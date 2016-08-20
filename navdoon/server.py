"""
navdoon.server
--------------
Define the Statsd server, that uses other components (collector, processor,
destination) to handle Statsd requests and flushe metrics to specified
destinations.
"""

import multiprocessing
from time import time, sleep
from threading import Thread, RLock, Event
from navdoon.pystdlib import queue
from navdoon.collector import AbstractCollector
from navdoon.utils.common import LoggerMixIn
from navdoon.processor import QueueProcessor


def validate_collectors(collectors):
    """Validate collectors to be usable by the server"""
    for collector in collectors:
        if not isinstance(collector, AbstractCollector):
            raise ValueError(
                "Collectors should extend AbstractCollector")


class Server(LoggerMixIn):
    """Statsd server
    Accepts multiple collectors, and a queue processor instance, creates a queue and shares it amongst all
    collectors and the processor.
    """

    def __init__(self):
        super(Server, self).__init__()
        self.log_signature = 'server '
        self._collectors = []
        self._running = Event()
        self._shutdown = Event()
        self._running_lock = RLock()
        self._shutdown_lock = RLock()
        self._queue = self._create_queue()
        self._queue_processor = None

    @property
    def queue_processor(self):
        return self._queue_processor

    @queue_processor.setter
    def queue_processor(self, value):
        if not isinstance(value, QueueProcessor):
            raise ValueError(
                "Invalid queue value. Processor should extend QueueProcessor")
        self._queue_processor = value

    def set_collectors(self, collectors):
        validate_collectors(collectors)
        self._collectors = collectors
        return self

    def start(self):
        """Starts the queue processor in background then starts all the collectors.
        Blocks current thread, until shutdown() is called from another thread.
        """
        if not self._collectors:
            raise Exception("Can not start Statsd server without a collector")
        if self._queue_processor is None:
            self._log_warn(
                "no queue processor provided. Creating a queue processor "
                "with no destinations")
            self._queue_processor = self.create_queue_processor()
        with self._running_lock:
            self._log("starting ...")
            self._share_queue()
            queue_thread = self._start_queue_processor(self._queue_processor)
            self._log_debug("started queue processor thread")
            try:
                self._start_collecting(self._collectors)
            finally:
                self._log("stopped, joining queue processor thread")
                queue_thread.join()
                self._running.clear()

    def _start_collecting(self, collectors):
        """Start all the collectors, blocking current thread until collector threads stop"""
        collector_threads = []
        self._log_debug("starting {} collectors ...".format(len(collectors)))
        for collector in collectors:
            thread = Thread(target=collector.start)
            collector_threads.append(thread)
            thread.start()
            collector.wait_until_queuing_requests()
        self._running.set()
        self._log("collectors are running")
        for thread in collector_threads:
            thread.join()

    def is_running(self):
        return self._running.is_set()

    def wait_until_running(self, timeout=None):
        self._running.wait(timeout)

    def shutdown(self, process_queue=True, timeout=None):
        """Shutdown the server, stopping the collectors and the queue processor"""
        with self._shutdown_lock:
            self._log("shutting down ...")
            start_time = time()
            self._shutdown_collectors(self._collectors, timeout)
            if self._queue_processor.is_processing():
                queue_timeout = max(0.1, timeout - (time() - start_time)) if timeout else None
                self._shutdown_queue_processor(self._queue_processor, process_queue, queue_timeout)
            else:
                self._log_debug("queue processor is not processing")
            self._close_queue()
            self._shutdown.set()

    def wait_until_shutdown(self, timeout=None):
        start = time()
        self._shutdown.wait(timeout)
        while True:
            if not self._running.is_set():
                break
            if timeout is not None and time() - start > timeout:
                raise Exception("Server shutdown timeout")
            sleep(0.5)

    def create_queue_processor(self):
        processor = QueueProcessor(self._queue)
        processor.logger = self.logger
        return processor

    def reload(self):
        raise NotImplementedError()

    @staticmethod
    def _use_multiprocessing():
        # FIXME: use multiprocessing if available
        # return available_cpus() > 1
        return False

    @classmethod
    def _create_queue(cls):
        return multiprocessing.Queue() if cls._use_multiprocessing(
        ) else queue.Queue()

    def _share_queue(self):
        queue_ = self._queue
        self._queue_processor.queue = queue_
        for collector in self._collectors:
            collector.queue = queue_

    def _close_queue(self):
        queue_ = self._queue
        if queue_:
            if callable(getattr(queue_, 'close', None)):
                queue_.close()
        self._queue = None

    def _start_queue_processor(self, processor):
        if self._use_multiprocessing():
            self._log_debug("stating queue processor in a separate process")
            queue_process = multiprocessing.Process(
                target=processor.process)
            queue_process.start()
        else:
            self._log_debug("stating queue processor in a thread")
            queue_process = Thread(target=processor.process)
            queue_process.start()

        processor.wait_until_processing(30)
        if not processor.is_processing():
            self._log_error(
                "queue processor didn't start correctly time is up")
            processor.shutdown()
            queue_process.join()
            raise Exception("Failed to start the queue processor")

        return queue_process

    def _shutdown_queue_processor(self, processor, process=True, timeout=None):
        start_time = time()
        self._log_debug("shutting down the queue processor ...")
        self._queue.put_nowait(processor.stop_process_token)
        if not process:
            processor.shutdown()
        processor.wait_until_shutdown(timeout)
        if processor.is_processing():
            self._log_error(
                "Queue processor shutdown timeout after {} seconds".format(
                    time() - start_time))
            raise Exception(
                "Server shutdown timeout when shutting down processor")

    def _shutdown_collectors(self, collectors, timeout=None):
        if not collectors:
            return

        start_time = time()
        self._log_debug("shutting down {} collectors ...".format(len(
            collectors)))

        for collector in collectors:
            self._log_debug("shutting down {}".format(collector))
            collector.shutdown()
            collector.wait_until_shutdown(timeout)
            self._log("{} shutdown successfully!".format(collector))
            if timeout is None:
                continue
            time_elapsed = time() - start_time
            if time_elapsed > timeout:
                self._log_error(
                    "collectors shutdown timeout after "
                    "{} seconds".format(time_elapsed))
                raise Exception(
                    "Server shutdown timed out when "
                    "shutting down collectors")
            else:
                timeout -= time_elapsed
        self._log_debug("all collectors shutdown")

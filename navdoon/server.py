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
from navdoon.utils import LoggerMixIn, available_cpus
from navdoon.processor import QueueProcessor


def validate_collectors(collectors):
    for collector in collectors:
        if not isinstance(collector, AbstractCollector):
            raise ValueError(
                "Invalid collector. Collectors should extend AbstractCollector")


class Server(LoggerMixIn):
    """Statsd server"""

    def __init__(self):
        super(Server, self).__init__()
        self.log_signature = 'server'
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
    def queue_processor(self, processor):
        if not isinstance(processor, QueueProcessor):
            raise ValueError(
                "Invalid queue processor. Processor should extend QueueProcessor")
        self._queue_processor = processor

    def set_collectors(self, collectors):
        validate_collectors(collectors)
        self._collectors = collectors
        return self

    def start(self):
        if not self._collectors:
            raise Exception("Can not start Statsd server without a collector")
        if self._queue_processor is None:
            self._log_warn("no queue processor provided. Creating a queue processor with no destinations")
            self._queue_processor = self.create_queue_processor()
        with self._running_lock:
            self._log("starting ...")
            self._share_queue_with_collectors_and_processor()
            queue_thread = self._start_queue_processor()
            self._log_debug("started queue processor thread")
            try:
                collector_threads = self._start_collector_threads()
                self._running.set()
                self._log("queue processor and collectors are running")
                for thread in collector_threads:
                    thread.join()
            finally:
                self._log("stopped, joining queue processor thread")
                queue_thread.join()
                self._running.clear()

    def is_running(self):
        return self._running.is_set()

    def wait_until_running(self, timeout=None):
        self._running.wait(timeout)

    def shutdown(self, process_queue=True, timeout=None):
        with self._shutdown_lock:
            self._log("shutting down ...")
            start_time = time()
            self._shutdown_collectors(timeout)
            if self._queue_processor.is_processing():
                self._shutdown_queue_processor(process_queue, max(
                    0.1, timeout - (time() - start_time)) if timeout else None)
            self._close_queue()
            self._shutdown.set()

    def wait_until_shutdown(self, timeout=None):
        start = time()
        self._shutdown.wait(timeout)
        while True:
            if not self._running.is_set():
                break
            if timeout is not None and time() - start > timeout:
                raise Exception("Servert shutdown timedout")
            sleep(0.5)

    @staticmethod
    def _use_multiprocessing():
        # FIXME: use multiprocessing if available
        #return available_cpus() > 1
        return False

    @classmethod
    def _create_queue(cls):
        return multiprocessing.Queue() if cls._use_multiprocessing(
        ) else queue.Queue()

    def create_queue_processor(self):
        processor = QueueProcessor(self._queue)
        processor.logger = self.logger
        return processor

    def _share_queue_with_collectors_and_processor(self):
        queue = self._queue
        self._queue_processor.queue = queue
        for collector in self._collectors:
            collector.queue = queue

    def _close_queue(self):
        queue = self._queue
        if queue:
            if callable(getattr(queue, 'close', None)):
                queue.close()
        self._queue = None

    def _start_queue_processor(self):
        if self._use_multiprocessing():
            self._log_debug("stating queue processor in a separate process")
            queue_process = multiprocessing.Process(
                target=self._queue_processor.process)
            queue_process.start()
        else:
            self._log_debug("stating queue processor in a thread")
            queue_process = Thread(target=self._queue_processor.process)
            queue_process.setDaemon(True)
            queue_process.start()

        self._queue_processor.wait_until_processing(30)
        if not self._queue_processor.is_processing():
            self._log_error("queue processor didn't start correctly time is up")
            self._queue_processor.shutdown()
            queue_process.join()
            raise Exception("Failed to start the queue processor")

        return queue_process

    def _shutdown_queue_processor(self, process=True, timeout=None):
        start_time = time()
        self._log_debug("shutting down the queue processor ...")
        self._queue.put_nowait(self._queue_processor.stop_process_token)
        if not process:
            self._queue_processor.shutdown()
        self._queue_processor.wait_until_shutdown(timeout)
        if self._queue_processor.is_processing():
            self._log_error("shutting down queue processor timedout after {} seconds".format(time() - start_time))
            raise Exception(
                "Server shutdown timedout when shutting down processor")

    def _start_collector_threads(self):
        collector_threads = []
        self._log_debug("stating {} collectors ...".format(len(self._collectors)))
        for collector in self._collectors:
            thread = Thread(target=collector.start)
            collector_threads.append(thread)
            thread.start()
            collector.wait_until_queuing_requests()
        return collector_threads

    def _shutdown_collectors(self, timeout=None):
        start_time = time()
        if self._collectors:
            self._log_debug("shutting down {} collectors ...".format(len(self._collectors)))
            for collector in self._collectors:
                collector.shutdown()
                collector.wait_until_shutdown(timeout)
                if timeout is not None:
                    time_elapsed = time() - start_time
                    if time_elapsed > timeout:
                        self._log_error("shutting down collectors timedout after {} seconds".format(time_elapsed))
                        raise Exception(
                            "Server shutdown timed out when shutting down collectors")
                    else:
                        timeout -= time_elapsed

"""
navdoon.server
--------------
Define the Statsd server, that uses other components (collector, processor,
destination) to handle Statsd requests and flush metrics to specified
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
        self._running_collectors = []
        self._running = Event()
        self._shutdown = Event()
        self._reload = Event()
        self._pause = Event()
        self._should_reload = Event()
        self._running_lock = RLock()
        self._pause_lock = RLock()
        self._queue = self._create_queue()
        self._queue_processor = None
        self._running_queue_processor = None

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
        """Start the queue processor in background then starts all the collectors.
        Blocks current thread, until shutdown() is called from another thread.
        """
        if not self._collectors:
            raise Exception("Can not start Statsd server without a collector")
        if self._queue_processor is None:
            self._log_warn(
                "no queue processor provided. Creating a queue processor "
                "with no destinations")
            self._queue_processor = self.create_queue_processor()
        reloading = False
        keep_running = True
        with self._running_lock:
            self._log("starting ...")
            while keep_running:
                self._should_reload.clear()
                self._share_queue()
                queue_thread = self._start_queue_processor()
                self._log_debug("started queue processor thread")
                try:
                    collector_threads = self._start_collectors()
                    self._running.set()
                    if reloading:
                        self._reload.set()
                    self._log("collectors are running")
                    self._pause.wait()
                    self._pause.clear()
                    self._shutdown_collectors()
                    for thread in collector_threads:
                        thread.join()
                    self._running_collectors = []
                    self._shutdown_queue_processor()
                finally:
                    self._log("stopped, joining queue processor thread")
                    queue_thread.join()
                    self._running.clear()
                reloading = self._should_reload.is_set()
                keep_running = reloading
                if reloading:
                    self._log("reloading ...")

    def _start_collectors(self):
        """Start collectors in background threads and returns the threads"""
        collector_threads = []
        self._log_debug("starting {} collectors ...".format(len(self._collectors)))
        for collector in self._collectors:
            thread = Thread(target=collector.start)
            collector_threads.append(thread)
            thread.start()
            collector.wait_until_queuing_requests()
            self._running_collectors.append(collector)
        return collector_threads

    def is_running(self):
        return self._running.is_set()

    def wait_until_running(self, timeout=None):
        self._running.wait(timeout)

    def shutdown(self, timeout=None):
        """Shutdown the server, stopping the collectors and the queue processor"""
        with self._pause_lock:
            self._log("shutting down ...")
            start_time = time()
            self._shutdown_collectors(timeout)
            if self._queue_processor.is_processing():
                queue_timeout = max(0.1, timeout - (time() - start_time)) if timeout else None
                self._shutdown_queue_processor(queue_timeout)
            else:
                self._log_debug("queue processor is not processing")
            self._pause.set()
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
        with self._pause_lock:
            self._reload.clear()
            self._should_reload.set()
            self._pause.set()

    def wait_until_reload(self, timeout=None):
        self._reload.wait(timeout)

    @staticmethod
    def _use_multiprocessing():
        # FIXME: use multiprocessing if available
        # return available_cpus() > 1
        return False

    @classmethod
    def _create_queue(cls):
        return multiprocessing.Queue() if cls._use_multiprocessing() else queue.Queue()

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

    def _start_queue_processor(self):
        if self._use_multiprocessing():
            self._log_debug("starting queue processor in a separate process")
            queue_process = multiprocessing.Process(target=self._queue_processor.process)
            queue_process.start()
        else:
            self._log_debug("starting queue processor in a thread")
            queue_process = Thread(target=self._queue_processor.process)
            queue_process.start()

        self._queue_processor.wait_until_processing(30)
        if not self._queue_processor.is_processing():
            self._log_error("queue processor didn't start correctly time is up")
            self._queue_processor.shutdown()
            queue_process.join()
            raise Exception("Failed to start the queue processor")
        self._running_queue_processor = self._queue_processor
        return queue_process

    def _shutdown_queue_processor(self, timeout=None):
        if not self._running_queue_processor:
            return False
        start_time = time()
        self._log_debug("shutting down the queue processor ...")
        self._running_queue_processor.shutdown()
        self._running_queue_processor.wait_until_shutdown(timeout)
        if self._running_queue_processor.is_processing():
            self._log_error(
                "Queue processor shutdown timeout after {} seconds".format(
                    time() - start_time))
            raise Exception(
                "Server shutdown timeout when shutting down processor")
        self._running_queue_processor = None
        return True

    def _shutdown_collectors(self, timeout=None):
        if not self._running_collectors:
            return

        start_time = time()
        self._log_debug("shutting down {} collectors ...".format(len(
            self._running_collectors)))

        stopped_collectors = []
        try:
            for collector in self._running_collectors:
                self._log_debug("shutting down {}".format(collector))
                collector.shutdown()
                collector.wait_until_shutdown(timeout)
                self._log("{} shutdown successfully!".format(collector))
                stopped_collectors.append(collector)
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
        finally:
            for collector in stopped_collectors:
                self._running_collectors.remove(collector)

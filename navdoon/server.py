"""
navdoon.server
--------------
Define the server that handles Statsd requests and flushes metrics to
specified destinations
"""

import multiprocessing
import threading
from time import time
from navdoon.procssor import QueueProcessor
from navdoon.utils import LoggerMixIn

class Server(LoggerMixIn):
    def __init__(self):
        LoggerMixIn.__init__(self)
        self.shutdown_timeout = 5
        self._destinations = []
        self._collectors = []
        self._queue = self._create_queue()
        self._queue_processor = QueueProcessor(self._queue)
        self._running = threading.Event()
        self._runing_lock = threading.Lock()
        self._shutdown_lock = threading.Lock()

    def _create_queue(self):
        return multiprocessing.Queue()

    def add_destination(self, destination):
        if not destination in self._destinations:
            self._queue_processor.add_destination(destination)
            self._destinations.append(destination)
        return self

    def add_collector(self, collector):
        if not hasattr(collector, 'queue'):
            raise ValueError("Collector should have a queue attribute")
        if not hasattr(collector, 'shutdown') or not callable(collector.shutdown):
            raise ValueError("Collector should have a shutdown method")
        if not collector in self._collectors:
            collector.queue = self._queue
            self._collectors.append(collector)
        return self

    def start(self):
        with self._runing_lock:
            try:
                if not self._collectors:
                    raise Exception("No collectors ar specified for the server")
                self._start_queue_processor()
                self._start_collectors()
                self._running.set()
            finally:
                self._running.clear()

    def is_running(self):
        return self._running.is_set()

    def wait_until_running(self, timeout=None):
        self._running.wait(timeout)

    def shutdown(self, process_queue=True):
        with self._shutdown_lock:
            start_time = time()
            collector_shutdown_timeout = self.shutdown_timeout / len(self._collectors)
            if self._collectors:
                for collector in self._collectors:
                    collector.shutdown()
                    collector.wait_until_shutdown(collector_shutdown_timeout)
                    if time() - start_time > self.shutdown_timeout:
                        raise Exception("Server shutdown timed out when shutting down collectors")
            self._queue.put_nowait(self._queue_processor.stop_process_token)
            if not process_queue:
                processor_timeout = max(0.1, self.shutdown_timeout - (time() - start_time))
                self._queue_processor.shutdown()
                self._queue_processor.wait_until_shutdown(processor_timeout)
                if self._queue_processor.is_processing():
                    raise Exception("Server shutdown timedout when shutting down processor")
            self._queue_processor.wait_until_processing(processor_timeout)

    def _start_queue_processor(self):
        self._queue_processor.process()
        self._queue_processor.wait_until_running(30)
        if not self._queue_processor.is_processing():
            self._queue_processor.shutdown()
            raise Exception("Failed to start the queue processor")

    def _start_collectors(self):
        self._queue_processor.procssor()
        self._queue_processor.wait_until_running(30)
        if not self._queue_processor.is_processing():
            self._queue_processor.shutdown()
            raise Exception("Failed to start the queue processor")


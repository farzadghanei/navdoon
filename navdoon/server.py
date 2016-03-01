"""
navdoon.server
--------------
Define the Statsd server, that uses other components (collector, processor,
destination) to handle Statsd requests and flushe metrics to specified
destinations.
"""

from time import time, sleep
from threading import Thread, RLock, Event
import multiprocessing
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
        self._collectors = []
        self._queue = self._create_queue()
        self._queue_processor = QueueProcessor(self._queue)
        self._running = Event()
        self._shutdown = Event()
        self._running_lock = RLock()
        self._shutdown_lock = RLock()

    @staticmethod
    def _use_multiprocessing():
        #return available_cpus() > 1
        return False

    @classmethod
    def _create_queue(cls):
        return multiprocessing.Queue() if cls._use_multiprocessing(
        ) else queue.Queue()

    def set_destinations(self, destinations):
        self._queue_processor.set_destinations(destinations)
        return self

    def set_collectors(self, collectors):
        validate_collectors(collectors)
        self._collectors = collectors
        return self

    def start(self):
        if not self._collectors:
            raise Exception("Can not start Statsd server without a collector")
        with self._running_lock:
            queue_proc = self._start_queue_processor()
            try:
                collector_threads = self._start_collector_threads()
                self._running.set()
                for thread in collector_threads:
                    thread.join()
            finally:
                queue_proc.join()
                self._running.clear()

    def is_running(self):
        return self._running.is_set()

    def wait_until_running(self, timeout=None):
        self._running.wait(timeout)

    def shutdown(self, process_queue=True, timeout=None):
        with self._shutdown_lock:
            start_time = time()
            self._shutdown_collectors(timeout)

            if self._queue_processor.is_processing():
                self._shutdown_queue_processor(max(0.1, timeout - (time(
                ) - start_time)) if timeout else None)
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

    def _start_queue_processor(self):
        if self._use_multiprocessing():
            queue_process = Process(target=self._queue_processor.process)
            queue_process.start()
        else:
            queue_process = Thread(target=self._queue_processor.process)
            queue_process.setDaemon(True)
            queue_process.start()

        self._queue_processor.wait_until_processing(30)
        if not self._queue_processor.is_processing():
            self._queue_processor.shutdown()
            queue_process.join()
            raise Exception("Failed to start the queue processor")

        return queue_process

    def _shutdown_queue_processor(self, process=True, timeout=None):
        self._queue.put_nowait(self._queue_processor.stop_process_token)
        if not process:
            self._queue_processor.shutdown()
        self._queue_processor.wait_until_shutdown(timeout)
        if self._queue_processor.is_processing():
            raise Exception(
                "Server shutdown timedout when shutting down processor")

    def _start_collector_threads(self):
        collector_threads = []
        for collector in self._collectors:
            thread = Thread(target=collector.start)
            collector_threads.append(thread)
            thread.start()
            collector.wait_until_queuing_requests()
        return collector_threads

    def _shutdown_collectors(self, timeout=None):
        if self._collectors:
            for collector in self._collectors:
                collector.shutdown()
                collector.wait_until_shutdown(timeout)
                if timeout is not None:
                    time_elapsed = time() - start_time
                    if time_elapsed > timeout:
                        raise Exception(
                            "Server shutdown timed out when shutting down collectors")
                    else:
                        timeout -= time_elapsed

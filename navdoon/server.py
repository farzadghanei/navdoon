"""
navdoon.server
--------------
Define the Statsd server, that uses other components (collector, processor,
destination) to handle Statsd requests and flushe metrics to specified
destinations.
"""

from time import time
from threading import Thread, RLock, Event
import multiprocessing
from navdoon.pystdlib import queue
from navdoon.utils import LoggerMixIn
from navdoon.processor import QueueProcessor


def cpu_count():
    try:
        cpu_count = multiprocessing.cpu_count()
    except Exception:
        cpu_count = 1
    return cpu_count


class Server(LoggerMixIn):
    """Statsd server"""

    def __init__(self):
        super(Server, self).__init__()
        self.shutdown_timeout = 5
        self._destinations = []
        self._collectors = []
        self._queue = self._create_queue()
        self._queue_processor = QueueProcessor(self._queue)
        self._running = Event()
        self._running_lock = RLock()
        self._shutdown_lock = RLock()

    @staticmethod
    def _use_multiprocessing():
        #return cpu_count() > 1
        return False

    @classmethod
    def _create_queue(cls):
        return multiprocessing.Queue() if cls._use_multiprocessing() else queue.Queue()

    def set_destinations(self, destinations):
        for destination in destinations:
            if not destination in self._destinations:
                self._queue_processor.add_destination(destination)
                self._destinations.append(destination)
        return self

    def start(self):
        if not self._collectors:
            raise Exception(
                "Can not start Statsd server without a collector")
        with self._running_lock:
            queue_proc = self._start_queue_processor()
            try:
                collector_threads = self._start_collector_threads()
                self._running.set()
                for thread in collector_threads:
                    thread.join()
            finally:
                self._running.clear()
                queue_proc.join()

    def is_running(self):
        return self._running.is_set()

    def wait_until_running(self, timeout=None):
        self._running.wait(timeout)

    def shutdown(self, process_queue=True):
        with self._shutdown_lock:
            start_time = time()
            if self._collectors:
                collector_shutdown_timeout = self.shutdown_timeout / len(
                        self._collectors)
                for collector in self._collectors:
                    collector.shutdown()
                    collector.wait_until_shutdown(collector_shutdown_timeout)
                    if time() - start_time > self.shutdown_timeout:
                        raise Exception(
                            "Server shutdown timed out when shutting down collectors")
            self._queue.put_nowait(self._queue_processor.stop_process_token)
            processor_timeout = max(0.1, self.shutdown_timeout -
                                    (time() - start_time))

            if self._queue_processor.is_processing():
                if not process_queue:
                    self._queue_processor.shutdown()
                    self._queue_processor.wait_until_shutdown(processor_timeout)
                    if self._queue_processor.is_processing():
                        raise Exception(
                            "Server shutdown timedout when shutting down processor")
                self._queue_processor.wait_until_processing(processor_timeout)

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

    def _start_collector_threads(self):
        with self._running_lock:
            collector_threads = []
            for collector in self._collectors:
                thread = Thread(target=collector.serve)
                collector_threads.append(thread)
                thread.start()
                collector.wait_until_queuing_requests()
            return collector_threads

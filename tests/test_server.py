import unittest
import logging
from random import random
from time import sleep
from threading import Event, Thread
from statsdmetrics import Counter
from navdoon.destination import AbstractDestination
from navdoon.processor import QueueProcessor
from navdoon.collector import AbstractCollector
from navdoon.server import Server, validate_collectors


class StubDestination(AbstractDestination):
    def __init__(self, expected_count=0):
        self.metrics = []
        self.expected_count = expected_count
        self._flushed_expected_count = Event()

    def flush(self, metrics):
        self.metrics.extend(metrics)
        if len(self.metrics) >= self.expected_count:
            self._flushed_expected_count.set()

    def wait_until_expected_count_items(self, timeout=None):
        self._flushed_expected_count.wait(timeout)


class StubCollector(AbstractCollector):
    def __init__(self, data=None, frequency=1.0):
        super(StubCollector, self).__init__()
        self.data = data
        self.max_items = None
        self.frequency = float(frequency)
        self._shutdown = Event()
        self.queued_data = []

    def start(self):
        while not self._shutdown.is_set():
            if self.max_items is None or self.max_items > len(
                    self.queued_data):
                self.queue.put(self.data)
                self.queued_data.append(self.data)
            sleep(random() / self.frequency)

    def wait_until_queuing_requests(self, timeout=None):
        pass

    def shutdown(self):
        self._shutdown.set()

    def wait_until_shutdown(self, timeout=None):
        self._shutdown.wait(timeout)


class TestFunctions(unittest.TestCase):
    def test_validate_collectors_fails_on_non_collectors(self):
        self.assertRaises(ValueError, validate_collectors, ["not a collector"])
        self.assertRaises(ValueError, validate_collectors, [2])

    def test_validate_collectors(self):
        collector = StubCollector()
        validate_collectors([collector])


class TestServer(unittest.TestCase):
    def test_queue_processor(self):
        server = Server()
        server.logger = logging.getLogger('test')
        processor = server.queue_processor
        self.assertIsInstance(processor, QueueProcessor)

    def test_start_fails_without_collectors(self):
        server = Server()
        server.queue_processor.set_destinations([StubDestination()])
        self.assertRaises(Exception, server.start)

    def test_start_and_shutdown(self):
        server = Server()
        processor = server.queue_processor
        processor.set_destinations([StubDestination()])
        collector = StubCollector('-')
        server.set_collectors([collector])
        server_thread = Thread(target=server.start)
        server_thread.setDaemon(True)
        server_thread.start()
        server.wait_until_running(5)
        self.assertTrue(server.is_running())
        server.shutdown()
        server.wait_until_shutdown(5)
        self.assertFalse(server.is_running())
        self.assertFalse(server_thread.isAlive())

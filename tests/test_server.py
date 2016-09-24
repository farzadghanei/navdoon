import sys
import unittest
import logging
from random import random
from time import sleep, time
from threading import Event, Thread

from statsdmetrics import Counter
from navdoon.destination import AbstractDestination
from navdoon.processor import QueueProcessor
from navdoon.collector import AbstractCollector
from navdoon.server import Server, validate_collectors


class StubDestination(AbstractDestination):
    """Stub destination to inspect server behavior"""

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
    """Stub collector to inspect server behavior"""

    def __init__(self, data=None, frequency=1.0):
        super(StubCollector, self).__init__()
        self.data = data
        self.max_items = None
        self.frequency = float(frequency)
        self._shutdown = Event()
        self._running = Event()
        self.queued_data = []

    def start(self):
        self._running.set()
        while not self._shutdown.is_set():
            if self.max_items is None or self.max_items > len(
                    self.queued_data):
                self.queue.put(self.data)
                self.queued_data.append(self.data)
            sleep(random() / self.frequency)
        self._running.clear()

    def wait_until_queuing_requests(self, timeout=None):
        pass

    def shutdown(self):
        self._shutdown.set()

    def is_queuing_requests(self):
        return self._running.is_set()

    def wait_until_shutdown(self, timeout=None):
        self._shutdown.wait(timeout)


class TestFunctions(unittest.TestCase):
    """Test server module functions"""

    def test_validate_collectors_fails_on_non_collectors(self):
        self.assertRaises(ValueError, validate_collectors, ["not a collector"])
        self.assertRaises(ValueError, validate_collectors, [2])

    def test_validate_collectors(self):
        collector = StubCollector()
        validate_collectors([collector])


class TestServer(unittest.TestCase):
    """Test Server"""

    def test_create_queue_processor(self):
        server = Server()
        server.logger = logging.getLogger('test')
        processor = server.create_queue_processor()
        self.assertIsInstance(processor, QueueProcessor)
        self.assertEqual(server.logger, processor.logger)

    def test_start_fails_without_collectors(self):
        server = Server()
        processor = server.create_queue_processor()
        processor.set_destinations([StubDestination()])
        server.queue_processor = processor
        self.assertRaises(Exception, server.start)

    def test_server_creates_a_default_queue_processor_without_destination(
            self):
        server = Server()
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

    def test_start_and_shutdown_with_configured_queue_processor(self):
        start_time = time()
        destination = StubDestination(10)
        server = Server()
        processor = server.create_queue_processor()
        processor.set_destinations([destination])
        processor.flush_interval = 0.5
        server.queue_processor = processor
        metric = Counter('test.metric', 1)
        collector = StubCollector(data=metric.to_request(), frequency=10)
        server.set_collectors([collector])
        server_thread = Thread(target=server.start)
        server_thread.setDaemon(True)
        server_thread.start()
        server.wait_until_running(5)
        self.assertTrue(server.is_running())
        destination.wait_until_expected_count_items(10)

        server.shutdown()
        server.wait_until_shutdown(5)
        self.assertFalse(server.is_running())
        self.assertFalse(server_thread.isAlive())
        self.assertFalse(collector.is_queuing_requests())
        self.assertFalse(processor.is_processing())

        self.assertGreaterEqual(len(destination.metrics), 10)
        for metric in destination.metrics:
            self.assertEqual(3, len(metric))
            self.assertEqual(metric[0], "test.metric")
            self.assertGreaterEqual(metric[1], 0)
            self.assertGreaterEqual(metric[2], start_time)

    def test_reload_stops_collectors_and_processor_and_new_ones_used_in_server_start_thread(self):
        start_time = time()
        destination = StubDestination(10)
        server = Server()
        processor = server.create_queue_processor()
        processor.set_destinations([destination])
        processor.flush_interval = 0.5
        server.queue_processor = processor
        metric = Counter('test.metric', 1)
        collector = StubCollector(data=metric.to_request(), frequency=10)
        server.set_collectors([collector])
        server_thread = Thread(target=server.start)
        server_thread.setDaemon(True)
        server_thread.start()
        server.wait_until_running(5)
        self.assertTrue(server.is_running())
        destination.wait_until_expected_count_items(10)

        metric2 = Counter('test.metric2', 1)
        collector2 = StubCollector(data=metric2.to_request(), frequency=10)
        destination2 = StubDestination(5)
        processor2 = server.create_queue_processor()
        processor2.set_destinations([destination2])
        processor2.flush_interval = 0.5
        server.queue_processor = processor2
        server.set_collectors([collector2])
        server.reload()
        server.wait_until_reload(10)
        self.assertTrue(server_thread.isAlive())
        self.assertTrue(server.is_running())
        self.assertTrue(collector2.is_queuing_requests())
        self.assertTrue(processor2.is_processing())
        self.assertFalse(collector.is_queuing_requests())
        self.assertFalse(processor.is_processing())
        destination2.wait_until_expected_count_items(15)

        self.assertEqual(len(destination2.metrics), 5)
        for metric in destination2.metrics:
            self.assertEqual(3, len(metric))
            self.assertEqual(metric[0], "test.metric2")
            self.assertGreaterEqual(metric[1], 0)
            self.assertGreaterEqual(metric[2], start_time)

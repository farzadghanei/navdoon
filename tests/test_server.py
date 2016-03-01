import unittest
from random import random
from time import sleep
from threading import Event, Thread
from statsdmetrics import Counter
from navdoon.destination import AbstractDestination
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
    def __init__(self, data=None):
        super(StubCollector, self).__init__()
        self.data = data
        self._shutdown = Event()
        self.queued_data = []

    def start(self):
        while not self._shutdown.is_set():
            self.queue.put(self.data)
            self.queued_data.append(self.data)
            sleep(random())

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
    def test_set_destination_fails_on_invalid_destination(self):
        server = Server()
        self.assertRaises(ValueError, server.set_destinations,
                          "not a destination")

    def test_set_destinations(self):
        server = Server()
        destinations = [StubDestination()]
        server.set_destinations(destinations)
        self.assertEqual(destinations, server._queue_processor._destinations)

    def test_start_fails_without_collectors(self):
        server = Server()
        server.set_destinations([StubDestination()])
        self.assertRaises(Exception, server.start)

    def test_start_and_shutdown(self):
        server = Server()
        dest = StubDestination()
        server.set_destinations([dest])
        metric = Counter('test.event', 1)
        collector = StubCollector(metric.to_request())
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

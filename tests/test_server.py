import unittest
from threading import Event
from navdoon.server import Server
from navdoon.utils import LoggerMixIn


class StubDestination(LoggerMixIn):
    def __init__(self, expected_count = 0):
        LoggerMixIn.__init__(self)
        self.log_signature = 'test.destination'
        self.metrics = []
        self.expected_count = expected_count
        self._flushed_expected_count = Event()

    def flush(self, metrics):
        self._log_debug("{} metrics flushed".format(len(metrics)))
        self.metrics.extend(metrics)
        if len(self.metrics) >= self.expected_count:
            self._flushed_expected_count.set()

    def wait_until_expected_count_items(self, timeout=None):
        self._log("flush destination waiting for expected items to be flushed ...")
        self._flushed_expected_count.wait(timeout)


class TestServer(unittest.TestCase):

    def test_add_destinations(self):
        destination1 = StubDestination()

        server = Server()
        server.add_destination(destination1)
        server.add_destination(destination1)
        self.assertEqual([destination1], server._destinations)

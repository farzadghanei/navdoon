import unittest

from time import time
from navdoon.destination import Graphite


class TestGraphite(unittest.TestCase):
    def test_create_request_from_metrics(self):
        metrics = [('users', 34, 123456), ('cpu', 78, 98765)]
        self.assertEqual(["users 34 123456", "cpu 78 98765"],
                         Graphite.create_request_from_metrics(metrics), )

        metrics = [('no.time', 34), ('is.fine', 78, time())]
        self.assertEqual(2, len(Graphite.create_request_from_metrics(metrics)))

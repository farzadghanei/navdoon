import unittest

from statsdmetrics import Counter
from navdoon.processor import QueueProcessor, StatsShelf


class TestQueueProcessor(unittest.TestCase):
    pass


class TestStatsShelf(unittest.TestCase):

    def test_counter(self):
        shelf = StatsShelf()
        shelf.add(Counter("mymetric", 3))
        shelf.add(Counter("mymetric", 2))
        shelf.add(Counter("something.else", 2, 0.5))
        expected = {"mymetric": 5, "something.else": 4}
        self.assertEqual(expected, shelf.counters())

import unittest

from statsdmetrics import Counter, Set, Gauge, GaugeDelta
from navdoon.processor import QueueProcessor, StatsShelf


class TestQueueProcessor(unittest.TestCase):
    pass


class TestStatsShelf(unittest.TestCase):
    def test_counters(self):
        shelf = StatsShelf()
        self.assertEqual(dict(), shelf.counters())

        shelf.add(Counter("mymetric", 3))
        shelf.add(Counter("mymetric", 2))
        shelf.add(Counter("something.else", 2, 0.5))
        expected = {"mymetric": 5, "something.else": 4}
        self.assertEqual(expected, shelf.counters())

        counters = shelf.counters()
        counters["counters should"] = "not changed"
        self.assertEqual(expected, shelf.counters())

    def test_sets(self):
        shelf = StatsShelf()
        self.assertEqual(dict(), shelf.sets())

        shelf.add(Set("users", "me"))
        shelf.add(Set("users", "me"))
        shelf.add(Set("users", "you"))
        shelf.add(Set("say.what?", "nothing"))
        shelf.add(Set("users", "me"))
        shelf.add(Set("say.what?", "nothing"))
        shelf.add(Set("say.what?", "ok"))
        expected = {"users": set(("me", "you")),
                    "say.what?": set(("nothing", "ok"))}
        self.assertEqual(expected, shelf.sets())

        sets = shelf.sets()
        sets["sets should"] = set("not change")
        self.assertEqual(expected, shelf.sets())

    def test_gauges(self):
        shelf = StatsShelf()
        self.assertEqual(dict(), shelf.gauges())

        shelf.add(Gauge("cpu%", 50))
        shelf.add(Gauge("cpu%", 51))
        shelf.add(Gauge("mem%", 20))
        shelf.add(Gauge("mem%", 23))
        shelf.add(Gauge("cpu%", 58))

        expected = {"cpu%": 58, "mem%": 23}
        self.assertEqual(expected, shelf.gauges())

        gauges = shelf.gauges()
        gauges["gauges should"] = "not change"
        self.assertEqual(expected, shelf.gauges())

    def test_gauge_deltas(self):
        shelf = StatsShelf()
        self.assertEqual(dict(), shelf.gauges())

        shelf.add(GaugeDelta("cpu%", 10))
        shelf.add(Gauge("mem%", 10))
        shelf.add(GaugeDelta("cpu%", 10))
        shelf.add(GaugeDelta("cpu%", -5))
        shelf.add(GaugeDelta("mem%", -2))
        shelf.add(GaugeDelta("mem%", 4))

        expected = {"cpu%": 15, "mem%": 12}
        self.assertEqual(expected, shelf.gauges())

    def test_clear_all_metrics(self):
        shelf = StatsShelf()

        shelf.add(Set("users", "me"))
        shelf.add(Counter("mymetric", 3))
        shelf.clear()

        self.assertEqual(dict(), shelf.counters())
        self.assertEqual(dict(), shelf.sets())
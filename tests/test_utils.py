import unittest
import navdoon.utils


def mock_cpu_count(count):
    def _cpu_count():
        return count

    return _cpu_count


def not_implemented(*args):
    raise NotImplementedError


class TestFunctions(unittest.TestCase):
    def test_available_cpus_returns_number_of_cpus(self):
        navdoon.utils.cpu_count = mock_cpu_count(3)
        self.assertEqual(3, navdoon.utils.available_cpus())

    def test_available_cpus_returns_minimum_count_on_errors(self):
        navdoon.utils.cpu_count = not_implemented
        self.assertEqual(1, navdoon.utils.available_cpus())


class TestDataSeries(unittest.TestCase):
    def test_mean(self):
        simple = navdoon.utils.DataSeries([10,20,30])
        self.assertEqual(20, simple.mean())

        negative = navdoon.utils.DataSeries([-2,0.8,12, 100])
        self.assertEqual(27.7, negative.mean())

        single = navdoon.utils.DataSeries([18.4])
        self.assertEqual(18.4, single.mean())

    def test_max(self):
        simple = navdoon.utils.DataSeries([10,20,30])
        self.assertEqual(30, simple.max())

        negative = navdoon.utils.DataSeries([-2,0.6,0, 13.2])
        self.assertEqual(13.2, negative.max())

        single = navdoon.utils.DataSeries([17.9])
        self.assertEqual(17.9, single.max())

    def test_min(self):
        simple = navdoon.utils.DataSeries([10,20,30])
        self.assertEqual(10, simple.min())

        negative = navdoon.utils.DataSeries([-2,0.6,0, 13.2])
        self.assertEqual(-2, negative.min())

        single = navdoon.utils.DataSeries([14.6])
        self.assertEqual(14.6, single.min())

    def test_median(self):
        simple = navdoon.utils.DataSeries([10,20,30])
        self.assertEqual(20, simple.median())

        with_float = navdoon.utils.DataSeries([2,0.6,0, 13.2])
        self.assertEqual(7.6, with_float.median())

        single = navdoon.utils.DataSeries([12.8])
        self.assertEqual(12.8, single.median())

        double = navdoon.utils.DataSeries([12.8, 14])
        self.assertEqual(13.4, double.median())
import unittest
import navdoon.utils.common


class TestDataSeries(unittest.TestCase):
    def test_mean(self):
        simple = navdoon.utils.common.DataSeries([10,20,30])
        self.assertEqual(20, simple.mean())

        negative = navdoon.utils.common.DataSeries([-2,0.8,12, 100])
        self.assertEqual(27.7, negative.mean())

        single = navdoon.utils.common.DataSeries([18.4])
        self.assertEqual(18.4, single.mean())

    def test_max(self):
        simple = navdoon.utils.common.DataSeries([10,20,30])
        self.assertEqual(30, simple.max())

        negative = navdoon.utils.common.DataSeries([-2,0.6,0, 13.2])
        self.assertEqual(13.2, negative.max())

        single = navdoon.utils.common.DataSeries([17.9])
        self.assertEqual(17.9, single.max())

    def test_min(self):
        simple = navdoon.utils.common.DataSeries([10,20,30])
        self.assertEqual(10, simple.min())

        negative = navdoon.utils.common.DataSeries([-2,0.6,0, 13.2])
        self.assertEqual(-2, negative.min())

        single = navdoon.utils.common.DataSeries([14.6])
        self.assertEqual(14.6, single.min())

    def test_median(self):
        simple = navdoon.utils.common.DataSeries([10,20,30])
        self.assertEqual(20, simple.median())

        with_float = navdoon.utils.common.DataSeries([2,0.6,0, 13.2])
        self.assertEqual(7.6, with_float.median())

        single = navdoon.utils.common.DataSeries([12.8])
        self.assertEqual(12.8, single.median())

        double = navdoon.utils.common.DataSeries([12.8, 14])
        self.assertEqual(13.4, double.median())

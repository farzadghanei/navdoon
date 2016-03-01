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

import unittest
import navdoon.utils.system
from navdoon.utils.system import TaskThreadPool


def mock_cpu_count(count):
    def _cpu_count():
        return count

    return _cpu_count


def not_implemented(*args):
    raise NotImplementedError


class TestFunctions(unittest.TestCase):
    def test_available_cpus_returns_number_of_cpus(self):
        navdoon.utils.system.cpu_count = mock_cpu_count(3)
        self.assertEqual(3, navdoon.utils.system.available_cpus())

    def test_available_cpus_returns_minimum_count_on_errors(self):
        navdoon.utils.system.cpu_count = not_implemented
        self.assertEqual(1, navdoon.utils.system.available_cpus())


class TestTaskThreadPool(unittest.TestCase):
    def test_init(self):
        pool = TaskThreadPool(4)
        self.assertEquals(pool.size, 4)

    def test_initialize(self):
        pool = TaskThreadPool(4)
        pool.initialize()
        self.assertEqual(len(pool.threads), 4)

    def test_do_tasks(self):
        pool = TaskThreadPool(4)
        pool.initialize()
        executed = []

        def some_task():
            return executed.append(True)

        for i in range(10):
            pool.do(some_task)

        pool.wait_until_done()
        pool.stop()
        self.assertEqual(executed, [True] * 10)

    def test_check_task_results(self):
        pool = TaskThreadPool(5)
        pool.initialize()

        def change_text(text, number):
            return "{}. {}".format(number, text.upper())

        words = ["this", "will be", "uppercased"]
        expected_results = ["1. THIS", "2. WILL BE", "3. UPPERCASED"]
        counter = 1
        task_ids = []

        for word in words:
            task_ids.append(pool.do(change_text, word, counter))
            counter += 1

        pool.wait_until_done()
        pool.stop()
        results = []

        for id in task_ids:
            results.append(pool.get_result(id))

        self.assertEqual(results, expected_results)

    def test_check_task_results_fails_on_invalid_task_id(self):
        pool = TaskThreadPool(2)
        pool.initialize()
        pool.stop()
        self.assertRaises(ValueError, pool.get_result, 1003)
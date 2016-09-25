import unittest
import logging
import sys
from time import time, sleep
from threading import Thread, Event
from statsdmetrics import Counter, Set, Gauge, GaugeDelta, Timer
from navdoon.pystdlib.queue import Queue
from navdoon.processor import QueueProcessor, StatsShelf
from navdoon.utils.common import LoggerMixIn
from navdoon.destination import AbstractDestination


def create_debug_logger():
    logger = logging.Logger('navdoon.test')
    logger.addHandler(logging.StreamHandler(sys.stderr))
    logger.setLevel(logging.DEBUG)
    return logger


class DestinationWithoutFlushMethod(object):
    pass


class StubDestination(LoggerMixIn, AbstractDestination):
    def __init__(self, expected_count=0):
        super(StubDestination, self).__init__()
        self.log_signature = 'test.destination '
        self.metrics = []
        self.expected_count = expected_count
        self.flushed_expected_count = Event()

    def flush(self, metrics):
        self._log_debug("received {} metrics".format(len(metrics)))
        self.metrics.extend(metrics)
        if len(self.metrics) >= self.expected_count:
            self.flushed_expected_count.set()
        else:
            self.flushed_expected_count.clear()

    def wait_until_expected_count_items(self, timeout=None):
        self._log(
            "flush destination waiting for expected items to be flushed ...")
        self.flushed_expected_count.wait(timeout)


class TestQueueProcessor(unittest.TestCase):
    """Test processor.QueueProcessor class"""

    def test_set_flush_interval_accepts_positive_numbers(self):
        processor = QueueProcessor(Queue())
        processor.flush_interval = 103
        self.assertEqual(103, processor.flush_interval)
        processor.flush_interval = 0.58
        self.assertEqual(0.58, processor.flush_interval)
        processor.flush_interval = '3.4'
        self.assertEqual(3.4, processor.flush_interval)

    def test_set_flush_interval_fails_on_not_positive_numbers(self):
        processor = QueueProcessor(Queue())

        def set_interval(value):
            processor.flush_interval = value

        self.assertRaises(ValueError, set_interval, 0)
        self.assertRaises(ValueError, set_interval, -10)
        self.assertRaises(ValueError, set_interval, "not a number")

    def test_processor_does_not_accept_invalid_queue(self):
        self.assertRaises(ValueError, QueueProcessor, "not a queue")
        self.assertRaises(ValueError, QueueProcessor, 100)

        processor = QueueProcessor(Queue())

        def set_queue(value):
            processor.queue = value

        self.assertRaises(ValueError, set_queue, "not a queue")
        self.assertRaises(ValueError, set_queue, 100)

    def test_set_the_queue(self):
        queue_ = Queue()
        processor = QueueProcessor(queue_)
        self.assertEqual(queue_, processor.queue)

        next_queue = Queue()
        processor.queue = next_queue
        self.assertEqual(next_queue, processor.queue)

    def test_set_destination_fails_on_invalid_destination(self):
        processor = QueueProcessor(Queue())
        self.assertRaises(ValueError, processor.set_destinations,
                          "not a destination")

    def test_set_destinations_when_not_started(self):
        processor = QueueProcessor(Queue())
        destinations = [StubDestination()]
        processor.set_destinations(destinations)
        self.assertEqual(destinations, processor._destinations)
        self.assertFalse(processor.is_processing())

    def test_destinations_can_change_when_queue_processor_is_running(self):
        processor = QueueProcessor(Queue())
        try:
            destinations = [StubDestination()]
            processor.set_destinations(destinations)
            processor_thread = Thread(target=processor.process)
            processor_thread.start()
            processor.wait_until_processing(10)
            self.assertTrue(processor.is_processing())
            new_destinations = [StubDestination()]
            processor.set_destinations(new_destinations)
            self.assertEqual(new_destinations, processor.get_destinations())
            self.assertTrue(processor.is_processing())
        finally:
            processor.shutdown()

    def test_clear_destinations(self):
        destination = StubDestination()
        queue_ = Queue()
        processor = QueueProcessor(queue_)
        processor.set_destinations([destination])
        self.assertEqual([destination], processor._destinations)
        processor.clear_destinations()
        self.assertEqual([], processor._destinations)

    def test_process(self):
        expected_flushed_metrics_count = 2
        metrics = (Counter('user.jump', 2),
                   Set('username', 'navdoon'),
                   Set('username', 'navdoon.test'),
                   Counter('user.jump', 4),
                   Set('username', 'navdoon'),
                   Counter('user.jump', -1),)
        queue_ = Queue()
        destination = StubDestination()
        destination.expected_count = expected_flushed_metrics_count
        processor = QueueProcessor(queue_)
        processor.set_destinations([destination])
        processor.init_destinations()
        process_thread = Thread(target=processor.process)
        process_thread.start()
        processor.wait_until_processing(5)
        for metric in metrics:
            queue_.put(metric.to_request())
        destination.wait_until_expected_count_items(5)
        processor.shutdown()
        processor.wait_until_shutdown(5)
        self.assertEqual(expected_flushed_metrics_count,
                         len(destination.metrics))
        self.assertEqual(('user.jump', 5), destination.metrics[0][:2])
        self.assertEqual(('username', 2), destination.metrics[1][:2])

    def test_process_stops_on_stop_token_in_queue(self):
        token = 'STOP'
        expected_flushed_metrics_count = 2
        metrics = (Counter('user.login', 1),
                   Set('username', 'navdoon'),
                   Counter('user.login', 3),
                   token,
                   Counter('user.login', -1),
                   Counter('user.logout', 1),)
        queue_ = Queue()
        destination = StubDestination()
        destination.expected_count = expected_flushed_metrics_count
        processor = QueueProcessor(queue_)
        processor.flush_interval = 2
        processor.stop_process_token = token
        processor.set_destinations([destination])
        process_thread = Thread(target=processor.process)
        process_thread.start()
        processor.wait_until_processing(5)
        for metric in metrics:
            if metric is token:
                sleep(processor.flush_interval)  # make sure one flush happened before token
                request = metric
            else:
                request = metric.to_request()
            queue_.put(request)
        # make sure the processor has process the queue
        processor.wait_until_shutdown(5)
        self.assertFalse(processor.is_processing())
        destination.wait_until_expected_count_items(10)
        self.assertEqual(expected_flushed_metrics_count,
                         len(destination.metrics))
        self.assertEqual(('user.login', 4), destination.metrics[0][:2])
        self.assertEqual(('username', 1), destination.metrics[1][:2])

    def test_continues_processing_after_reload(self):
        metrics = (Counter('user.login', 1), Set('username', 'navdoon'),
                   Counter('user.login', 3))
        queue_ = Queue()
        destination = StubDestination()
        destination.expected_count = 1

        processor = QueueProcessor(queue_)
        processor.flush_interval = 1
        processor.set_destinations([destination])
        process_thread = Thread(target=processor.process)
        process_thread.start()
        processor.wait_until_processing(5)

        expected_flushed_metrics2 = 2
        destination2 = StubDestination()
        destination2.expected_count = expected_flushed_metrics2
        processor.set_destinations([destination2])

        for metric in metrics:
            queue_.put(metric.to_request())

        destination.wait_until_expected_count_items(5)
        processor.shutdown()
        process_thread.join(5)
        self.assertFalse(processor.is_processing())
        self.assertGreaterEqual(len(destination.metrics), 1)
        self.assertLessEqual(queue_.qsize(), 2)

        for metric in metrics:
            queue_.put(metric.to_request())

        self.assertGreaterEqual(queue_.qsize(), len(metrics))
        resume_process_thread = Thread(target=processor.process)
        resume_process_thread.start()
        processor.wait_until_processing(5)
        self.assertTrue(processor.is_processing())
        self.assertEqual(processor.get_destinations(), [destination2])

        destination2.wait_until_expected_count_items(5)
        processor.shutdown()
        resume_process_thread.join(5)
        self.assertGreaterEqual(len(destination2.metrics), expected_flushed_metrics2)

    def test_queue_can_only_change_when_not_processing(self):
        processor = QueueProcessor(Queue())
        orig_queue = processor.queue
        process_thread = Thread(target=processor.process)
        process_thread.start()
        processor.wait_until_processing(5)

        def set_queue(new_queue):
            processor.queue = new_queue

        new_queue = Queue()
        self.assertRaises(Exception, set_queue, new_queue)
        self.assertEqual(orig_queue, processor.queue)

        processor.shutdown()
        processor.wait_until_shutdown(5)

        processor.queue = new_queue
        self.assertEqual(new_queue, processor.queue)

    def test_process_timers(self):
        start_timestamp = time()
        expected_flushed_metrics_count = 2 + 5  # each timer has 5 separate metrics
        metrics = (Counter('user.jump', 2),
                   Set('username', 'navdoon'),
                   Timer('db.query', 300),
                   Set('username', 'navdoon2'),
                   Counter('user.jump', -1),
                   Timer('db.query', 309),
                   Timer('db.query', 303)
                   )
        queue_ = Queue()
        destination = StubDestination()
        destination.expected_count = expected_flushed_metrics_count
        processor = QueueProcessor(queue_)
        processor.set_destinations([destination])
        process_thread = Thread(target=processor.process)
        process_thread.start()
        processor.wait_until_processing(5)
        for metric in metrics:
            queue_.put(metric.to_request())
        destination.wait_until_expected_count_items(5)
        processor.shutdown()
        processor.wait_until_shutdown(5)
        self.assertEqual(expected_flushed_metrics_count,
                         len(destination.metrics))

        metrics_dict = dict()
        for (name, value, timestamp) in destination.metrics:
            metrics_dict[name] = value
            self.assertGreaterEqual(timestamp, start_timestamp)

        self.assertEqual(metrics_dict['user.jump'], 1)
        self.assertEqual(metrics_dict['username'], 2)
        self.assertEqual(metrics_dict['db.query.count'], 3)
        self.assertEqual(metrics_dict['db.query.max'], 309)
        self.assertEqual(metrics_dict['db.query.min'], 300)
        self.assertEqual(metrics_dict['db.query.mean'], 304)
        self.assertEqual(metrics_dict['db.query.median'], 303)


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
        expected = {"users": {"me", "you"},
                    "say.what?": {"nothing", "ok"}}
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

    def test_timers_data(self):
        shelf = StatsShelf()
        self.assertEqual(dict(), shelf.timers_data())

        shelf.add(Timer("query.user", 3.223))
        shelf.add(Timer("query.user", 4.12))
        shelf.add(Timer("api.auth", 9.78))
        shelf.add(Timer("api.auth", 8.45))

        expected = {"query.user": [3.223, 4.12], "api.auth": [9.78, 8.45]}
        self.assertEqual(expected, shelf.timers_data())

    def test_timers(self):
        shelf = StatsShelf()
        self.assertEqual(dict(), shelf.timers())

        shelf.add(Timer("query.user", 2.9))
        shelf.add(Timer("query.user", 3))
        shelf.add(Timer("query.user", 4.1))
        shelf.add(Timer("api.auth", 8))
        shelf.add(Timer("api.auth", 7.96))
        shelf.add(Timer("cache.clear", 1.56))

        expected = {
            "query.user": dict(count=3, min=2.9, max=4.1, mean=3.3333333333333335, median=3),
            "api.auth": dict(count=2, min=7.96, max=8, mean=7.98, median=7.98),
            "cache.clear": dict(count=1, min=1.56, max=1.56, mean=1.56, median=1.56),
        }
        self.assertEqual(expected, shelf.timers())

    def test_clear_all_metrics(self):
        shelf = StatsShelf()

        shelf.add(Set("users", "me"))
        shelf.add(Counter("mymetric", 3))
        shelf.add(Timer("query", 4.12))
        shelf.add(Gauge("cpu%", 38))

        shelf.clear()

        self.assertEqual(dict(), shelf.counters())
        self.assertEqual(dict(), shelf.sets())
        self.assertEqual(dict(), shelf.timers_data())
        self.assertEqual(dict(), shelf.gauges())


if __name__ == '__main__':
    unittest.main()
import unittest
import logging
import sys
from threading import Thread, Event
from statsdmetrics import Counter, Set, Gauge, GaugeDelta
from navdoon.pystdlib.queue import Queue
from navdoon.processor import QueueProcessor, StatsShelf
from navdoon.utils import LoggerMixIn
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
        self.log_signature = 'test.destination'
        self.metrics = []
        self.expected_count = expected_count
        self.flushed_expected_count = Event()

    def flush(self, metrics):
        self._log_debug("{} metrics flushed".format(len(metrics)))
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
        self.assertEquals(103, processor.flush_interval)
        processor.flush_interval = 0.58
        self.assertEquals(0.58, processor.flush_interval)

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

    def test_add_destination_fails_when_flush_method_is_missing(self):
        invalid_destinations = ["not callable", DestinationWithoutFlushMethod]
        processor = QueueProcessor(Queue())
        for dest in invalid_destinations:
            self.assertRaises(ValueError, processor.add_destination, dest)

    def test_add_destinations(self):
        destination = StubDestination()
        destination2 = StubDestination()
        queue_ = Queue()
        processor = QueueProcessor(queue_)

        processor.add_destination(destination)
        processor.add_destination(destination)
        self.assertEqual([destination], processor._destinations)

        processor.add_destination(destination2)
        self.assertEqual([destination, destination2], processor._destinations)

    def test_set_destination_fails_on_invalid_destination(self):
        processor = QueueProcessor(Queue())
        self.assertRaises(ValueError, processor.set_destinations,
                          "not a destination")

    def test_set_destinations(self):
        processor = QueueProcessor(Queue())
        destinations = [StubDestination()]
        processor.set_destinations(destinations)
        self.assertEqual(destinations, processor._destinations)

    def test_clear_destinations(self):
        destination = StubDestination()
        queue_ = Queue()
        processor = QueueProcessor(queue_)
        processor.add_destination(destination)
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
                   Counter('user.jump', -1), )
        queue_ = Queue()
        destination = StubDestination()
        destination.expected_count = expected_flushed_metrics_count
        processor = QueueProcessor(queue_)
        processor.add_destination(destination)
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
                   Counter('user.logout', 1), )
        queue_ = Queue()
        destination = StubDestination()
        destination.expected_count = expected_flushed_metrics_count
        processor = QueueProcessor(queue_)
        processor.flush_interval = 2
        processor.stop_process_token = token
        processor.add_destination(destination)
        process_thread = Thread(target=processor.process)
        process_thread.start()
        processor.wait_until_processing(5)
        for metric in metrics:
            request = token if metric is token else metric.to_request()
            queue_.put(request)
        # make sure the processor has process the queue
        processor.wait_until_shutdown(5)
        # make sure at least a flush has occurred so we can test the destination
        processor.flush()
        self.assertFalse(processor.is_processing())
        destination.wait_until_expected_count_items(10)
        self.assertEqual(expected_flushed_metrics_count,
                         len(destination.metrics))
        self.assertEqual(('user.login', 4), destination.metrics[0][:2])
        self.assertEqual(('username', 1), destination.metrics[1][:2])

    def test_process_can_resume_after_shutdown_called(self):
        metrics = (Counter('user.login', 1), Set('username', 'navdoon'),
                   Counter('user.login', 3))
        queue_ = Queue()
        destination = StubDestination()
        destination.expected_count = 1

        processor = QueueProcessor(queue_)
        processor.flush_interval = 1
        processor.add_destination(destination)
        process_thread = Thread(target=processor.process)
        process_thread.start()
        processor.wait_until_processing(5)

        for metric in metrics:
            queue_.put(metric.to_request())

        destination.wait_until_expected_count_items(5)
        processor.shutdown()
        process_thread.join(5)
        self.assertGreaterEqual(len(destination.metrics), 1)
        self.assertLessEqual(queue_.qsize(), 2)
        processor.clear_destinations()

        for metric in metrics:
            queue_.put(metric.to_request())

        expected_flushed_metrics = len(metrics)
        destination2 = StubDestination()
        destination2.expected_count = expected_flushed_metrics
        processor.add_destination(destination2)

        resume_process_thread = Thread(target=processor.process)
        resume_process_thread.start()
        processor.wait_until_processing(5)

        destination2.wait_until_expected_count_items(5)
        processor.shutdown()
        resume_process_thread.join(5)
        self.assertGreaterEqual(expected_flushed_metrics,
                                len(destination2.metrics))

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

    def test_clear_all_metrics(self):
        shelf = StatsShelf()

        shelf.add(Set("users", "me"))
        shelf.add(Counter("mymetric", 3))
        shelf.clear()

        self.assertEqual(dict(), shelf.counters())
        self.assertEqual(dict(), shelf.sets())

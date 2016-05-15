"""
navdoon.processor
-----------------
Define queue processor, that will process the actualy Statsd requests
queued by the collectors.
"""

from time import time
from threading import Event, RLock, Thread
from navdoon.pystdlib.queue import Empty
from navdoon.utils import LoggerMixIn, DataSeries
from statsdmetrics import (Counter, Gauge, GaugeDelta, Set, Timer,
                           parse_metric_from_request)


def validate_destinations(destinations):
    for destination in destinations:
        if not hasattr(destination,
                       'flush') or not callable(destination.flush):
            raise ValueError("Invalid destination for queue processor."
                             "Destination should have a flush() method")


def validate_queue(queue_):
    if not callable(getattr(queue_, 'get', None)):
        raise ValueError("Invalid queue for queue processor."
                         "queue should have a get() method")


class QueueProcessor(LoggerMixIn):
    """Process Statsd requests queued by the collectors"""

    default_stop_process_token = None

    def __init__(self, queue_):
        validate_queue(queue_)
        super(QueueProcessor, self).__init__()
        self.log_signature = 'queue.processor '
        self.stop_process_token = self.__class__.default_stop_process_token
        self._flush_interval = 1
        self._queue = queue_
        self._should_stop_processing = Event()
        self._processing = Event()
        self._shutdown = Event()
        self._processing_lock = RLock()
        self._flush_lock = RLock()
        self._shelf = StatsShelf()
        self._destinations = []
        self._last_flush_timestamp = None

    @property
    def queue(self):
        return self._queue

    @queue.setter
    def queue(self, queue_):
        validate_queue(queue_)
        if self.is_processing():
            raise Exception(
                "Can not change queue processor's queue while processing")
        self._queue = queue_

    @property
    def flush_interval(self):
        return self._flush_interval

    @flush_interval.setter
    def flush_interval(self, interval):
        interval_float = float(interval)
        if interval_float <= 0:
            raise ValueError(
                "Invalid flush interval. Interval should be a positive number")
        self._flush_interval = interval

    def add_destination(self, destination):
        validate_destinations([destination])
        if destination not in self._destinations:
            self._destinations.append(destination)
        return self

    def clear_destinations(self):
        self._destinations = []
        return self

    def set_destinations(self, destinations):
        validate_destinations(destinations)
        self._destinations = destinations
        return self

    def is_processing(self):
        return self._processing.is_set()

    def wait_until_processing(self, timeout=None):
        return self._processing.wait(timeout)

    def process(self):
        self._log_debug("waiting for process lock ...")
        with self._processing_lock:
            self._log_debug("process lock acquired")
            if self._last_flush_timestamp is None:
                self._last_flush_timestamp = time()
            self._log("processing the queue ...")

            queue_ = self._queue
            queue_empty_error = Empty
            process = self._process_request
            stop = self._should_stop_processing
            log_debug = self._log_debug
            log = self._log
            flush = self.flush

            self._shutdown.clear()
            self._processing.set()

            try:
                while True:
                    if stop.is_set():
                        log_debug("instructed to shutdown")
                        break
                    try:
                        data = queue_.get(timeout=1)
                        queue_has_data = True
                    except queue_empty_error:
                        queue_has_data = False

                    if time(
                    ) - self._last_flush_timestamp >= self._flush_interval:
                        flush()

                    if queue_has_data:
                        if data == self.stop_process_token:
                            log("got stop process token in queue")
                            break
                        elif data:
                            process(data)
            finally:
                log("stopped processing the queue")
                self._processing.clear()
                self._shutdown.set()

    def flush(self):
        self._log_debug("waiting for flushing lock ...")
        with self._flush_lock:
            self._log_debug("flushing lock acquired")
            now = time()
            metrics = self._get_metrics_and_clear_shelf(now)
            self._log("flushing '{}' metrics to '{}' destinations".format(
                len(metrics), len(self._destinations)))
            for destination in self._destinations:
                try:
                    call_destination_thread = Thread(target=destination.flush,
                                                     args=[metrics])
                    call_destination_thread.daemon = True
                    call_destination_thread.start()
                except Exception as exp:
                    self._log_error(
                        "error occurred while flushing to destination: "
                        "{}".format(exp))
            self._last_flush_timestamp = now

    def shutdown(self):
        self._log("shutting down ...")
        self._should_stop_processing.set()

    def wait_until_shutdown(self, timeout=None):
        return self._shutdown.wait(timeout)

    def _process_request(self, request):
        self._log_debug("processing metrics: {}".format(str(request)))
        lines = [line.strip() for line in request.split("\n")]
        stop = self._should_stop_processing
        for line in lines:
            if stop.is_set():
                break
            try:
                metric = parse_metric_from_request(line)
            except ValueError as parse_error:
                self._log_error(
                    "failed to parse statsd metrics from '{}': {}".format(
                        line, parse_error))
                continue
            self._shelf.add(metric)

    def _get_metrics_and_clear_shelf(self, timestamp):
        shelf = self._shelf
        counters = shelf.counters()
        gauges = shelf.gauges()
        sets = shelf.sets()
        timers = shelf.timers()
        shelf.clear()

        metrics = []
        for name, value in counters.items():
            metrics.append((name, value, timestamp))

        for name, value in gauges.items():
            metrics.append((name, value, timestamp))

        for name, value in sets.items():
            metrics.append((name, len(value), timestamp))

        for name, timer_stats in timers.items():
            for statistic, value in timer_stats.items():
                metrics.append(
                    (
                        "{}.{}".format(name, statistic),
                        value,
                        timestamp
                    )
                )

        return metrics


class StatsShelf(object):
    """A container that will aggregate and accumulate metrics"""

    _metric_add_methods = {Counter.__name__: '_add_counter',
                           Set.__name__: '_add_set',
                           Gauge.__name__: '_add_gauge',
                           GaugeDelta.__name__: '_add_gauge_delta',
                           Timer.__name__: '_add_timer'}

    def __init__(self):
        self._lock = RLock()
        self._counters = dict()
        self._timers = dict()
        self._sets = dict()
        self._gauges = dict()

    def add(self, metric):
        method_name = self.__class__._metric_add_methods.get(
            metric.__class__.__name__)
        if not method_name:
            raise ValueError(
                "Can not add metric to shelf. No method is defined to "
                "handle {}".format(metric.__class__.__name__))
        with self._lock:
            getattr(self, method_name)(metric)

    def counters(self):
        return self._counters.copy()

    def sets(self):
        return self._sets.copy()

    def gauges(self):
        return self._gauges.copy()

    def timers_data(self):
        return self._timers.copy()

    def timers(self):
        result = dict()
        for name, timers in self._timers.items():
            series = DataSeries(timers)
            result[name] = dict(count=series.count(), min=series.min(), max=series.max(),
                                mean=series.mean(), median=series.median())
        return result

    def clear(self):
        self._counters = dict()
        self._timers = dict()
        self._sets = dict()
        self._gauges = dict()

    def _add_counter(self, counter):
        counters = self._counters
        name = counter.name
        if name not in counters:
            counters[name] = 0
        counters[name] += counter.count / counter.sample_rate

    def _add_set(self, metric):
        self._sets.setdefault(metric.name, set()).add(metric.value)

    def _add_gauge(self, metric):
        self._gauges[metric.name] = metric.value

    def _add_gauge_delta(self, metric):
        gauges = self._gauges
        name = metric.name
        if name not in gauges:
            gauges[name] = metric.delta
        else:
            gauges[name] += metric.delta

    def _add_timer(self, metric):
        self._timers.setdefault(metric.name, list()).append(
            metric.milliseconds)
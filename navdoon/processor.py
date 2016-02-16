from time import time
from threading import Event, RLock, Thread
try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty
from navdoon.utils import LoggerMixIn
from statsdmetrics import (Counter, Gauge, GaugeDelta, Set, Timer,
                           parse_metric_from_request, normalize_metric_name)


class QueueProcessor(LoggerMixIn):
    default_stop_process_token = None

    def __init__(self, queue):
        LoggerMixIn.__init__(self)
        self.stop_process_token = self.__class__.default_stop_process_token
        self.flush_interval = 1
        self._queue = queue
        self._should_stop_processing = Event()
        self._processing = Event()
        self._shutdown = Event()
        self._processing_lock = RLock()
        self._flush_lock = RLock()
        self._shelf = StatsShelf()
        self._destinations = []
        self._last_flush_timestamp = 0

    def add_destination(self, destination):
        if not hasattr(destination, 'flush') or not callable(destination.flush):
            raise ValueError("Invalid destination for queue processor." \
                    "Destination should have a flush() method")
        if destination not in self._destinations:
            self._destinations.append(destination)
        return self

    def clear_destinations(self):
        self._destinations = []
        return self

    def is_processing(self):
        return self._processing.is_set()

    def wait_until_processing(self, timeout=None):
        return self._processing.wait(timeout)

    def process(self):
        self._log_debug("queue processor waiting for lock ...")
        with self._processing_lock:
            self._log_debug("queue process lock acquired")
            self._last_flush_timestamp = time()
            self._log("processing the queue ...")

            queue_ = self._queue
            QueueEmptyError = Empty
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
                        log_debug("queue processor instructed to stop")
                        break
                    try:
                        data = queue_.get(timeout=1)
                    except QueueEmptyError:
                        data = None

                    if time() - self._last_flush_timestamp >= self.flush_interval:
                        flush()

                    if data == self.stop_process_token:
                        log("got stop process token in queue")
                        break
                    if data:
                        process(data)
            finally:
                log("stopped processing the queue")
                self._processing.clear()
                self._shutdown.set()

    def flush(self):
        self._log_debug("queue processor waiting for flushing lock ...")
        with self._flush_lock:
            self._log_debug("queue processor flushing lock acquired")
            now = time()
            metrics = self._get_metrics_and_clear_shelf(now)
            self._log("flushing '{}' metrics to '{}' destinations".format(
                len(metrics), len(self._destinations)))
            for destination in self._destinations:
                try:
                    call_destination_thread = Thread(target=destination.flush, args=[metrics])
                    call_destination_thread.daemon = True
                    call_destination_thread.start()
                except Exception as exp:
                    self._log_error("error occurred while flushing to destination: {}".format(exp))
            self._last_flush_timestamp = now

    def shutdown(self):
        self._log("shutting down the queue processor ...")
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
            except ValueError as e:
                self._log_error(
                    "failed to parse statsd metrics from '{}'".format(line))
                continue
            self._shelf.add(metric)

    def _get_metrics_and_clear_shelf(self, timestamp):
        shelf = self._shelf
        counters = shelf.counters()
        gauges = shelf.gauges()
        sets = shelf.sets()
        shelf.clear()

        metrics = []
        for name, value in counters.items():
            metrics.append((name, value, timestamp))

        for name, value in gauges.items():
            metrics.append((name, value, timestamp))

        for name, value in sets.items():
            metrics.append((name, len(value), timestamp))

        return metrics


class StatsShelf(object):

    _metric_add_methods = {Counter.__name__: '_add_counter',
                           Set.__name__: '_add_set',
                           Gauge.__name__: '_add_gauge',
                           GaugeDelta.__name__: '_add_gauge_delta'}

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
                "Can not add metric to shelf. No method is defined to handle {}".format(
                    metric.__class__.__name__))
        with self._lock:
            getattr(self, method_name)(metric)

    def counters(self):
        return self._counters.copy()

    def sets(self):
        return self._sets.copy()

    def gauges(self):
        return self._gauges.copy()

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

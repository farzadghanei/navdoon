from copy import deepcopy
from threading import Event
from navdoon.utils import LoggerMixIn
from statsdmetrics import (Counter, Gauge, GaugeDelta, Set, Timer, parse_metric_from_request, normalize_metric_name)

class QueueProcessor(LoggerMixIn):
    default_stop_process_token = None

    def __init__(self, queue):
        LoggerMixIn.__init__(self)
        self._queue = queue
        self.stop_process_token = self.__class__.default_stop_process_token
        self._should_stop_processing = Event()
        self._processing = Event()
        self._shelf = StatsShelf()

    def is_processing(self):
        return self._processing.is_set()

    def wait_until_processing(self, timeout=None):
        return self._processing.wait(timeout)

    def process(self):
        stop = self._should_stop_processing
        self._log("processing the queue")
        self._processing.set()
        try:
            while stop.is_set():
                data = self._queue.get()
                if data == self.stop_process_token:
                    self._log_debug("got stop process token in queue")
                    break
                if not data:
                    self._log_debug("skipping empty data in queue")
                    continue
                self._process_request(data)
        finally:
            self._log("stopped processing the queue")
            self._processing.clear()

    def _process_request(self, request):
        lines = [line.strip() for line in request.split("\n")]
        stop = self._should_stop_processing()
        for line in lines:
            if stop.is_set():
                break
            try:
                metric = parse_metric_from_request(line)
            except ValueError as e:
                self._log_error("failed to parse statsd metrics from '{}'".format(line))
                continue
            self.shelf.add(metric)


class StatsShelf(object):

    _metric_add_methods = {
        Counter.__name__: '_add_counter'
    }

    def __init__(self):
        self._counters = dict()
        self._timers = dict()
        self._sets = dict()
        self._gauges = dict()

    def add(self, metric):
        method_name = self.__class__._metric_add_methods.get(metric.__class__.__name__)
        if not method_name:
            raise ValueError("Can not add metric to shelf. No method is defined to handle {}".format(metric.__class__))
        getattr(self, method_name)(metric)

    def counters(self):
        return self._counters.copy()

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
        counters[name] += round(counter.count / counter.sample_rate)

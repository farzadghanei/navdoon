from typing import AnyStr, Union, Dict, List, Tuple, Set as SetType
import multiprocessing
from statsdmetrics import (Counter, Gauge, GaugeDelta, Set, Timer)
from navdoon.pystdlib import queue
from navdoon.utils import LoggerMixIn
from navdoon.destination import AbstractDestination

Boolean = Union[True, False]
StatsMetricType = Union[Counter, Gauge, GaugeDelta, Set, Timer]
Queue = Union[queue.Queue, multiprocessing.Queue]
Metrics = List[Tuple(AnyStr, float, float)]

class QueueProcessor(LoggerMixIn):
    def __init__(self, queue_: Queue) -> None: ...
    def add_destination(self, destination: AbstractDestination) -> "QueueProcessor": ...
    def clear_destinations(self) -> "QueueProcessor" : ...
    def is_processing(self) -> Boolean: ...
    def wait_until_processing(self, timeout: float): ...
    def process(self) -> None: ...
    def flush(self) -> None: ...
    def shutdown(self) -> None: ...
    def wait_until_shutdown(self, timeout: float) -> None: ...
    def _process_request(self, request: str) -> None: ...
    def _get_metrics_and_clear_shelf(self, timestamp: float) -> Metrics: ...


class StatsShelf(object):
    def __init__(self) -> None: ...
    def add(self, metric: StatsMetricType) -> None: ...
    def counters(self) -> Dict[str, float]: ...
    def sets(self) -> Dict[str, SetType]: ...
    def gauges(self) -> Dict[str, float]: ...
    def clear(self) -> None: ...
    def _add_counter(self, counter: Counter) -> None: ...
    def _add_set(self, metric: Set) -> None: ...
    def _add_gauge(self, metric: Gauge) -> None: ...
    def _add_gauge_delta(self, metric: GaugeDelta) -> None: ...

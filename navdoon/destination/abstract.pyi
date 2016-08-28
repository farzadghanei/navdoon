from typing import List, Tuple, AnyStr
from abc import abstractmethod

Metrics = List[Tuple[AnyStr, float, float]]


class AbstractDestination(object):
    @abstractmethod
    def flush(self, metrics: Metrics) -> None: ...

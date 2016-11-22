"""
navdoon.destination.abstract
----------------------------
Define an abstract base class for destinations
"""

from abc import abstractmethod, ABCMeta
from navdoon.pystdlib.typing import List, Tuple, AnyStr


class AbstractDestination(object):
    """Abstract base class for destinations"""

    __metaclass__ = ABCMeta

    @abstractmethod
    def flush(self, metrics):
        # type: (List[Tuple[AnyStr, float, float]]) -> None
        """Flush the metrics"""
        raise NotImplementedError

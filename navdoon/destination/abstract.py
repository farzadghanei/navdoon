"""
navdoon.destination.abstract
----------------------------
Define an abstract base class for destinations
"""

from abc import abstractmethod, ABCMeta


class AbstractDestination(object):
    """Abstract base class for destinations"""

    __metaclass__ = ABCMeta

    @abstractmethod
    def flush(self, metrics):
        """Flush the metrics"""
        raise NotImplementedError

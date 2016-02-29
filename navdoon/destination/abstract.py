"""
navdoon.destination.abstract
----------------------------
Define an abstract base class for destinations
"""

from abc import abstractmethod


class AbstractDestination(object):
    """Abstract base class for destinations"""

    @abstractmethod
    def flush(self, metrics):
        """Flush the metrics"""
        raise NotImplementedError

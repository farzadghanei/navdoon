"""
navdoon.destination
-------------------
Where the data received from Statsd will be
flushed to
"""
from abc import abstractmethod
from navdoon.destination.graphite import Graphite
from navdoon.destination.stream import Stream, Stdout


class AbstractDestination(object):
    @abstractmethod
    def flush(self, metrics):
        raise NotImplemented

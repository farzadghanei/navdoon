"""
navdoon.destination
-------------------
Where the data received from Statsd will be
flushed to
"""
from navdoon.destination.abstract import AbstractDestination
from navdoon.destination.graphite import Graphite
from navdoon.destination.stream import Stream, Stdout, CsvStream, CsvStdout

__all__ = ['Graphite', 'Stream', 'Stdout', 'CsvStream', 'CsvStdout']

"""
navdoon.destination
-------------------
Where the data received from Statsd will be
flushed to
"""

from navdoon.destination.graphite import Graphite
from navdoon.destination.stream import Stream, Stdout
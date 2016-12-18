"""
navdoon.destination.file
------------------------
Define destinations to flush metrics to files
"""

from navdoon.destination.stream import Stream, CsvStream
from navdoon.pystdlib.typing import Any


class TextFile(Stream):
    """Destination to flush metrics to a file"""

    def __init__(self, name):
        # type: (str) -> None
        self._name = None  # type: str
        self.name = name
        file_handle = open(name, 'at')
        Stream.__init__(self, file_handle)

    def __del__(self):
        self.stream.close()

    @property
    def name(self):
        # type: () -> str
        return self._name

    @name.setter
    def name(self, name):
        # type: (str) -> None
        self._name = name

    def __eq__(self, other):
        # type: (Any) -> bool
        return self._name == other.name and self.pattern == other.pattern


class CsvFile(TextFile):
    """Destination to flush metrics to a CSV file"""

    def __init__(self, name):
        # type: (str) -> None
        TextFile.__init__(self, name)
        self.pattern = '"{name}","{value}","{timestamp}"'  # type: str
        self.append = "\r\n"  # type: str

"""
navdoon.destination.stream
--------------------------
Define destinations to flush metrics to streams
"""

import sys
from time import time
from navdoon.destination.abstract import AbstractDestination
from navdoon.pystdlib.typing import List, Tuple, Any, AnyStr, IO


class Stream(AbstractDestination):
    """Destination to flush metrics to stream"""

    def __init__(self, file_handle):
        # type: (IO) -> None
        self._file = None  # type: IO
        self.pattern = "{name} {value} {timestamp}"  # type: str
        self.append = "\n"  # type: str
        self.stream = file_handle

    @property
    def stream(self):
        # type: () -> IO
        return self._file

    @stream.setter
    def stream(self, file_):
        # type: (IO) -> None
        if not callable(getattr(file_, 'write', None)):
            raise ValueError("Destination stream should be file like object")
        self._file = file_

    def create_output_from_metrics(self, metrics):
        # type: (List[Tuple[AnyStr, float, float]]) -> List[str]
        """Creates the output to be flushed, from the metrics"""
        requests = []
        for metric in metrics:
            name, value = metric[:2]
            timestamp = len(metric) > 2 and metric[2] or time()
            requests.append(self.pattern.format(name=name,
                                                value=value,
                                                timestamp=timestamp))
        return requests

    def flush(self, metrics):
        # type: (List[Tuple[AnyStr, float, float]]) -> None
        """Flush metrics to the stream"""
        lines = self.create_output_from_metrics(metrics)
        self._write_lines(lines)

    def _write_lines(self, lines):
        # type: (List[AnyStr]) -> None
        write = self._file.write
        append_ = self.append
        for line in lines:
            write(line + append_)
        self._file.flush()

    def __eq__(self, other):
        # type: (Any) -> bool
        return self.stream == other.stream and self.pattern == other.pattern


class Stdout(Stream):
    """Destination to flush metrics to standard output"""

    def __init__(self):
        super(Stdout, self).__init__(sys.stdout)


class CsvStream(Stream):
    """Destination to flush metrics to a stream in CSV format"""
    def __init__(self, file_handle):
        Stream.__init__(self, file_handle)
        self.pattern = '"{name}","{value}","{timestamp}"'  # type: str
        self.append = "\r\n"  # type: str


class CsvStdout(CsvStream):
    """Destination to flush metrics to standard output in CSV format"""
    def __init__(self):
        CsvStream.__init__(self, sys.stdout)
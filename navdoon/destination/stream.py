"""
navdoon.destination.stream
--------------------------
Define destinations to flush metrics to streams
"""

import sys
from time import time
from navdoon.destination.abstract import AbstractDestination


class Stream(AbstractDestination):
    """Destination to flush metrics to stream"""

    def __init__(self, file_handle):
        self._file = None
        self.pattern = "{name} {value} {timestamp}"
        self.append = "\n"
        self.stream = file_handle

    @property
    def stream(self):
        return self._file

    @stream.setter
    def stream(self, file_):
        if not callable(getattr(file_, 'write', None)):
            raise ValueError("Destination stream should be file like object")
        self._file = file_

    def create_output_from_metrics(self, metrics):
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
        """Flush metrics to the stream"""
        lines = self.create_output_from_metrics(metrics)
        self._write_lines(lines)

    def _write_lines(self, lines):
        write = self._file.write
        append_ = self.append
        for line in lines:
            write(line + append_)
        self._file.flush()

    def __eq__(self, other):
        return self.stream == other.stream


class Stdout(Stream):
    """Destination to flush metrics to standard output"""

    def __init__(self):
        super(Stdout, self).__init__(sys.stdout)

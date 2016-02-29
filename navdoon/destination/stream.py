import sys
from time import time
from navdoon.destination.abstract import AbstractDestination


class Stream(AbstractDestination):
    def __init__(self, file_handle):
        self._file = file_handle
        self.pattern = "{name} {value} {timestamp}"
        self.append = "\n"

    def create_output_from_metrics(self, metrics):
        requests = []
        for metric in metrics:
            name, value = metric[:2]
            timestamp = len(metric) > 2 and metric[2] or time()
            requests.append(self.pattern.format(name=name,
                                                value=value,
                                                timestamp=timestamp))
        return requests

    def flush(self, metrics):
        lines = self.create_output_from_metrics(metrics)
        self._write_lines(lines)

    def _write_lines(self, lines):
        write = self._file.write
        append_ = self.append
        for line in lines:
            write(line + append_)
        self._file.flush()


class Stdout(Stream):
    def __init__(self):
        super(Stdout, self).__init__(sys.stdout)

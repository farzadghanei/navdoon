"""
navdoon.destination.graphite
----------------------------
A destination to flush metrics to Graphite
"""

from time import time
from navdoon.utils.common import TCPClient
from navdoon.destination.abstract import AbstractDestination
from navdoon.pystdlib.typing import List, Tuple, Any, AnyStr


class Graphite(TCPClient, AbstractDestination):
    """Flush metrics to Graphtie over a TCP connection"""

    def __init__(self, host='localhost', port=2003):
        # type: (str, int) -> None
        super(Graphite, self).__init__(host, port)

    def __del__(self):
        self.disconnect()

    @staticmethod
    def create_request_from_metrics(metrics):
        # type: (List[Tuple[AnyStr, float, float]]) -> List[str]
        """Creates Graphite protocol lines from metrics"""
        requests = []
        for metric in metrics:
            name, value = metric[:2]
            timestamp = len(metric) > 2 and metric[2] or time()
            requests.append("{} {} {}".format(name, value, timestamp))
        return requests

    def flush(self, metrics):
        # type: (List[Tuple[AnyStr, float, float]]) -> None
        """Flush metrics to Graphite"""
        lines = self.create_request_from_metrics(metrics)
        self._send_lines(lines)

    def _send_lines(self, lines):
        # type: (List[AnyStr]) -> None
        num_lines = len(lines)
        data = "\n".join([line.strip() for line in lines]).encode()
        self._log_debug("flushing {} metrics to graphite on {}:{} ...".format(
            num_lines, self.host, self.port))
        self._send_with_lock(data)
        self._log("flushed {} metrics to graphite on {}:{}".format(
            num_lines, self.host, self.port))

    def __eq__(self, other):
        # type: (Any) -> bool
        return self.host == other.host and self.port == other.port and \
                self.max_retry == other.max_retry

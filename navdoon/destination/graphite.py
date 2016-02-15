from navdoon.utils import TCPClient
from time import time


class Graphite(TCPClient):
    def __init__(self, host='localhost', port=2003):
        TCPClient.__init__(self, host, port)

    def __del__(self):
        self.disconnect()

    @staticmethod
    def create_request_from_metrics(metrics):
        requests = []
        for metric in metrics:
            name, value = metric[:2]
            timestamp = len(metric) > 2 and metric[2] or time()
            requests.append("{} {} {}".format(name, value, timestamp))
        return requests

    def flush(self, metrics):
        lines = self.create_request_from_metrics(metrics)
        self._send_lines(lines)

    def _send_lines(self, lines):
        num_lines = len(lines)
        data = "\n".join([line.strip() for line in lines]).encode()
        self._log_debug("flushing %d metrics to graphite on {}:{} ...".format(
            num_lines, self.host, self.port))
        self._send_with_lock(data)
        self._log("flushed %d metrics to graphite on {}:{}".format(
            num_lines, self.host, self.port))

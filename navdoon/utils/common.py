"""
navdoon.utils.common
--------------------
Common utilities and mixin classes
"""

import socket
from os import getpid
from time import sleep
from logging import INFO, DEBUG, ERROR, WARN
from threading import Lock
from navdoon.pystdlib.typing import AnyStr, Sequence


class LoggerMixIn(object):
    """A MixIn class for anything that needs to log messages"""

    def __init__(self):
        self.logger = None  # type: logging.Logger
        self.log_pattern = "{signature}{message}"  # type: str
        self.log_signature = ''  # type: str
        self._pid = getpid()  # type: int

    def _log_debug(self, msg):
        # type: (str) -> None
        self._log(msg, DEBUG)

    def _log_error(self, msg):
        # type: (str) -> None
        self._log(msg, ERROR)

    def _log_warn(self, msg):
        # type: (str) -> None
        self._log(msg, WARN)

    def _log(self, msg, level=INFO):
        # type: (str, int) -> None
        if self.logger:
            self.logger.log(
                level,
                self.log_pattern.format(message=msg,
                                        signature=self.log_signature,
                                        pid=self._pid))


class TCPClient(LoggerMixIn):
    """A generic TCP client with reconnecting feature"""

    def __init__(self, host, port):
        # type: (str, int) -> None
        super(TCPClient, self).__init__()
        self.host = host  # type: str
        self.port = port  # type: int
        self.max_retry = None  # type: int
        self._connection_tries = 0  # type: int
        self._sleep_between_retries = 0.5  # type: float
        self._sock = None  # type: socket.socket
        self._connection_lock = Lock()  # type: Lock
        self._sending_lock = Lock()  # type: Lock

    def connect(self):
        self._connection()
        self._log("connected to {}:{}".format(self.host, self.port))

    def disconnect(self):
        with self._connection_lock:
            self._log_debug("disconnecting from {}:{}".format(self.host,
                                                              self.port))
            if self._sock:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                    self._sock.close()
                except socket.error:
                    pass
            self._sock = None
            self._log("disconnected from {}:{}".format(self.host, self.port))

    def reconnect(self):
        self._log_debug("reconnecting to {}:{}".format(self.host, self.port))
        if self._connection_tries >= self.max_retry:
            raise IOError(
                "Reached maximum connection tries of '{}' to {}:{}".format(
                    self.max_retry, self.host, self.port))
        self.disconnect()
        self.connect()

    def reset_connection_tries(self):
        with self._connection_lock:
            self._connection_tries = 0

    def _send_with_lock(self, data_bytes):
        # type: (bytes) -> None
        data_size = len(data_bytes)
        with self._sending_lock:
            while True:
                self._log_debug("sending {} bytes to {}:{} ...".format(
                    data_size, self.host, self.port))
                sock = self._connection()
                try:
                    sock.sendall(data_bytes)
                    self._log_debug("sent {} bytes to {}:{}".format(
                        data_size, self.host, self.port))
                    break
                except socket.error as err:
                    self._log_error("failed to send data to {}:{}. {}".format(
                        self.host, self.port, err))
                    self.reconnect()

    def _connection(self):
        # type: () -> socket.socket
        with self._connection_lock:
            if not self._sock:
                max_retry = self.max_retry
                while True:
                    self._connection_tries += 1
                    self._log_debug("connecting to {}:{} try {}/{}".format(
                        self.host, self.port, self._connection_tries,
                        max_retry))
                    try:
                        sock = socket.socket(socket.AF_INET,
                                             socket.SOCK_STREAM)
                        sock.connect((self.host, self.port))
                        self._log_debug("connected to {}:{}".format(self.host,
                                                                    self.port))
                        self._sock = sock
                        break
                    except socket.error as err:
                        self._log_error(
                            "failed to connect to {}:{}. {}".format(
                                self.host, self.port, err))
                        sock.close()
                        if max_retry and max_retry <= self._connection_tries:
                            raise IOError(
                                "Reached maximum connection tries of "
                                "'{}' to {}:{}".format(
                                    max_retry, self.host, self.port))
                    sleep(self._sleep_between_retries * self._connection_tries)
        return self._sock


class DataSeries(object):
    def __init__(self, data):
        # type: (Sequence[float]) -> None
        self._count = len(data)  # type: int
        if self._count < 1:
            raise ValueError("Can not create a series from an empty data set")
        self._data = sorted(data)  # type: Sequence[float]

    def count(self):
        # type: () -> int
        return self._count

    def min(self):
        # type: () -> float
        return min(self._data)

    def max(self):
        # type: () -> float
        return max(self._data)

    def mean(self):
        # type: () -> float
        return sum(self._data) / self._count

    def median(self):
        # type: () -> float
        count = self._count
        if count == 2:
            return self.mean()
        last_index = count - 1
        middle_index = count // 2
        if middle_index < last_index and count % 2 == 0:
            return (self._data[middle_index] + self._data[middle_index + 1]) / 2
        else:
            return self._data[middle_index]

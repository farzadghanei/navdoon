import socket
from os import getpid
from logging import INFO, DEBUG, ERROR
from threading import Lock
from time import sleep


class LoggerMixIn(object):
    def __init__(self):
        self.logger = None
        self.log_pattern = "[{pid}] {message}"
        self._pid = getpid()

    def _log_debug(self, msg):
        self._log(msg, DEBUG)

    def _log_error(self, msg):
        self._log(msg, ERROR)

    def _log(self, msg, level=INFO):
        if self.logger:
            self.logger.log(level,
                            self.log_pattern.format(message=msg,
                                                    pid=self._pid))


class TCPClient(LoggerMixIn):
    def __init__(self, host, port):
        LoggerMixIn.__init__(self)
        self.host = host
        self.port = port
        self.max_retry = None
        self._connection_tries = 0
        self._sleep_between_retries = 0.5
        self._sock = None
        self._connection_lock = Lock()
        self._sending_lock = Lock()

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
                    max_retry, self.host, self.port))
        self.disconnect()
        self.connect()

    def reset_connection_tries(self):
        with self._connection_lock:
            self._connection_tries = 0

    def _send_with_lock(self, data_bytes):
        data_size = len(data_bytes)
        with self._sending_lock:
            while True:
                self._log_debug("sending {} bytes to {}:{} ...".format(
                    data_size, self.host, self.port))
                sock = self._connection()
                try:
                    sock.sendall(data)
                    self._log_debug("sent {} bytes to {}:{}".format(
                        data_size, self.host, self.port))
                    break
                except socket.error:
                    self._log_error("failed to send data to {}:{}. {}".format(
                        self.host, self.port, err))
                    self.reconnect()

    def _connection(self):
        with self._connection_lock:
            if not self._sock:
                max_retry = self.max_retry
                while True:
                    self._connection_tries += 1
                    try:
                        self._log_debug("connecting to {}:{} try {}/{}".format(
                            self.host, self.port, self._connection_tries,
                            max_retry))
                        sock = socket.socket(socket.AF_INET,
                                             socket.SOCK_STRAEM)
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
                                "Reached maximum connection tries of '{}' to {}:{}".format(
                                    max_retry, self.host, self.port))
                    sleep(self._sleep_between_retries * self._connection_tries)
        return self._sock

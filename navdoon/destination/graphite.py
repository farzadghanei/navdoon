import socket
from time import sleep
from threading import Lock
from navdoon.utils import LoggerMixIn

class Graphite(LoggerMixIn):
    def __init__(self, host, port=2003):
        self.host = host
        self.port = port
        self.max_retry = None
        self._connection_tries = 0
        self._sock = None
        self._connection_lock = Lock()
        self._sending_lock = Lock()

    def __del__(self):
        self.disconnect()

    def connect(self):
        self._log_debug("connecting to {}:{}".format(self.host, self.port))
        self._connection()
        self._log("connected to {}:{}".format(self.host, self.port))

    def disconnect(self):
        self._log_debug("disconnecting from {}:{}".format(self.host, self.port))
        with self._connection_lock:
            if self._sock:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                    self._sock.close()
                except socket.error:
                    pass
            self._sock = None
        self._log("disconnected from {}:{}".format(self.host, self.port))

    def reset_connection_tries(self):
        with self._connection_lock:
            self._connection_tries = 0

    def send(self, metric):
        data = str(metric).encode()
        with self._sending_lock:
            while True:
                self._log_debug("sending metrics to graphite ...")
                sock = self._connection()
                try:
                    sock.sendall(data)
                    self._log_debug("flushed metrics to graphite")
                    break
                except socket.error:
                    self.disconnect()

    def _connection(self):
        with self._connection_lock:
            if not self._sock:
                max_retry = self.max_retry
                while True:
                    self._connection_tries += 1
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STRAEM)
                        sock.connect((self.host, self.port))
                        self._sock = sock
                        break
                    except socket.error:
                        sock.close()
                        if max_retry and max_retry <= self._connection_tries:
                            raise IOError("Reached maximum connection retry of {} to {}:{}".format(max_retry, self.host, self.port))
        return self._sock

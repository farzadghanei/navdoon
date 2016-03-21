"""
navdoon.collector
-----------------
Define collectors, that collect Statsd requests and queue them to be
processed by the processor.
"""

import os
import socket
from abc import abstractmethod, ABCMeta
from threading import Event
from navdoon.pystdlib.queue import Queue
from navdoon.utils import LoggerMixIn


DEFAULT_PORT = 8125


class AbstractCollector(object):
    """Abstract base class for collectors"""

    __metaclass__ = ABCMeta

    def __init__(self):
        self._queue = Queue()

    @abstractmethod
    def start(self):
        raise NotImplementedError

    @abstractmethod
    def wait_until_queuing_requests(self, timeout=None):
        raise NotImplementedError

    @abstractmethod
    def shutdown(self):
        raise NotImplementedError

    @abstractmethod
    def wait_until_shutdown(self, timeout=None):
        raise NotImplementedError

    @property
    def queue(self):
        return self._queue

    @queue.setter
    def queue(self, value):
        for method in ('put_nowait', ):
            if not callable(getattr(value, method, None)):
                raise ValueError(
                    "Invalid queue for collector. Queue is missing "
                    "method '{}'".format(method))
        self._queue = value


class SocketServer(LoggerMixIn, AbstractCollector):
    """Collect Statsd metrics via TCP/UDP socket"""

    default_port = DEFAULT_PORT

    def __init__(self, **kargs):
        AbstractCollector.__init__(self)
        LoggerMixIn.__init__(self)
        self.chunk_size = 65535
        self.socket_type = socket.SOCK_DGRAM
        self.socket_timeout = 1
        self.host = '127.0.0.1'
        self.port = self.__class__.default_port
        self.user = None
        self.group = None
        self.socket = None
        self._stop_queuing_requests = Event()
        self._queuing_requests = Event()
        self._shutdown = Event()
        self._should_shutdown = Event()
        self.configure(**kargs)
        self.log_signature = "collector.socket_server "

    def __del__(self):
        self._do_shutdown()

    def configure(self, **kargs):
        """Configure the server, setting attributes.
        Returns a list of attribute names that were affected
        """
        configured = []
        for key in ('host', 'port', 'user', 'group', 'socket_type'):
            if key in kargs:
                setattr(self, key, kargs[key])
                configured.append(key)
        return configured

    def start(self):
        self._bind_socket()
        try:
            while not self._should_shutdown.is_set():
                self._shutdown.clear()
                self._log("starting serving requests on {} {}:{}".format(
                    self.socket_type == socket.SOCK_STREAM and 'TCP' or 'UDP',
                    self.host, self.port))
                self._pre_start()
                if self.socket_type == socket.SOCK_STREAM:
                    self._queue_requests_tcp()
                else:
                    self._queue_requests_udp()
                self._post_start()
                self._log("stopped serving requests")
        finally:
            self._do_shutdown()

    def is_queuing_requests(self):
        return self._queuing_requests.is_set()

    def wait_until_queuing_requests(self, timeout=None):
        self._queuing_requests.wait(timeout)

    def shutdown(self):
        self._log_debug("shutting down ...")
        self._stop_queuing_requests.set()
        self._should_shutdown.set()

    def wait_until_shutdown(self, timeout=None):
        self._shutdown.wait(timeout)

    def _pre_start(self):
        pass

    def _queue_requests_udp(self):
        stop = self._stop_queuing_requests
        chunk_size = self.chunk_size
        sock = self.socket
        receive = sock.recv
        timeout_exception = socket.timeout
        enqueue = self._queue.put_nowait

        try:
            self._queuing_requests.set()
            while not stop.is_set():
                try:
                    data = receive(chunk_size)
                except timeout_exception:
                    data = None
                if data:
                    enqueue(data.decode())
        finally:
            self._queuing_requests.clear()

    def _queue_requests_tcp(self):
        stop = self._stop_queuing_requests
        buffer_size = self.chunk_size
        queue_put_nowait = self._queue.put_nowait
        shutdown_rdwr = socket.SHUT_RDWR
        socket_timeout_exception = socket.timeout

        def _enqueue_from_connection(conn):
            receive = conn.recv
            enqueue = queue_put_nowait
            socket_timeout = socket_timeout_exception
            try:
                while not stop.is_set():
                    try:
                        buff = receive(buffer_size)
                    except socket_timeout:
                        continue
                    if not buff:
                        break
                    enqueue(buff.decode())
            finally:
                conn.shutdown(shutdown_rdwr)
                conn.close()

        try:
            self._queuing_requests.set()
            while not stop.is_set():
                try:
                    connection = self.socket.accept()[0]
                except socket_timeout_exception:
                    continue
                _enqueue_from_connection(connection)
        finally:
            self._queuing_requests.clear()

    def _post_start(self):
        pass

    def _do_shutdown(self):
        self._close_socket()
        self._shutdown.set()

    def _bind_socket(self, sock=None):
        if not sock:
            sock = self._create_socket()
        self._close_socket()
        self._change_process_user_group()
        self.socket = sock
        self._log("bound to address {}:{}".format(*sock.getsockname()))

    def _create_socket(self):
        sock = socket.socket(socket.AF_INET, self.socket_type)
        sock.bind((self.host, self.port))
        sock.settimeout(self.socket_timeout)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        if self.socket_type == socket.SOCK_STREAM:
            sock.listen(5)
        return sock

    def _close_socket(self):
        sock = self.socket
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except socket.error:
                pass
        self.socket = None

    def _change_process_user_group(self):
        if self.user:
            self._log("changing process user to {}".format(self.user))
            os.seteuid(self.user)
        if self.group:
            self._log("changing process group to {}".format(self.group))
            os.setegid(self.group)

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
from navdoon.utils.common import LoggerMixIn
from navdoon.utils.system import ExpandableThreadPool

DEFAULT_PORT = 8125


def socket_type_repr(socket_type):
    sock_types = {
        socket.SOCK_STREAM: "TCP",
        socket.SOCK_DGRAM: "UDP"
    }
    return sock_types.get(socket_type, "UNKNOWN")


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
        for method in ('put_nowait',):
            if not callable(getattr(value, method, None)):
                raise ValueError(
                    "Invalid queue for collector. Queue is missing "
                    "method '{}'".format(method))
        self._queue = value

    def __repr__(self):
        return "collector <{}>".format(self.__class__)


class SocketServer(LoggerMixIn, AbstractCollector):
    """Collect Statsd metrics via TCP/UDP socket"""

    default_port = DEFAULT_PORT

    def __init__(self, **kargs):
        AbstractCollector.__init__(self)
        LoggerMixIn.__init__(self)
        self.chunk_size = 8196
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
        self.num_worker_threads = 4
        self.worker_threads_limit = 128

    def __del__(self):
        self._do_shutdown()

    def __repr__(self):
        return "collector.socket_server {}@{}:{}".format(
            socket_type_repr(self.socket_type),
            self.host,
            self.port
        )

    def configure(self, **kargs):
        """Configure the server, setting attributes.
        Returns a list of attribute names that were affected
        """
        configured = []
        for key in ('host', 'port', 'user', 'group', 'socket_type',
                    'num_worker_threads', 'worker_threads_limit'):
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
                    socket_type_repr(self.socket_type), self.host, self.port))
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
        self._log_debug("waiting until shutdown ...")
        self._shutdown.wait(timeout)
        self._log("shutdown successfully")

    def _pre_start(self):
        pass

    def _queue_requests_udp(self):
        should_stop = self._stop_queuing_requests.is_set
        chunk_size = self.chunk_size
        receive = self.socket.recv
        timeout_exception = socket.timeout
        enqueue = self._queue.put_nowait

        try:
            self._queuing_requests.set()
            self._log_debug("starting queuing UDP requests ...")
            while not should_stop():
                try:
                    data = receive(chunk_size)
                except timeout_exception:
                    data = None
                if data:
                    enqueue(data.decode())
        finally:
            self._log_debug("stopped queuing UDP requests")
            self._queuing_requests.clear()

    def _queue_requests_tcp(self):
        stop_event = self._stop_queuing_requests
        should_stop_accepting = stop_event.is_set
        chunk_size = self.chunk_size
        queue_put_nowait = self._queue.put_nowait
        shutdown_rdwr = socket.SHUT_RDWR
        socket_timeout_exception = socket.timeout

        thread_pool = ExpandableThreadPool(self.num_worker_threads)
        thread_pool.workers_limit = self.worker_threads_limit
        thread_pool.logger = self.logger
        thread_pool.log_signature = "threadpool =< {} ".format(self)
        thread_pool.initialize()

        def _enqueue_from_connection(conn, address):
            buffer_size = chunk_size
            enqueue = queue_put_nowait
            timeout_exception = socket_timeout_exception
            should_stop_queuing = stop_event.is_set
            receive = conn.recv
            incomplete_line_chunk = ''
            try:
                self._log_debug("collecting metrics from TCP {}:{} ...".format(address[0], address[1]))
                while not should_stop_queuing():
                    try:
                        buff_bytes = receive(buffer_size)
                    except timeout_exception:
                        continue
                    if not buff_bytes:
                        break

                    buff_lines = buff_bytes.decode().splitlines(True)
                    if incomplete_line_chunk != '':
                        buff_lines[0] = incomplete_line_chunk + buff_lines[0]
                        incomplete_line_chunk = ''

                    if not buff_lines[-1].endswith('\n'):
                        incomplete_line_chunk = buff_lines.pop()

                    enqueue(''.join(buff_lines))
            finally:
                conn.shutdown(shutdown_rdwr)
                conn.close()
                if incomplete_line_chunk != '':
                    enqueue(incomplete_line_chunk)

        try:
            self._queuing_requests.set()
            self._log_debug("starting accepting TCP connections ...")
            while not should_stop_accepting():
                try:
                    (connection, remote_addr) = self.socket.accept()
                    self._log_debug("TCP connection from {}:{} ...".format(remote_addr[0], remote_addr[1]))
                    connection.settimeout(self.socket_timeout)
                except socket_timeout_exception:
                    continue
                thread_pool.do(_enqueue_from_connection, connection, remote_addr)
            self._log_debug("stopped accepting TCP connection")
            thread_pool.stop(True, 10)  # TODO: set this timeout from object attrs
            self._log_debug("stopped enqueuing TCP requests")
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
            except socket.error as e:
                pass
            finally:
                sock.close()
        self.socket = None

    def _change_process_user_group(self):
        if self.user:
            self._log("changing process user to {}".format(self.user))
            os.seteuid(self.user)
        if self.group:
            self._log("changing process group to {}".format(self.group))
            os.setegid(self.group)

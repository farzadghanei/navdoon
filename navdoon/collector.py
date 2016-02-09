import os
import socket
from multiprocessing import Queue
from threading import Event

from navdoon.utils import LoggerMixIn


class SocketServer(LoggerMixIn):
    default_port = 8125

    def __init__(self, **kargs):
        LoggerMixIn.__init__(self)
        self.chunk_size = 65535
        self.socket_type = socket.SOCK_DGRAM
        self.host = '127.0.0.1'
        self.port = self.__class__.default_port
        self.user = None
        self.group = None
        self.socket = None
        self.queue = Queue()
        self._stop_queuing_requests = Event()
        self._queuing_requests = Event()
        self._listening = Event()
        self._should_shutdown = Event()
        self.configure(**kargs)

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

    def serve(self):
        self._bind_socket()
        try:
            while not self._should_shutdown.is_set():
                self._log(
                    "starting serving requests on {} {}:{}".format(
                        self.socket_type == socket.SOCK_STREAM and 'TCP' or 'UDP',
                        self.host,
                        self.port
                    )
                )
                self._pre_serve()
                if self.socket_type == socket.SOCK_STREAM:
                    self._queue_requests_tcp()
                else:
                    self._queue_requests_udp()
                self._post_serve()
                self._log("stopped serving requests")
        finally:
            self._do_shutdown()

    def is_running(self):
        return self._listening.is_set() and self._queuing_requests.is_set()

    def wait_until_running(self, timeout=None):
        self._queuing_requests.wait(timeout)

    def shutdown(self, force=False):
        self._log("shutting down the server ...")
        self._should_shutdown.set()
        self._stop_queuing_requests.set()
        if force:
            self._log("force shutting down the server")
            self._close_socket()
            self._clear_queue(False)

    def _pre_serve(self):
        pass

    def _queue_requests_udp(self):
        stop = self._stop_queuing_requests
        chunk_size = self.chunk_size
        sock = self.socket
        receive = sock.recv
        enqueue = self.queue.put_nowait

        try:
            self._queuing_requests.set()
            while not stop.is_set():
                data = receive(chunk_size)
                if data:
                    enqueue(data)
        finally:
            self._queuing_requests.clear()

    def _queue_requests_tcp(self):
        stop = self._stop_queuing_requests
        buffer_size = self.chunk_size
        queue_put_nowait = self.queue.put_nowait
        shutdown_rdwr = socket.SHUT_RDWR

        def _enqueue_from_connection(connection, remote_address):
            receive = connection.recv
            enqueue = queue_put_nowait
            try:
                while not stop.is_set():
                    buffer = receive(buffer_size)
                    if not buffer:
                        break
                    enqueue(buffer)
            finally:
                connection.shutdown(shutdown_rdwr)
                connection.close()

        try:
            self._queuing_requests.set()
            while not stop.is_set():
                connection, remote_address = self.socket.accept()
                _enqueue_from_connection(connection, remote_address)
        finally:
            self._queuing_requests.clear()

    def _post_serve(self):
        pass

    def _do_shutdown(self):
        self._close_socket()
        self._clear_queue()

    def _clear_queue(self, join=True):
        queue = self.queue
        if queue:
            queue.close()
            if join:
                queue.join_thread()
            else:
                queue.cancel_join_thread()
        self.queue = None

    def _bind_socket(self, sock=None):
        if not sock:
            sock = self._create_socket()
        self._close_socket()
        self._change_process_user_group()
        self.socket = sock
        self._log("bound to address {}:{}".format(*sock.getsockname()))
        self._listening.set()

    def _create_socket(self):
        sock = socket.socket(socket.AF_INET, self.socket_type)
        sock.bind((self.host, self.port))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)

        if self.socket_type == socket.SOCK_STREAM:
            sock.listen(5)
        return sock

    def _close_socket(self):
        sock = self.socket
        if sock:
            self._log("closing socket on {}:{} ...".format(*sock.getsockname()))
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except socket.error:
                pass
        self.socket = None
        self._listening.clear()

    def _change_process_user_group(self):
        if self.user:
            self._log("Changing process user to %s ...".format(self.user))
            os.seteuid(self.user)
        if self.group:
            self._log("Changing process group to %s ...".format(self.group))
            os.setegid(self.group)

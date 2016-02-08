import socket
from multiprocessing import Queue
from threading import Event


class SocketServer(object):
    default_port = 8125

    def __init__(self):
        self.chunk_size = 65535
        self.socket_type = socket.SOCK_DGRAM
        self.address = ('127.0.0.1', self.__class__.default_port)
        self.user = None
        self.group = None
        self.socket = None
        self.queue = Queue()
        self._stop_queuing_requests = Event()
        self._listening = Event()
        self._should_shutdown = Event()

    def __del__(self):
        self._do_shutdown()

    def serve(self):
        self._bind_socket()
        try:
            while not self._should_shutdown.is_set():
                self._pre_serve()
                self._queue_requests()
                self._post_serve()
        finally:
            self._do_shutdown()

    def is_running(self):
        return self._listening.is_set()

    def wait_until_running(self, timeout=None):
        self._listening.wait(timeout)

    def shutdown(self, force=False):
        self._should_shutdown.set()
        self._stop_queuing_requests.set()
        if force:
            self._close_socket()
            self._clear_queue(False)

    def _pre_serve(self):
        pass

    def _queue_requests(self):
        stop = self._stop_queuing_requests
        chunk_size = self.chunk_size
        sock = self.socket
        receive = sock.recv
        enqueue = self.queue.put_nowait

        while not stop.is_set():
            data = receive(chunk_size)
            if data:
                enqueue(data)

    def _post_serve(self):
        pass

    def _do_shutdown(self):
        self._close_socket()
        self._clear_queue()

    def _clear_queue(self, join=True):
        if self.queue:
            self.queue.close()
            if join:
                self.queue.join_thread()
            else:
                self.queue.cancel_join_thread()
        self.queue = None

    def _bind_socket(self, sock=None):
        if not sock:
            sock = self._create_socket()
        self._close_socket()
        self.socket = sock
        self._listening.set()

    def _create_socket(self):
        sock = socket.socket(socket.AF_INET, self.socket_type)
        sock.bind(self.address)
        if self.socket_type == socket.SOCK_STREAM:
            sock.listen(5)
        return sock

    def _close_socket(self):
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except socket.error:
                pass
        self.socket = None
        self._listening.clear()

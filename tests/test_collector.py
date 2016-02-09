import sys
import socket
import threading
import unittest
import logging
import gc
try:
    from Queue import Empty
except ImportError:
    from queue import Empty
from navdoon.collector import SocketServer


def find_open_port(host, sock_type):
    for port in range(8125, 65535):
        try:
            sock = socket.socket(socket.AF_INET, sock_type)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            sock.bind((host, port))
            break
        except socket.error:
            pass
        finally:
            sock.close()
    return port


def consume_queue(queue, count, timeout=1):
    consumed = []
    for i in range(count):
        try:
            consumed.append(queue.get(True, timeout))
        except Empty:
            break
    return tuple(consumed)


def send_through_socket(sock, data_set):
    for data in data_set:
        sock.sendall(data)
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()


class SocketServerTestCaseMixIn(object):
    def _create_logger(self):
        logger = logging.Logger('navdoon.tests')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler(sys.stderr))
        return logger

    def setup_socket_server(self, socket_type):
        self.host = '127.0.0.1'
        self.port = find_open_port(self.host, socket_type)
        self.server = SocketServer()
        self.server.socket_type = socket_type
        self.server.host = self.host
        self.server.port = self.port
        self.server_thread = threading.Thread(target=self.server.serve)
        self.server_thread.daemon = True

    def start_server_send_data_and_consume_queue(self, data_set, socket_type):
        self.server_thread.start()
        self.server.wait_until_running()
        client_sock = socket.socket(socket.AF_INET, socket_type)
        client_sock.connect((self.host, self.port))
        send_through_socket(client_sock, data_set)
        in_queue = consume_queue(self.server.queue, len(data_set))
        self.server.shutdown()
        return in_queue


class TestUdpServer(SocketServerTestCaseMixIn, unittest.TestCase):
    def setUp(self):
        self.setup_socket_server(socket.SOCK_DGRAM)

    def tearDown(self):
        self.server.shutdown(True)
        self.server = None
        gc.collect()

    def test_constructor_args(self):
        conf = dict(user='thisuser', port=9876, group='thatgroup', host='example.org')
        server = SocketServer(**conf)
        self.assertEquals(server.host, 'example.org')
        self.assertEquals(server.port, 9876)
        self.assertEquals(server.user, 'thisuser')
        self.assertEquals(server.group, 'thatgroup')

    def test_configure(self):
        conf = dict(user='someuser', port=1234, group='somegroup', host='example.org')
        configured = self.server.configure(**conf)
        self.assertEquals(sorted(configured), sorted(conf.keys()))
        self.assertEquals(self.server.host, 'example.org')
        self.assertEquals(self.server.port, 1234)
        self.assertEquals(self.server.user, 'someuser')
        self.assertEquals(self.server.group, 'somegroup')

    def test_queue_requests(self):
        data_set = ("test message", "could be anything")
        in_queue = self.start_server_send_data_and_consume_queue(data_set, socket.SOCK_DGRAM)
        self.assertEqual(data_set, in_queue)


class TestTCPServer(SocketServerTestCaseMixIn, unittest.TestCase):
    def setUp(self):
        self.setup_socket_server(socket.SOCK_STREAM)

    def tearDown(self):
        self.server.shutdown(True)
        self.server = None
        gc.collect()

    def test_constructor_args(self):
        conf = dict(socket_type=socket.SOCK_STREAM)
        server = SocketServer(**conf)
        self.assertEquals(server.socket_type, socket.SOCK_STREAM)

    def test_configure(self):
        conf = dict(socket_type=socket.SOCK_STREAM)
        configured = self.server.configure(**conf)
        self.assertEquals(sorted(configured), sorted(conf.keys()))
        self.assertEquals(self.server.socket_type, socket.SOCK_STREAM)

    def test_queue_requests(self):
        data_set = ("test message",)
        in_queue = self.start_server_send_data_and_consume_queue(data_set, socket.SOCK_STREAM)
        self.assertEqual(data_set, in_queue)
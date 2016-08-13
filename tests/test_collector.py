import sys
import socket
import threading
import unittest
import logging
import gc
from navdoon.pystdlib.queue import Empty, Queue
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


def consume_queue(queue_, count, timeout=1):
    consumed = []
    for i in range(count):
        try:
            consumed.append(queue_.get(True, timeout))
        except Empty:
            break
    return tuple(consumed)


def socket_sendall_close(sock, data_set):
    for data in data_set:
        sock.sendall(data)
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()


def create_logger():
    logger = logging.Logger('navdoon.tests')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stderr))
    return logger


class SocketServerTestCaseMixIn(object):
    def setup_socket_server(self, socket_type):
        self.host = '127.0.0.1'
        self.port = find_open_port(self.host, socket_type)
        self.server = SocketServer()
        self.server.socket_type = socket_type
        self.server.host = self.host
        self.server.port = self.port
        self.server_thread = threading.Thread(target=self.server.start)
        self.server_thread.daemon = True

    def start_server_send_data_and_consume_queue(self, data_set, socket_type):
        self.server_thread.start()
        self.server.wait_until_queuing_requests()
        client_sock = socket.socket(socket.AF_INET, socket_type)
        client_sock.connect((self.host, self.port))
        socket_sendall_close(client_sock, data_set)
        in_queue = consume_queue(self.server.queue, len(data_set))
        return in_queue


class TestUDPServer(SocketServerTestCaseMixIn, unittest.TestCase):
    def setUp(self):
        self.setup_socket_server(socket.SOCK_DGRAM)

    def tearDown(self):
        if self.server.is_queuing_requests():
            self.server.shutdown()
            self.server.wait_until_shutdown(3)
        self.server = None
        gc.collect()

    def test_constructor_args(self):
        conf = dict(user='thisuser',
                    port=9876,
                    group='thatgroup',
                    host='example.org')
        server = SocketServer(**conf)
        self.assertEqual(server.host, 'example.org')
        self.assertEqual(server.port, 9876)
        self.assertEqual(server.user, 'thisuser')
        self.assertEqual(server.group, 'thatgroup')

    def test_configure(self):
        conf = dict(user='someuser',
                    port=1234,
                    group='somegroup',
                    host='example.org')
        configured = self.server.configure(**conf)
        self.assertEqual(sorted(configured), sorted(conf.keys()))
        self.assertEqual(self.server.host, 'example.org')
        self.assertEqual(self.server.port, 1234)
        self.assertEqual(self.server.user, 'someuser')
        self.assertEqual(self.server.group, 'somegroup')

    def test_get_set_queue(self):
        def set_queue(queue_):
            self.server.queue = queue_

        self.assertRaises(ValueError, set_queue, "not a queue")
        queue = Queue()
        self.server.queue = queue
        self.assertEqual(queue, self.server.queue)

    def test_queue_requests(self):
        data_set = ("test message".encode(), "could be anything".encode())
        expected_values_in_queue = tuple([data.decode() for data in data_set])
        in_queue = self.start_server_send_data_and_consume_queue(
            data_set, socket.SOCK_DGRAM)
        self.assertEqual(expected_values_in_queue, in_queue)


class TestTCPServer(SocketServerTestCaseMixIn, unittest.TestCase):
    def setUp(self):
        self.setup_socket_server(socket.SOCK_STREAM)

    def tearDown(self):
        if self.server.is_queuing_requests():
            self.server.shutdown()
            self.server.wait_until_shutdown(3)
        self.server = None
        gc.collect()

    def test_constructor_args(self):
        conf = dict(socket_type=socket.SOCK_STREAM)
        server = SocketServer(**conf)
        self.assertEqual(server.socket_type, socket.SOCK_STREAM)

    def test_configure(self):
        conf = dict(socket_type=socket.SOCK_STREAM)
        configured = self.server.configure(**conf)
        self.assertEqual(sorted(configured), sorted(conf.keys()))
        self.assertEqual(self.server.socket_type, socket.SOCK_STREAM)

    def test_queue_requests(self):
        data_set = ("test message\nin 2 lines\n".encode(), "resource.cpu 42|g\n".encode())
        expected_values_in_queue = ''.join([data.decode() for data in data_set])
        in_queue = self.start_server_send_data_and_consume_queue(
            data_set, socket.SOCK_STREAM)
        self.assertEqual(expected_values_in_queue, ''.join(in_queue))

    def test_queue_requests_includes_incomplete_lines(self):
        long_request = "test message with long message\n" * 500
        # the long request will break into 2 items in the queue, since the test needs to know the number of items in the
        # queue to pick, I'm putting an extra item in the data_set so while test consumes the queue, it will get 1 extra
        # item from the queue to match the number of items put on the queue. looks ugly but I'm fine with it now
        data_set = (long_request.encode(), "resource.cpu 42|g".encode(), "".encode())
        expected_values_in_queue = ''.join([data.decode() for data in data_set])
        in_queue = self.start_server_send_data_and_consume_queue(
            data_set, socket.SOCK_STREAM)
        self.assertEqual(expected_values_in_queue, ''.join(in_queue))

    def test_shutdown(self):
        data_set = ("".encode(), "test_messsage".encode(), "name 10|c@0.1".encode())
        expected_values_in_queue = ''.join([data.decode() for data in data_set])
        in_queue = self.start_server_send_data_and_consume_queue(
            data_set, socket.SOCK_STREAM)
        self.assertEqual(expected_values_in_queue, ''.join(in_queue))
        self.server.shutdown()
        self.server.wait_until_shutdown(5)
        self.assertFalse(self.server.is_queuing_requests())

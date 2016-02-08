import socket
import threading
import unittest
from navdoon.collector import SocketServer


def find_open_port(host, sock_type):
    for port in range(8125, 65535):
        try:
            sock = socket.socket(socket.AF_INET, sock_type)
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
        consumed.append(queue.get(True, timeout))
    return consumed


def send_to_socket(sock, data_set):
    for data in data_set:
        sock.sendall(data)
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()


class SocketServerTestCaseMixIn(object):
    def setup_socket_server(self, socket_type):
        self.host = '127.0.0.1'
        self.port = find_open_port(self.host, socket_type)
        self.server = SocketServer()
        self.server.socket_type = socket_type
        self.server.address = (self.host, self.port)
        self.server_thread = threading.Thread(target=self.server.serve)
        self.server_thread.daemon = True

    def start_server_send_data_and_consume_queue(self, data_set, socket_type):
        self.server_thread.start()
        self.server.wait_until_running()
        client_sock = socket.socket(socket.AF_INET, socket_type)
        client_sock.connect((self.host, self.port))
        send_to_socket(client_sock, data_set)
        in_queue = consume_queue(self.server.queue, len(data_set))
        self.assertEqual(data_set, in_queue)
        self.server.shutdown(True)
        return in_queue


class TestUdpServer(SocketServerTestCaseMixIn, unittest.TestCase):
    def setUp(self):
        self.setup_socket_server(socket.SOCK_DGRAM)

    def test_queue_requests(self):
        data_set = ["test message", "could be anything"]
        in_queue = self.start_server_send_data_and_consume_queue(data_set, socket.SOCK_DGRAM)
        self.assertEqual(data_set, in_queue)
import os
import socket
import sys
import logging
import logging.handlers
import unittest
from os import path
from tempfile import mkstemp

from navdoon.app import App, parse_config_file, default_syslog_socket
from navdoon.collector import SocketServer
from navdoon.destination import Stdout, Graphite, TextFile, CsvFile
from navdoon.processor import QueueProcessor

test_config_file_path = path.join(
    path.join(
        path.dirname(__file__), 'fixtures'), 'test_config.ini')


class TestParseConfigFile(unittest.TestCase):
    def test_parse_config_file(self):
        with open(test_config_file_path) as test_config_file:
            config = parse_config_file(test_config_file)
        self.assertEqual('WARN', config['log_level'])


class TestDefaultSyslogSocket(unittest.TestCase):
    def test_default_syslog_socket(self):
        syslog_socket = default_syslog_socket()
        self.assertIsInstance(syslog_socket, str)
        self.assertNotEqual(syslog_socket, '')
        if not hasattr(self, 'assertRegex'):
            self.assertRegex = self.assertRegexpMatches
        self.assertRegex(syslog_socket, '[/:]')


class TestApp(unittest.TestCase):
    def setUp(self):
        self.config_filename = test_config_file_path

    def test_get_args(self):
        app = App(())
        self.assertEqual((), app.get_args())

        args = ('--log-level', 'DEBUG')
        app = App(args)
        self.assertEqual(args, app.get_args())

    def test_get_config(self):
        app = App(())
        conf = app.get_config()
        self.assertFalse(conf['log_syslog'])

        app = App(('--log-syslog', '-c', self.config_filename))
        conf = app.get_config()
        self.assertTrue(conf['log_syslog'])
        self.assertEqual('WARN', conf['log_level'])

    def test_args_overwrite_config(self):
        app = App(('--log-level', 'ERROR', '-c', self.config_filename))
        conf = app.get_config()
        self.assertEqual('ERROR', conf['log_level'])

    def test_validate_configs(self):
        self.assertRaises(ValueError, App, ('--collector-threads', '0'))
        self.assertRaises(ValueError, App, ('--collector-threads-limit', '-1'))
        self.assertRaises(
            ValueError, App,
            ('--collector-threads', '2', '--collector-threads-limit', '1')
        )

    def test_defaults_for_optional_args(self):
        app = App(())
        conf = app.get_config()
        self.assertEqual('INFO', conf['log_level'])
        self.assertFalse(conf['log_stderr'])
        self.assertEqual(None, conf['log_file'])
        self.assertFalse(conf['log_syslog'])
        self.assertLess(0, conf['flush_interval'])
        self.assertFalse(conf['flush_stdout'])
        self.assertEqual('', conf['flush_graphite'])
        self.assertEqual('', conf['flush_file'])
        self.assertEqual('', conf['collect_udp'])
        self.assertEqual('', conf['collect_tcp'])

    def test_default_options_cover_missing_configs(self):
        app = App(('--log-level', 'FATAL', '-c', self.config_filename))
        conf = app.get_config()
        self.assertEqual('FATAL', conf['log_level'])
        self.assertTrue(conf['log_stderr'])
        self.assertEqual(None, conf['log_file'])
        self.assertFalse(conf['log_syslog'])
        self.assertLess(0, conf['flush_interval'])
        self.assertTrue(conf['flush_stdout'])
        self.assertEqual('', conf['flush_graphite'])
        self.assertEqual('', conf['collect_udp'])
        self.assertEqual('', conf['collect_tcp'])

    def test_get_logger(self):
        app = App(('--config', self.config_filename, '--log-syslog'))
        logger = app.get_logger()
        self.assertEqual(logging.WARN, logger.getEffectiveLevel())
        self.assertEqual(3, len(logger.handlers))
        null_handler, stderr_handler, syslog_handler = logger.handlers
        self.assertIsInstance(stderr_handler, logging.StreamHandler)
        self.assertEqual(stderr_handler.stream, sys.stderr)
        self.assertIsInstance(syslog_handler, logging.handlers.SysLogHandler)

    def test_create_destinations(self):
        app = App(['--config', self.config_filename])
        destinations = app.create_destinations()
        self.assertEqual(1, len(destinations))
        self.assertEqual([Stdout()], destinations)

        app_flush_graphite = App(['--flush-graphite', 'localhost'])
        destinations = app_flush_graphite.create_destinations()
        self.assertEqual(1, len(destinations))
        self.assertEqual([Graphite('localhost', 2003)], destinations)

        app_multi_flush = App(
            ['--config', self.config_filename, '--flush-graphite',
             'example.org:2006,localhost'])
        destinations = app_multi_flush.create_destinations()
        self.assertEqual(3, len(destinations))
        expected = [
            Stdout(), Graphite('example.org', 2006),
            Graphite ('localhost', 2003)
        ]
        self.assertEqual(expected, destinations)

    def test_create_file_destinations(self):
        try:
            _, temp_file_name = mkstemp()
            other_temp_file_name = temp_file_name + '_2'
            app = App(['--flush-file', '{}|{}'.format(temp_file_name, other_temp_file_name)])
            destinations = app.create_destinations()
            self.assertEqual(2, len(destinations))
            self.assertEqual([TextFile(temp_file_name), TextFile(other_temp_file_name)], destinations)
        finally:
            if os.path.exists(temp_file_name):
                os.remove(temp_file_name)
            if os.path.exists(other_temp_file_name):
                os.remove(other_temp_file_name)

    def test_create_csv_file_destinations(self):
        try:
            _, temp_file_name = mkstemp()
            other_temp_file_name = temp_file_name + '_2'
            app = App(['--flush-file-csv', '{}|{}'.format(temp_file_name, other_temp_file_name)])
            destinations = app.create_destinations()
            self.assertEqual(2, len(destinations))
            self.assertEqual([CsvFile(temp_file_name), CsvFile(other_temp_file_name)], destinations)
        finally:
            if os.path.exists(temp_file_name):
                os.remove(temp_file_name)
            if os.path.exists(other_temp_file_name):
                os.remove(other_temp_file_name)

    def test_get_addresses_with_unique_ports(self):
        app = App([])
        self.assertEqual(
            [("localhost", 8127)],
            app.get_addresses_with_unique_ports("localhost:8127")
        )
        self.assertEqual(
            [("example.org", 8125), ("localhost", 8126), ("127.0.0.1", 8127)],
            app.get_addresses_with_unique_ports("example.org,localhost:8126,127.0.0.1:8127")
        )
        self.assertEqual(
            [("", 12345), ("example.org", 8125), ("", 6789)],
            app.get_addresses_with_unique_ports(":12345,example.org,:6789")
        )
        self.assertRaises(ValueError, app.get_addresses_with_unique_ports, "localhost:8125,127.0.0.1:8125")
        self.assertRaises(ValueError, app.get_addresses_with_unique_ports, "localhost:81250000")
        self.assertRaises(ValueError, app.get_addresses_with_unique_ports, "localhost:0")
        self.assertRaises(ValueError, app.get_addresses_with_unique_ports, "localhost:-23")
        self.assertRaises(ValueError, app.get_addresses_with_unique_ports, "localhost,:8125")

    def test_create_collectors_creates_udp_server_by_default(self):
        app = App([])
        collectors = app.create_collectors()
        self.assertEqual(len(collectors), 1)
        collector = collectors.pop()
        self.assertIsInstance(collector, SocketServer)
        self.assertEqual(
            ("127.0.0.1", 8125, socket.SOCK_DGRAM),
            (collector.host, collector.port, collector.socket_type)
        )

    def test_create_udp_collectors(self):
        app = App(['--collect-udp', ':8127,example.com,127.0.0.1:8126'])
        collectors = app.create_collectors()
        self.assertEqual(len(collectors), 3)
        for collector in collectors:
            self.assertIsInstance(collector, SocketServer)
        self.assertEqual(
            ("", 8127, socket.SOCK_DGRAM),
            (collectors[0].host, collectors[0].port, collectors[0].socket_type)
        )
        self.assertEqual(
            ("example.com", 8125, socket.SOCK_DGRAM),
            (collectors[1].host, collectors[1].port, collectors[1].socket_type)
        )
        self.assertEqual(
            ("127.0.0.1", 8126, socket.SOCK_DGRAM),
            (collectors[2].host, collectors[2].port, collectors[2].socket_type)
        )

    def test_create_server(self):
        app = App(['--config', self.config_filename, '--flush-interval', '17'])
        logger = app.get_logger()
        server = app.create_server()
        queue_processor = server.queue_processor
        self.assertEqual(server.logger, logger)
        self.assertIsInstance(queue_processor, QueueProcessor)
        self.assertEqual(queue_processor.logger, logger)
        self.assertEqual(queue_processor.flush_interval, 17)

    def test_create_tcp_collectors(self):
        app = App(['--collect-tcp', ':8127,example.org,127.0.0.1:8126',
                   '--collector-threads', '8', '--collector-threads-limit', '32'])
        collectors = app.create_collectors()
        self.assertEqual(len(collectors), 3)
        for collector in collectors:
            self.assertIsInstance(collector, SocketServer)
            self.assertEqual(collector.num_worker_threads, 8)
            self.assertEqual(collector.worker_threads_limit, 32)
        self.assertEqual(
            ("", 8127, socket.SOCK_STREAM),
            (collectors[0].host, collectors[0].port, collectors[0].socket_type)
        )
        self.assertEqual(
            ("example.org", 8125, socket.SOCK_STREAM),
            (collectors[1].host, collectors[1].port, collectors[1].socket_type)
        )
        self.assertEqual(
            ("127.0.0.1", 8126, socket.SOCK_STREAM),
            (collectors[2].host, collectors[2].port, collectors[2].socket_type)
        )

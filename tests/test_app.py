import sys
import logging
import logging.handlers
import unittest
from os import path
from navdoon.app import App, parse_config_file
from navdoon.destination import Stdout, Graphite

test_config_file_path = path.join(
    path.join(
        path.dirname(__file__), 'fixtures'), 'test_config.ini')


class TestParseConfigFile(unittest.TestCase):
    def test_parse_config_file(self):
        with open(test_config_file_path) as test_config_file:
            config = parse_config_file(test_config_file)
        self.assertEqual('WARN', config['log_level'])


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

    def test_get_logger(self):
        app = App(('--config', self.config_filename, '--log-syslog'))
        logger = app.get_logger()
        self.assertEqual(logging.WARN, logger.getEffectiveLevel())
        self.assertEqual(2, len(logger.handlers))
        stderr_handler, syslog_handler = logger.handlers
        self.assertIsInstance(stderr_handler, logging.StreamHandler)
        self.assertEqual(stderr_handler.stream, sys.stderr)
        self.assertIsInstance(syslog_handler, logging.handlers.SysLogHandler)

    def test_get_destinations(self):
        app = App(['--config', self.config_filename])
        destinations = app.get_destinations()
        self.assertEqual(1, len(destinations))
        self.assertEqual([(Stdout, ())], destinations)

        app_flush_graphite = App(['--flush-graphite', 'localhost'])
        destinations = app_flush_graphite.get_destinations()
        self.assertEqual(1, len(destinations))
        self.assertEqual([(Graphite, ('localhost', 2003))], destinations)

        app_multi_flush = App(
            ['--config', self.config_filename, '--flush-graphite',
             'example.org:2006,localhost'])
        destinations = app_multi_flush.get_destinations()
        self.assertEqual(3, len(destinations))
        expected = [
            (Stdout, ()), (Graphite,
                           ('example.org', 2006)), (Graphite,
                                                    ('localhost', 2003))
        ]
        self.assertEqual(expected, destinations)

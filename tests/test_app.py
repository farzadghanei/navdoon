import unittest
from os import path
from navdoon.app import App


class TestApp(unittest.TestCase):
    def setUp(self):
        self.config_filename = path.join(path.join(path.dirname(__file__), 'fixtures'), 'test_config.ini')

    def test_get_args(self):
        app = App(())
        self.assertEqual((), app.get_args())

        args = ('--log-level', 'DEBUG')
        app = App(args)
        self.assertEqual(args, app.get_args())

    def test_get_config(self):
        app = App(())
        conf = app.get_config()
        self.assertFalse(conf['syslog'])

        app = App(('--syslog', '-c', self.config_filename))
        conf = app.get_config()
        self.assertTrue(conf['syslog'])
        self.assertEqual('WARN', conf['log_level'])

    def test_args_overwrite_config(self):
        app = App(('--log-level', 'ERROR', '-c', self.config_filename))
        conf = app.get_config()
        self.assertEqual('ERROR', conf['log_level'])

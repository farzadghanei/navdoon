import sys
import logging
from argparse import ArgumentParser, FileType
from threading import Lock
from signal import signal, SIGINT, SIGTERM, SIGHUP
try:
    import ConfigParser as configparser
except ImportError:
    import configparser
import navdoon
from navdoon.server import Server
from navdoon.destination import Stream, Graphite


log_level_names = ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL', 'CRITICAL')


class App(object):
    def __init__(self, args):
        self._config = dict()
        self._args = args
        self._configure(args)
        self._server = None
        self._run_lock = Lock()
        self._shutdown_lock = Lock()
        self._reload_lock = Lock()

    def __del__(self):
        self.shutdown()

    @staticmethod
    def get_description():
        return "{} v{}\n{}".format(
                navdoon.__title__,
                navdoon.__version__,
                navdoon.__summary__
            )

    @staticmethod
    def get_default_config():
        return dict(
                config=None,
                log_level='INFO',
                log_file=None,
                log_stderr=False,
                syslog=False,
            )

    def get_args(self):
        return self._args

    def get_config(self):
        return self._config

    def create_logger(self):
        logger = logging.Logger('navdoon')
        return logger

    def create_collectors(self):
        collectors = []
        args = self._args
        if args.get('flush-stdout'):
            collectors.append(Stream(sys.stdout))

        if args.get('flush-stderr'):
            collectors.append(Stream(sys.stderr))

        if args.get('flush-graphite'):
            collectors.append(Graphite())

        return collectors


    def create_destinations(self):
        raise NotImplemented()

    def create_server(self):
        server = Server()
        server.logger = self.create_logger()
        destinations = self.create_destinations()
        collectors = self.create_destinations()
        for dest in destinations:
            server.add_destination(dest)
        for collector in collectors:
            server.add_collector(collector)
        return server

    def run(self):
        with self._run_lock:
            self._register_signal_handlers()
            self._server = self.create_server()
            self._server.start()

    def _configure(self, args):
        parsed_args = vars(self._parse_args(args))
        configs = self.get_default_config()
        if parsed_args['config'] is not None:
            with parsed_args['config'] as config_file:
                configs = self._parse_config_file(config_file)

        for key, value in parsed_args.items():
            if value is not None:
                configs[key] = value

        self._config = configs

    def _parse_config_file(self, file_):
        parser = configparser.SafeConfigParser()
        parser.readfp(file_)
        config = dict()
        for key, value in parser.items('navdoon'):
            if key == 'config':
                continue
            elif key == 'log-level' and value not in log_level_names:
                raise ValueErorr("Invalid log level '{}' in configuration file '{}'".format(
                    value, file_.name))
            config[key.replace('-', '_')] = value
        return config

    def _parse_args(self, args):
        parser = ArgumentParser(description=self.get_description())
        parser.add_argument('-c', '--config', help='path to config file', type=FileType('r'))
        parser.add_argument('--log-level', help='logging level', choices=log_level_names)
        parser.add_argument('-l', '--log', help='path to log file')
        parser.add_argument('--log-stderr', help='log to stderr')
        parser.add_argument('--syslog', action='store_true', help='log to syslog')
        return parser.parse_args(args)

    def _register_signal_handlers(self):
        signal(SIGINT, self._handle_signal_int)
        signal(SIGTERM, self._handle_signal_term)
        signal(SIGHUP, self._handle_signal_hup)

    def shutdown(self):
        with self._shutdown_lock:
            if self._server:
                self._server.shutdown()
            self._server = None

    def reload(self):
        with self._reload_lock:
            if not self._server:
                raise Exception("App is not running, can not reload")
            self._configure(self.args)
            self._server.reload()

    def _handle_signal_int(self):
        self.shutdown()

    def _handle_signal_term(self):
        self.shutdown()

    def _handle_signal_hup(self):
        self.reload()


def main(args):
    app = App(args)
    app.run()


if __name__ == '__main__':
    sys.exit(main(sys.argv))

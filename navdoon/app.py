import sys
import logging
import logging.handlers
from argparse import ArgumentParser, FileType
from threading import Lock
from signal import signal, SIGINT, SIGTERM, SIGHUP
import navdoon
from navdoon.pystdlib import configparser
from navdoon.server import Server
from navdoon.destination import Stdout, Graphite


log_level_names = ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL', 'CRITICAL')


def parse_config_file(file_):
    parser = configparser.SafeConfigParser()
    parser.readfp(file_)
    config = dict()
    for key, value in parser.items('navdoon'):
        if key == 'config':
            continue
        elif key == 'log-level' and value not in log_level_names:
            raise ValueError("Invalid log level '{}' in configuration file '{}'".format(
                value, file_.name))
        config[key.replace('-', '_')] = value
    return config


class App(object):
    def __init__(self, args):
        self._config = dict()
        self._args = args
        self._server = None
        self._logger = None
        self._run_lock = Lock()
        self._shutdown_lock = Lock()
        self._reload_lock = Lock()
        self._configure(args)

    def __del__(self):
        self.shutdown()
        self._close_logger()

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

    def get_logger(self):
        if not self._logger:
            self._logger = self._create_logger()
        return self._logger

    def get_destinations(self):
        destinations = []
        if self._config.get('flush_stdout'):
            destinations.append((Stdout, ()))
        if self._config.get('flush_graphite'):
            for graphite_address in self._config['flush_graphite'].split(','):
                graphite_address = graphite_address.strip().split(':')
                graphite_host = graphite_address.pop(0).strip()
                graphite_port = graphite_address and int(graphite_address.pop()) or 2003
                destinations.append((Graphite, (graphite_host, graphite_port)))
        return destinations

    def create_server(self):
        server = Server()
        server.logger = self.get_logger()
        server.set_destinations(self.get_destinations())
        return server

    def run(self):
        with self._run_lock:
            self._register_signal_handlers()
            self._server = self.create_server()
            self._server.start()

    def shutdown(self):
        with self._shutdown_lock:
            if self._server:
                self._server.shutdown()
            self._server = None

    def reload(self):
        with self._reload_lock:
            if not self._server:
                raise Exception("App is not running, can not reload")
            self._configure(self._args)
            logger = self._create_logger()
            destinations = self.get_destinations()
            self._close_logger()
            self._logger = logger
            self._server.logger = logger
            self._server.set_destinations(destinations)
            self._server.reload()

    def _configure(self, args):
        parsed_args = vars(self._parse_args(args))
        configs = self.get_default_config()
        if parsed_args['config'] is not None:
            with parsed_args['config'] as config_file:
                configs = parse_config_file(config_file)

        for key, value in parsed_args.items():
            if value is not None:
                configs[key] = value

        self._config = configs

    def _parse_args(self, args):
        parser = ArgumentParser(description=self.get_description())
        parser.add_argument('-c', '--config', help='path to config file', type=FileType('r'))
        parser.add_argument('--log-level', help='logging level', choices=log_level_names)
        parser.add_argument('--log-file', help='path to log file')
        parser.add_argument('--log-stderr', help='log to stderr')
        parser.add_argument('--log-syslog', action='store_true', help='log to syslog')
        parser.add_argument('--flush-stdout', help='flush to standard output')
        parser.add_argument('--flush-graphite', help='flush to graphite', default=None)
        return parser.parse_args(args)

    def _register_signal_handlers(self):
        signal(SIGINT, self._handle_signal_int)
        signal(SIGTERM, self._handle_signal_term)
        signal(SIGHUP, self._handle_signal_hup)

    def _handle_signal_int(self):
        self.shutdown()

    def _handle_signal_term(self):
        self.shutdown()

    def _handle_signal_hup(self):
        self.reload()

    def _create_logger(self):
        log_level_name = self._config.get('log_level', 'INFO')
        if log_level_name not in log_level_names:
            raise ValueError("invalid log level " + log_level_name)
        logger = logging.Logger('navdoon')
        logger.setLevel(getattr(logging, log_level_name))
        if self._config.get('log_stderr'):
            logger.addHandler(logging.StreamHandler(sys.stderr))
        if self._config.get('log_file'):
            logger.addHandler(logging.FileHandler(self._config['log_file']))
        if self._config.get('log_syslog'):
            logger.addHandler(logging.handlers.SysLogHandler())
        return logger

    def _close_logger(self):
        if self._logger:
            for handler in self._logger.handlers:
                if hasattr(handler, 'close') and callable(handler.close):
                    handler.close()
                self._logger.removeHandler(handler)
        self._logger = None


def main(args):
    app = App(args)
    app.run()


if __name__ == '__main__':
    sys.exit(main(sys.argv))

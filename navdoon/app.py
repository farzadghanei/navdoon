"""
navdoon.app
-----------
Define the application, what is executed and handles interations and signals.
The application combines all the other components into what the end user
can use as the final product.
"""

from __future__ import print_function

import socket
import sys
import logging
import logging.handlers
from argparse import ArgumentParser, FileType
from threading import RLock, Thread
from signal import signal, SIGINT, SIGTERM, SIGHUP
from time import sleep

import navdoon
from navdoon.pystdlib import configparser
from navdoon.server import Server
from navdoon.destination import Stdout, Graphite
from navdoon.collector import SocketServer, DEFAULT_PORT
from navdoon.utils import os_syslog_socket, LoggerMixIn

LOG_LEVEL_NAMES = ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL', 'CRITICAL')


def parse_config_file(file_):
    """Parse app configurations from contents of a file"""

    parser = configparser.SafeConfigParser()
    parser.readfp(file_)
    config = dict()
    for key, value in parser.items('navdoon'):
        if key == 'config':
            continue
        elif key == 'log-level' and value not in LOG_LEVEL_NAMES:
            raise ValueError(
                "Invalid log level '{}' in configuration file '{}'".format(
                    value, file_.name))
        config[key.replace('-', '_')] = value
    return config


def default_syslog_socket():
    return os_syslog_socket() or 'localhost:{}'.format(
                                logging.handlers.SYSLOG_UDP_PORT)


class App(LoggerMixIn):
    """Navdoon application, configure and use the components based on the
    provided arguments and configurations.
    """

    def __init__(self, args):
        super(App, self).__init__()
        self.log_signature = "navdoon.app "
        self._config = dict()
        self._args = args
        self._server = None
        self._run_lock = RLock()
        self._shutdown_lock = RLock()
        self._reload_lock = RLock()
        self._configure(args)

    def __del__(self):
        self.shutdown(1)
        self._close_logger()

    @staticmethod
    def get_description():
        return "{} v{}\n{}".format(navdoon.__title__, navdoon.__version__,
                                   navdoon.__summary__)

    @staticmethod
    def get_default_config():
        return dict(config=None,
                    log_level='INFO',
                    log_file=None,
                    log_stderr=False,
                    log_syslog=False,
                    syslog_socket= default_syslog_socket(),
                    flush_interval=1,
                    flush_stdout=False,
                    flush_graphite='',
                    collect_udp='',
                    collect_tcp='')

    def get_args(self):
        return self._args

    def get_config(self):
        return self._config

    def get_logger(self):
        if not self.logger:
            self.logger = self._create_logger()
        return self.logger

    def create_destinations(self):
        destinations = []
        if self._config.get('flush_stdout'):
            destinations.append(Stdout())
        if self._config.get('flush_graphite'):
            for graphite_address in self._config['flush_graphite'].split(','):
                graphite_address = graphite_address.strip().split(':')
                graphite_host = graphite_address.pop(0).strip()
                graphite_port = graphite_address and int(graphite_address.pop(
                )) or 2003
                destinations.append(Graphite(graphite_host, graphite_port))
        return destinations

    def create_collectors(self):
        collectors = []
        if self._config.get('collect_tcp'):
            collectors.extend(
                self._create_socket_servers(
                    self._config['collect_tcp'], socket.SOCK_STREAM))
        if self._config.get('collect_udp'):
            collectors.extend(
                self._create_socket_servers(
                    self._config['collect_udp'], socket.SOCK_DGRAM))
        if len(collectors) < 1:
            collectors.extend(
                self._create_socket_servers(
                    '127.0.0.1:8125', socket.SOCK_DGRAM))
        return collectors

    def _create_socket_servers(self, addresses, socket_type):
        collectors = []
        socket_addresses = self.get_addresses_with_unique_ports(
            addresses)
        for (host, port) in socket_addresses:
            socket_server = self._configure_socket_server(
                SocketServer(),
                host=host,
                port=port
            )
            socket_server.socket_type = socket_type
            collectors.append(socket_server)
        return collectors

    def create_server(self):
        server = Server()
        return self._configure_server(server)

    def run(self):
        with self._run_lock:
            self._register_signal_handlers()
            self._server = self.create_server()
            server_thread = Thread(target=self._server.start)
            server_thread.start()
            # If we block by joining thread, we won't receive OS signals
            # poll the status of the server thread every often instead.
            while server_thread.is_alive():
                sleep(2)
            server_thread.join()

    def shutdown(self, timeout=None):
        with self._shutdown_lock:
            self._log_debug("acquired shutdown lock")
            if self._server:
                self._log_debug("shutting down server ...")
                self._server.shutdown(timeout)
            self._server = None
            self._log("server shutdown successfully")

    def reload(self):
        with self._reload_lock:
            if not self._server:
                raise Exception("App is not running, can not reload")
            self._configure(self._args)
            logger = self._create_logger()
            self._close_logger()
            self.logger = logger
            self._configure_server(self._server)
            self._server.reload()

    def _configure_server(self, server):
        conf = self.get_config()
        logger = self.get_logger()
        destinations = self.create_destinations()
        if logger.handlers:
            server.logger = logger
        queue_processor = server.queue_processor
        if queue_processor is None:
            queue_processor = server.create_queue_processor()
        queue_processor.logger = logger
        queue_processor.flush_interval = conf['flush_interval']
        queue_processor.set_destinations(destinations)
        server.queue_processor = queue_processor
        server.set_collectors(self.create_collectors())
        return server

    def _configure_socket_server(self, collector, host=None, port=None):
        logger = self.get_logger()
        if logger.handlers:
            collector.logger = logger
        if host is not None:
            collector.host = host
        if port is not None:
            collector.port = port
        return collector

    def _configure(self, args):
        parsed_args = vars(self._parse_args(args))
        configs = self.get_default_config()
        if parsed_args['config'] is not None:
            with parsed_args['config'] as config_file:
                configs = parse_config_file(config_file)

        store_true_args = ('log_stderr', 'log_syslog', 'flush_stdout')
        for key, value in parsed_args.items():
            if key in store_true_args:
                if key not in configs or value is True:
                    configs[key] = value
                continue
            if value is not None:
                configs[key] = value

        self._config = configs

    def _parse_args(self, args):
        parser = ArgumentParser(description=self.get_description())
        parser.add_argument('-c',
                            '--config',
                            help='path to config file',
                            type=FileType('r'))
        parser.add_argument('--log-level',
                            help='logging level',
                            choices=LOG_LEVEL_NAMES)
        parser.add_argument('--log-file', help='path to log file')
        parser.add_argument('--log-stderr',
                            action='store_true',
                            help='log to stderr')
        parser.add_argument('--log-syslog',
                            action='store_true',
                            help='log to syslog')
        parser.add_argument('--syslog-socket',
                            default=default_syslog_socket(),
                            help='syslog server socket address. '
                            'socket path, or host:port for UDP'
                            )
        parser.add_argument('--flush-interval',
                            type=float,
                            help='flush interval in seconds')
        parser.add_argument('--flush-stdout',
                            action='store_true',
                            help='flush to standard output')
        parser.add_argument('--flush-graphite',
                            help='comma separated graphite addresses to flush '
                                    'stats to, each in host[:port] format',
                            default=None)
        parser.add_argument('--collect-udp',
                            help='listen on UDP addresses to collect stats')
        parser.add_argument('--collect-tcp',
                            help='listen on TCP addresses to collect stats')

        return parser.parse_args(args)

    def _register_signal_handlers(self):
        signal(SIGINT, self._handle_signal_int)
        signal(SIGTERM, self._handle_signal_term)
        #FIXME: uncomment this after fixing reload
        #signal(SIGHUP, self._handle_signal_hup)

    def _handle_signal_int(self, *args):
        self._log("received SIGINT")
        self.shutdown(3)

    def _handle_signal_term(self, *args):
        self._log("received SIGTERM")
        self.shutdown(3)

    def _handle_signal_hup(self, *args):
        self._log("received SIGHUP")
        self.reload()

    def _create_logger(self):
        log_level_name = self._config.get('log_level', 'INFO')
        if log_level_name not in LOG_LEVEL_NAMES:
            raise ValueError("invalid log level " + log_level_name)
        logger = logging.Logger('navdoon')
        logger.setLevel(getattr(logging, log_level_name))
        if self._config.get('log_stderr'):
            logger.addHandler(logging.StreamHandler(sys.stderr))
        if self._config.get('log_file'):
            logger.addHandler(logging.FileHandler(self._config['log_file']))
        if self._config.get('log_syslog'):
            syslog_address = self._config['syslog_socket'].split(':')
            if len(syslog_address) < 2:
                syslog_address = syslog_address[0].strip()
            else:
                syslog_address = tuple([syslog_address[0].strip(),
                                      int(syslog_address[1])])
            logger.addHandler(logging.handlers.SysLogHandler(syslog_address))
        return logger

    def _close_logger(self):
        if self.logger:
            handlers = []
            for handler in self.logger.handlers:
                if hasattr(handler, 'close') and callable(handler.close):
                    handler.close()
                handlers.append(handler)
            map(self.logger.removeHandler, handlers)
        self.logger = None

    @staticmethod
    def get_addresses_with_unique_ports(addresses):
        address_tuples = [tuple(address.strip().split(':')) for address in
                          addresses.split(',')]
        result = []
        ports = set()
        for address in address_tuples:
            host = address[0]
            if len(address) > 1 and address[1]:
                port_str = address[1]
                port = int(port_str)
                if port < 1 or port > 65535:
                    raise ValueError(
                        "Port {} is out of range".format(port_str))
                if port in ports:
                    raise ValueError(
                        "Port {} is already specified before".format(port_str))
            else:
                port = DEFAULT_PORT
            result.append((host, port))
            ports.add(port)
        return result


def main(args=sys.argv[1:]):
    """Entry point, setup and start the application"""
    app = App(args)
    return app.run()


if __name__ == '__main__':
    sys.exit(main())

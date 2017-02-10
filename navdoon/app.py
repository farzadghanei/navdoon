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
import signal
from argparse import ArgumentParser, FileType, Namespace
from threading import RLock, Thread
from time import sleep

import navdoon
from navdoon.pystdlib import configparser
from navdoon.server import Server
from navdoon.destination import Stdout, Graphite, AbstractDestination, TextFile, CsvFile
from navdoon.collector import AbstractCollector, SocketServer, DEFAULT_PORT
from navdoon.utils.common import LoggerMixIn
from navdoon.utils.system import os_syslog_socket
from navdoon.pystdlib.typing import Tuple, IO, Dict, Any, Set

LOG_LEVEL_NAMES = ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL', 'CRITICAL')  # type: Tuple[str, str, str, str, str, str]


def parse_config_file(file_):
    # type: (IO) -> Dict[str, Any]
    """Parse app configurations from contents of a file"""

    parser = configparser.ConfigParser()  # type: ignore
    _parse_method = getattr(parser, 'read_file', parser.readfp)
    _parse_method(file_)

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
    # type: () -> str
    return os_syslog_socket() or 'localhost:{}'.format(
        logging.handlers.SYSLOG_UDP_PORT)  # type: ignore


class App(LoggerMixIn):
    """Navdoon application, configure and use the components based on the
    provided arguments and configurations.
    """

    def __init__(self, args):
        # type: (List[str]) -> None
        LoggerMixIn.__init__(self)
        self.log_signature = "navdoon.app "  # type: str
        self._config = dict()  # type: Dict[str, Any]
        self._args = args  # type: List[str]
        self._server = None  # type: Server
        self._run_lock = RLock()  # type: RLock
        self._shutdown_lock = RLock()  # type: RLock
        self._reload_lock = RLock()  # type: RLock
        self._configure(args)

    def __del__(self):
        # type() -> None
        self.shutdown(1)
        self._close_logger()

    @staticmethod
    def get_description():
        # type: () -> str
        return "{} v{}\n{}".format(navdoon.__title__, navdoon.__version__,
                                   navdoon.__summary__)

    @staticmethod
    def get_default_config():
        # type: () -> Dict[str, Any]
        return dict(config=None,
                    log_level='INFO',
                    log_file=None,
                    log_stderr=False,
                    log_syslog=False,
                    syslog_socket=default_syslog_socket(),
                    flush_interval=1,
                    flush_stdout=False,
                    flush_graphite='',
                    flush_file='',
                    flush_file_csv='',
                    collect_udp='',
                    collect_tcp='',
                    collector_threads=4,
                    collector_threads_limit=128)

    def get_args(self):
        # type: () -> List[Any]
        return self._args

    def get_config(self):
        # type: () -> Dict[str, Any]
        return self._config

    def get_logger(self):
        # type: () -> logging.Logger
        if not self.logger:
            self.logger = self._create_logger()  # type: logging.Logger
        return self.logger

    def create_destinations(self):
        # type: () -> List[AbstractDestination]
        destinations = []  # type: List[AbstractDestination]
        if self._config.get('flush_stdout'):
            destinations.append(Stdout())
        if self._config.get('flush_graphite'):
            for graphite_address in self._config['flush_graphite'].split(','):
                graphite_address = graphite_address.strip().split(':')
                graphite_host = graphite_address.pop(0).strip()
                graphite_port = graphite_address and int(graphite_address.pop(
                )) or 2003
                destinations.append(Graphite(graphite_host, graphite_port))
        if self._config.get('flush_file'):
            for file_path in self._config['flush_file'].split('|'):
                destinations.append(TextFile(file_path))
        if self._config.get('flush_file_csv'):
            for file_path in self._config['flush_file_csv'].split('|'):
                destinations.append(CsvFile(file_path))
        return destinations

    def create_collectors(self):
        # type: () -> List[AbstractCollector]
        collectors = []  # type: List[AbstractCollector]
        if self._config.get('collect_tcp'):
            tcp_collectors = self._create_socket_servers(
                self._config['collect_tcp'], socket.SOCK_STREAM)
            for collector in tcp_collectors:
                collector.num_worker_threads = self._config['collector_threads']
                collector.worker_threads_limit = self._config['collector_threads_limit']
            collectors.extend(tcp_collectors)
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
        # type: (str, int) -> List[SocketServer]
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
        # type: () -> Server
        server = Server()
        return self._configure_server(server)

    def run(self):
        # type: () -> int
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
        return 0

    def shutdown(self, timeout=None):
        # type: (float) -> None
        if not self._server:
            return
        with self._shutdown_lock:
            self._log_debug("shutting down server ...")
            self._server.shutdown(timeout)
            self._server = None
            self._log("server shutdown successfully")

    def reload(self):
        # type: () -> None
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
        # type: (Server) -> Server
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
        # type: (SocketServer, str, int) -> SocketServer
        logger = self.get_logger()
        if logger.handlers:
            collector.logger = logger
        if host is not None:
            collector.host = host
        if port is not None:
            collector.port = port
        return collector

    def _configure(self, args):
        # type: (List[str]) -> None
        parsed_args = vars(self._parse_args(args))
        configs = self.get_default_config()
        if parsed_args['config'] is not None:
            with parsed_args['config'] as config_file:
                configs.update(parse_config_file(config_file))

        store_true_args = ('log_stderr', 'log_syslog', 'flush_stdout')
        for key, value in parsed_args.items():
            if key in store_true_args:
                if key not in configs or value is True:
                    configs[key] = value
            elif value is not None:
                configs[key] = value

        self._validate_configs(configs)
        self._config = configs

    def _parse_args(self, args):
        # type: (List[str]) -> Namespace
        parser = ArgumentParser(description=self.get_description())
        parser.add_argument('-c',
                            '--config',
                            help='path to config file',
                            type=FileType('rt'))
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
        parser.add_argument('--flush-file',
                            help='pipe separated file paths to flush '
                                 'stats to',
                            default=None)
        parser.add_argument('--flush-file-csv',
                            help='pipe separated file paths to flush '
                                 'stats to in CSV format',
                            default=None)
        parser.add_argument('--collect-udp',
                            help='listen on UDP addresses to collect stats')
        parser.add_argument('--collect-tcp',
                            help='listen on TCP addresses to collect stats')
        parser.add_argument('--collector-threads',
                            help='number of threads started by each collector'
                                 ' (TCP collectors only)',
                            type=int
                            )
        parser.add_argument('--collector-threads-limit',
                            help='max number of threads running by each collector'
                                 ' (TCP collectors only)',
                            type=int
                            )

        return parser.parse_args(args)

    def _validate_configs(self, args):
        # type: (Dict[str, Any]) -> None
        none_negative_args = ('collector_threads_limit',)
        greater_than_one_args = ('collector_threads',)
        for key, value in args.items():
            if key in none_negative_args and value < 0:
                raise ValueError("The value for {} can not be negative".format(key))
            if key in greater_than_one_args and value < 1:
                raise ValueError("The value for {} can not be less than 1".format(key))
        if args['collector_threads_limit'] != 0 \
                and args['collector_threads_limit'] < args['collector_threads']:
            raise ValueError(
                "The value for collector_threads_limit can not be less than collector_threads")

    def _register_signal_handlers(self):
        # type: () -> None
        signal.signal(signal.SIGINT, self._handle_signal_int)
        signal.signal(signal.SIGTERM, self._handle_signal_term)
        # we can not set a handler for SIGHUP on Windows
        if hasattr(signal, 'SIGHUP'):
            try:
                signal.signal(signal.SIGHUP, self._handle_signal_hup)
                pass
            except ValueError:
                pass

    def _handle_signal_int(self, *args):
        # type: (*Any) -> None
        self._log("received SIGINT")
        self.shutdown()

    def _handle_signal_term(self, *args):
        # type: (*Any) -> None
        self._log("received SIGTERM")
        self.shutdown()

    def _handle_signal_hup(self, *args):
        # type: (*Any) -> None
        self._log("received SIGHUP")
        self.reload()

    def _create_logger(self):
        # type: () -> logging.Logger
        log_level_name = self._config.get('log_level', 'INFO')
        if log_level_name not in LOG_LEVEL_NAMES:
            raise ValueError("invalid log level " + log_level_name)
        logger = logging.Logger('navdoon')  # type: ignore
        logger.addHandler(logging.NullHandler())
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
        # type: () -> None
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
        # type: (str) -> List[Tuple[str, int]]
        address_tuples = [tuple(address.strip().split(':')) for address in
                          addresses.split(',')]
        result = []  # type: List[Tuple[str, int]]
        ports = set()  # type: Set[int]
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
    # type: (List[str]) -> int
    """Entry point, setup and start the application"""
    app = App(args)
    return app.run()


if __name__ == '__main__':
    sys.exit(main())

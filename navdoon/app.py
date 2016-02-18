import sys
import logging
from argparse import ArgumentParser
from threading import Lock
from signal import signal, SIGINT, SIGTERM, SIGHUP
from navdoon.server import Server
from navdoon.destination import Stream, Graphite


class App(object):
    def __init__(self, args):
        self._args = self._parse_args(args)
        self._server = None
        self._run_lock = Lock()
        self._shutdown_lock = Lock()
        self._reload_lock = Lock()

    def __del__(self):
        self._shutdown()

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

    def _parse_args(self):
        raise NotImplemented()

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

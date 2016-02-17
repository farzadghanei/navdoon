import sys
import logging
from threading import Lock
from signal import signal, SIGINT, SIGTERM, SIGHUP
from navdoon.server import Server
from navdoon.destinations import Stream, Graphite


class App(object):
    def __init__(self, opts, args):
        self.opts = opts
        self.args = args
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
        opts = self.opts
        if opts.get('flush-stdout'):
            collectors.append(Stream(sys.stdout))

        if opts.get('flush-stderr'):
            collectors.append(Stream(sys.stderr))

        if opts.get('flush-graphite'):
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

    def _register_signal_handlers(self):
        signal(SIGINT, self._handle_signal_int)
        signal(SIGTERM, self._handle_signal_term)
        signal(SIGTERM, self._handle_signal_hup)

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


def main(opts, args):
    app = App(opts, args)
    app.run()


if __name__ == '__main__':
    sys.exit(main([], []))

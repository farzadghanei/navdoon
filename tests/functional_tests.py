#!/usr/bin/env python
from __future__ import absolute_import, print_function

import os
import subprocess
from os.path import dirname, abspath
from time import time, sleep
from re import match
from unittest import TestCase, main, skip

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from statsdmetrics.client import Client
from statsdmetrics.client.tcp import TCPClient


TEST_DIR = dirname(abspath(__file__))
BASE_DIR = dirname(TEST_DIR)
CONF_FILE = os.path.join(TEST_DIR, 'fixtures', 'functional_test_config.ini')
APP_BIN = os.path.join(BASE_DIR, 'bin', 'navdoon_src')


class TestNavdoonStatsdServer(TestCase):
    tcp_port = 8126
    udp_port = 8125
    flush_interval = 2

    @classmethod
    def create_server_program_args(cls):
        return [
                APP_BIN,
                "--config", CONF_FILE,
                '--flush-interval', str(cls.flush_interval),
                '--collect-udp', '127.0.0.1:{}'.format(cls.udp_port)
            ]

    def setUp(self):
        self.app_args = self.create_server_program_args()
        self.app_proc = subprocess.Popen(
                self.app_args,
                stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                universal_newlines=True,
                )
        try:
            self._wait_until_server_starts_collecting()
        except RuntimeError as error:
            self.app_proc.kill()
            raise error

    def _wait_until_server_starts_collecting(self, timeout=10):
        self._wait_until_log_matches('.*server.+collectors.+are\s+running', timeout, 0.05)

    def _wait_until_server_shuts_down(self, timeout=10):
        self._wait_until_log_matches('.*server shutdown successfully', timeout, 0.05)

    def _wait_until_log_matches(self, pattern, timeout=10, sleep_time=None):
        start_time = time()
        while True:
            if time() - start_time > timeout:
                raise RuntimeError(
                        "waiting for pattern {} in server logs timedout".format(
                            pattern))
            line = self.app_proc.stderr.readline().strip()
            if match(pattern, line):
                break
            if sleep_time:
                sleep(sleep_time)

    def tearDown(self):
        self.app_proc.poll()
        if self.app_proc.returncode is None:
            self.app_proc.kill()

    @skip('test is not complete')
    def test_udp_collectors_flushing_stdout(self):
        client = Client("localhost", self.__class__.udp_port)
        for i in range(1, 5):
            client.increment("event")
        for i in range(1, 5):
            client.timing("process", 10.1)
        # wait for at least 1 flush
        sleep(self.__class__.flush_interval)
        self.app_proc.terminate()
        self._wait_until_server_shuts_down()
        flushed_metrics, logs = self.app_proc.communicate()
        flushed_metrics = [l.strip() for l in flushed_metrics.split()]
        self.assertGreater(len(flushed_metrics), 6, 'flushed enough metrics')



if __name__ == '__main__':
    main()

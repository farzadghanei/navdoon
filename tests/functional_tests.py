#!/usr/bin/env python
from __future__ import absolute_import, print_function

import sys
import os
import subprocess
import gc
from os.path import dirname, abspath
from random import randint
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


def metrics_to_dict(metrics):
    result = dict()
    for metric in metrics:
        name, value, _ = metric.split()
        result[name] = float(value) if '.' in value else int(value)
    return result


class TestNavdoonStatsdServer(TestCase):
    tcp_port = 8126
    udp_port = 8125
    flush_interval = 2

    @classmethod
    def create_server_program_args(cls, udp_port=None, tcp_port=None):
        udp_port = udp_port or cls.udp_port
        tcp_port = tcp_port or cls.tcp_port
        return [
                APP_BIN,
                "--config", CONF_FILE,
                "--flush-interval", str(cls.flush_interval),
                "--collect-udp", "127.0.0.1:{}".format(udp_port),
                "--collect-tcp", "127.0.0.1:{}".format(tcp_port)
            ]

    def setUp(self):
        self.udp_port = randint(8125, 8999)
        self.tcp_port = randint(8125, 9999)
        self.app_args = self.create_server_program_args(udp_port=self.udp_port, tcp_port=self.tcp_port)
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

    def _wait_until_server_shuts_down(self, timeout=20):
        self._wait_until_log_matches('.*server shutdown successfully', timeout, 0.05)

    def _wait_until_log_matches(self, pattern, timeout=10, sleep_time=None):
        start_time = time()
        logs = []
        while True:
            if time() - start_time > timeout:
                logs = [log for log in logs if log.strip() != ""]
                print("server logs dump")
                print("================")
                for log in logs:
                    print(log, file=sys.stderr)
                raise RuntimeError(
                    "waiting for pattern {} in server logs timedout.".format(
                        pattern))
            line = self.app_proc.stderr.readline().strip()
            logs.append(line)
            if match(pattern, line):
                break
            if sleep_time:
                sleep(sleep_time)

    def tearDown(self):
        self.app_proc.poll()
        if self.app_proc.returncode is None:
            self.app_proc.kill()
        self.app_proc = None
        gc.collect()

    def test_udp_collectors_flushing_stdout(self):
        client = Client("localhost", self.udp_port)
        for _ in range(0, 3):
            client.increment("event")
        client.timing("process", 10.1)
        client.timing("process", 10.2)
        client.timing("process", 10.3)
        # wait for at least 1 flush
        sleep(self.__class__.flush_interval)
        self.app_proc.terminate()
        self._wait_until_server_shuts_down()
        flushed_metrics = self.app_proc.communicate()[0].splitlines()
        self.assertGreater(len(flushed_metrics), 5, 'flushed 1 counter and at least 4 timers')
        self.assertDictEqual(
            {
                "event": 3, "process.count": 3, "process.max": 10.3,
                "process.min": 10.1, "process.mean": 10.2,
                "process.median": 10.2
            },
            metrics_to_dict(flushed_metrics)
        )

    def test_udp_and_tcp_collectors_combine_and_flush_to_stdout(self):
        client = Client("localhost", self.udp_port)
        tcp_client = TCPClient("localhost", self.tcp_port)
        for _ in range(0, 2):
            client.increment("event")
            tcp_client.increment("event")

        client.timing("process", 8.5)
        client.timing("process", 9.8)
        tcp_client.timing("process", 8.7)
        tcp_client.timing("query", 2)
        # wait for at least 1 flush
        sleep(self.__class__.flush_interval)
        self.app_proc.terminate()
        self._wait_until_server_shuts_down()
        flushed_metrics = self.app_proc.communicate()[0].splitlines()
        self.assertGreater(len(flushed_metrics), 9, 'flushed 1 counter and at least 2 x 4 timers')

        self.maxDiff = None
        self.assertDictEqual(
            {
                "event": 4, "process.count": 3, "process.max": 9.8,
                "process.min": 8.5, "process.mean": 9.0,
                "process.median": 8.7, "query.count": 1, "query.max": 2.0,
                "query.min": 2.0, "query.mean": 2.0, "query.median": 2.0
            },
            metrics_to_dict(flushed_metrics)
        )


if __name__ == '__main__':
    main()

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


def wait_until_log_matches(process, pattern, timeout=10, sleep_time=None):
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
        line = process.stderr.readline().strip()
        logs.append(line)
        if match(pattern, line):
            break
        if sleep_time:
            sleep(sleep_time)


def wait_until_server_shuts_down(process, timeout=20):
    wait_until_log_matches(process, '.*server shutdown successfully', timeout, 0.05)


def wait_until_server_starts_collecting(process, timeout=10):
    wait_until_log_matches(process, '.*server.+collectors.+are\s+running', timeout, 0.05)


class TestNavdoonStatsdServer(TestCase):
    @staticmethod
    def create_server_program_args(config=CONF_FILE, udp_port=None, tcp_port=None, flush_interval=1):
        program_args = [APP_BIN, '--flush-interval', str(flush_interval)]
        if config is not None:
            program_args.extend(('--config', config))
        if udp_port is not None:
            program_args.extend(('--collect-udp', '127.0.0.1:{}'.format(udp_port)))
        if tcp_port is not None:
            program_args.extend(('--collect-tcp', '127.0.0.1:{}'.format(tcp_port)))
        return program_args

    def create_server_process(self, *args, **kwargs):
        app_args = self.create_server_program_args(*args, **kwargs)
        app_process = subprocess.Popen(app_args, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                                       universal_newlines=True)
        try:
            wait_until_server_starts_collecting(app_process)
        except RuntimeError as error:
            app_process.kill()
            raise error
        return app_process

    def setUp(self):
        self.app_process = None

    def tearDown(self):
        if self.app_process is not None:
            self.app_process.poll()
            if self.app_process.returncode is None:
                self.app_process.kill()
            self.app_process = None
            gc.collect()

    def test_udp_collectors_flushing_stdout(self):
        udp_port = randint(8125, 8999)
        flush_interval = 2
        self.app_process = self.create_server_process(udp_port=udp_port, flush_interval=flush_interval)

        client = Client("localhost", udp_port)
        for _ in range(0, 3):
            client.increment("event")
        client.timing("process", 10.1)
        client.timing("process", 10.2)
        client.timing("process", 10.3)
        # wait for at least 1 flush
        sleep(flush_interval)
        self.app_process.terminate()
        wait_until_server_shuts_down(self.app_process)
        flushed_metrics = self.app_process.communicate()[0].splitlines()
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
        udp_port = randint(8125, 8999)
        tcp_port = randint(8125, 9999)
        flush_interval = 2
        self.app_process = self.create_server_process(udp_port=udp_port, tcp_port=tcp_port,
                                                      flush_interval=flush_interval)
        client = Client("localhost", udp_port)
        tcp_client = TCPClient("localhost", tcp_port)
        for _ in range(0, 2):
            client.increment("event")
            tcp_client.increment("event")

        client.timing("process", 8.5)
        client.timing("process", 9.8)
        tcp_client.timing("process", 8.7)
        tcp_client.timing("query", 2)
        # wait for at least 1 flush
        sleep(flush_interval)
        self.app_process.terminate()
        wait_until_server_shuts_down(self.app_process)
        flushed_metrics = self.app_process.communicate()[0].splitlines()
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

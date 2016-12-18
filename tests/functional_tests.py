#!/usr/bin/env python
from __future__ import absolute_import, print_function

import sys
import os
import signal
import subprocess
import gc
from os.path import dirname, abspath
from random import randint
from tempfile import mkstemp
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
            logs = [log for log in logs if log.strip()]
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


def wait_until_server_processed_metric(process, name, timeout=10):
    wait_until_log_matches(process, '.*queue.processor processing metrics:\s*' + name, timeout, 0.1)


def write_to_file(filename, content):
    with open(filename, 'wt') as fh:
        fh.write(content)


class TestNavdoonStatsdServer(TestCase):
    @staticmethod
    def create_server_program_args(config=CONF_FILE, udp_port=None, tcp_port=None, flush_interval=None, flush_file=None, flush_file_csv=None):
        program_args = [APP_BIN]
        if flush_interval is not None:
            program_args.extend(('--flush-interval', str(flush_interval)))
        if flush_file is not None:
            program_args.extend(('--flush-file', str(flush_file)))
        if flush_file_csv is not None:
            program_args.extend(('--flush-file-csv', str(flush_file_csv)))
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
        self.remove_files = []

    def tearDown(self):
        if self.app_process is not None:
            self.app_process.poll()
            if self.app_process.returncode is None:
                self.app_process.kill()
            self.app_process = None
            gc.collect()
        for filename in self.remove_files:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_udp_collectors_flushing_stdout(self):
        udp_port = randint(8125, 8999)
        flush_interval = 2
        self.app_process = self.create_server_process(udp_port=udp_port, flush_interval=flush_interval)

        client = Client("localhost", udp_port)
        for _ in range(0, 3):
            client.increment("event")
        client.timing("process", 101)
        client.timing("process", 102)
        client.timing("process", 103)
        # wait for at least 1 flush
        sleep(flush_interval)
        self.app_process.terminate()
        wait_until_server_shuts_down(self.app_process)
        flushed_metrics = self.app_process.communicate()[0].splitlines()
        self.assertGreater(len(flushed_metrics), 5, 'flushed 1 counter and at least 4 timers')
        self.assertDictEqual(
            {
                "event": 3, "process.count": 3, "process.max": 103,
                "process.min": 101, "process.mean": 102,
                "process.median": 102
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

        client.timing("process", 85)
        client.timing("process", 98)
        tcp_client.timing("process", 87)
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
                "event": 4, "process.count": 3, "process.max": 98,
                "process.min": 85, "process.mean": 90,
                "process.median": 87, "query.count": 1, "query.max": 2.0,
                "query.min": 2.0, "query.mean": 2.0, "query.median": 2.0
            },
            metrics_to_dict(flushed_metrics)
        )

    def test_reload_server_keeps_the_queue(self):
        tcp_port = randint(8125, 9999)
        _, config_filename = mkstemp(text=True)
        self.remove_files.append(config_filename)
        write_to_file(
            config_filename,
            """
[navdoon]
log-level=DEBUG
log-stderr=true
flush-stdout=true
collect-tcp=127.0.0.1:{}
flush-interval=60
""".format(tcp_port)
        )
        self.app_process = self.create_server_process(config=config_filename)
        tcp_client = TCPClient("localhost", tcp_port)
        for _ in range(0, 2):
            tcp_client.increment("event")
        tcp_client.timing("query", 2)
        del tcp_client
        wait_until_server_processed_metric(self.app_process, 'event')

        udp_port = randint(8125, 8999)
        flush_interval = 5
        write_to_file(
            config_filename,
            """
[navdoon]
log-level=DEBUG
log-stderr=true
flush-stdout=true
collect-udp=127.0.0.1:{}
flush-interval={}
""".format(udp_port, flush_interval)
        )

        self.app_process.send_signal(signal.SIGHUP)
        wait_until_server_starts_collecting(self.app_process, 10)

        client = Client("localhost", udp_port)
        for _ in range(0, 2):
            client.increment("event")
        client.timing("query", 4)
        client.increment("finish")

        self.assertRaises(Exception, TCPClient, "localhost", tcp_port)  # TCP collector should be down
        os.remove(config_filename)

        wait_until_server_processed_metric(self.app_process, 'finish')
        # wait for at least 1 flush
        sleep(flush_interval)

        self.app_process.terminate()
        wait_until_server_shuts_down(self.app_process)

        flushed_metrics = self.app_process.communicate()[0].splitlines()
        self.assertGreaterEqual(len(flushed_metrics), 5)

        self.maxDiff = None
        self.assertDictEqual(
            {
                "event": 4, "query.count": 2, "query.max": 4.0,
                "query.min": 2.0, "query.mean": 3.0, "query.median": 3.0,
                "finish": 1
            },
            metrics_to_dict(flushed_metrics)
        )

    def test_flushing_files(self):
        _, file_name = mkstemp()
        os.remove(file_name)
        udp_port = randint(8125, 8999)
        flush_interval = 2
        csv_file_name = file_name + '.csv'
        self.remove_files.append(file_name)
        self.remove_files.append(csv_file_name)
        self.app_process = self.create_server_process(udp_port=udp_port, flush_interval=flush_interval, flush_file=file_name, flush_file_csv=csv_file_name)

        client = Client("localhost", udp_port)
        for _ in range(0, 3):
            client.increment("event")
        client.timing("process", 20)
        client.timing("process", 22)
        client.timing("process", 24)
        # wait for at least 1 flush
        sleep(flush_interval)
        self.app_process.terminate()
        wait_until_server_shuts_down(self.app_process)

        self.assertTrue(os.path.exists(file_name))
        with open(file_name) as file_handle:
            flushed_metrics = [line.rstrip() for line in file_handle.readlines()]

        self.assertTrue(os.path.exists(csv_file_name))
        with open(csv_file_name) as file_handle:
            flushed_metrics_csv = [line.rstrip() for line in file_handle.readlines()]

        expected_metrics_dict = {
                "event": 3, "process.count": 3, "process.max": 24,
                "process.min": 20, "process.mean": 22,
                "process.median": 22
            }
        self.assertGreater(len(flushed_metrics), 5, 'flushed 1 counter and at least 4 timers')
        self.assertDictEqual(expected_metrics_dict,  metrics_to_dict(flushed_metrics))

        self.assertGreater(len(flushed_metrics_csv), 5, 'flushed 1 counter and at least 4 timers')


if __name__ == '__main__':
    main()

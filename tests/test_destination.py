import unittest
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
from time import time
from navdoon.destination import Graphite, Stream


class TestGraphite(unittest.TestCase):
    def test_create_request_from_metrics(self):
        metrics = [('users', 34, 123456), ('cpu', 78, 98765)]
        self.assertEqual(["users 34 123456", "cpu 78 98765"],
                         Graphite.create_request_from_metrics(metrics), )

        metrics = [('no.time', 34), ('is.fine', 78, time())]
        self.assertEqual(2, len(Graphite.create_request_from_metrics(metrics)))


class TestStream(unittest.TestCase):
    def test_create_output_from_metrics(self):
        output = StringIO()
        dest = Stream(output)

        metrics = [('logins', 12, 456789), ('mem', 53, 98765)]
        self.assertEqual(["logins 12 456789", "mem 53 98765"],
                         dest.create_output_from_metrics(metrics), )

        metrics = [('no.time', 192), ('is.fine', 221, time())]
        self.assertEqual(2, len(dest.create_output_from_metrics(metrics)))

    def test_flush(self):
        output = StringIO()
        dest = Stream(output)

        metrics = [('logins', 12, 456789), ('mem', 53, 98765)]
        dest.flush(metrics)
        self.assertEqual("logins 12 456789\nmem 53 98765\n", output.getvalue())

    def test_flush_with_pattern(self):
        output = StringIO()
        dest = Stream(output)
        dest.pattern = '"{name}"={value}@{timestamp}'

        metrics = [('logins', 12, 456789), ('mem', 53, 98765)]
        dest.flush(metrics)
        self.assertEqual('"logins"=12@456789\n"mem"=53@98765\n',
                         output.getvalue())

    def test_flush_with_append(self):
        output = StringIO()
        dest = Stream(output)
        dest.append = "+++"

        metrics = [('users', 800, 5678), ('cpu', 99, 1234)]
        dest.flush(metrics)
        self.assertEqual("users 800 5678+++cpu 99 1234+++", output.getvalue())

    def test_flush_with_partial_pattern_and_append(self):
        output = StringIO()
        dest = Stream(output)
        dest.pattern = "({name}:'{value}'"
        dest.append = ")"

        metrics = [('users', 800, 5678), ('cpu', 99, 1234)]
        dest.flush(metrics)
        self.assertEqual("(users:'800')(cpu:'99')", output.getvalue())

import os
import unittest
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
from os import remove
from time import time
from tempfile import mkstemp
from navdoon.destination import Graphite, Stream, CsvStream, TextFile


class TestGraphite(unittest.TestCase):
    def test_create_request_from_metrics(self):
        metrics = [('users', 34, 123456), ('cpu', 78, 98765)]
        self.assertEqual(["users 34 123456", "cpu 78 98765"],
                         Graphite.create_request_from_metrics(metrics), )

        metrics = [('no.time', 34), ('is.fine', 78, time())]
        self.assertEqual(2, len(Graphite.create_request_from_metrics(metrics)))

    def test_equality_based_on_attrs(self):
        graphite1 = Graphite('example.org', 2003)
        graphite2 = Graphite('localhost', 2004)
        self.assertNotEqual(graphite1, graphite2)

        graphite1.host = 'localhost'
        graphite1.port = 2004
        self.assertEqual(graphite1, graphite2)


class TestStream(unittest.TestCase):
    def test_stream_property(self):
        output = StringIO()
        dest = Stream(output)
        self.assertEqual(dest.stream, output)

        another_dest = Stream(StringIO())
        self.assertNotEqual(another_dest.stream, output)
        another_dest.stream = output
        self.assertEqual(another_dest.stream, output)

    def test_stream_property_fail_on_invalid_object(self):
        self.assertRaises(ValueError, Stream, "not a file like object")

    def test_equality_based_on_stream(self):
        output1 = StringIO()
        output2 = StringIO()
        stream1 = Stream(output1)
        stream2 = Stream(output2)
        self.assertNotEqual(stream1, stream2)
        stream2.stream = output1
        self.assertEqual(stream1, stream2)

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


class TestCsvStream(unittest.TestCase):
    def test_create_output_from_metrics(self):
        output = StringIO()
        dest = CsvStream(output)

        metrics = [('events', 8, 12345), ('mem', 34, 98765)]
        self.assertEqual(['"events","8","12345"', '"mem","34","98765"'],
                         dest.create_output_from_metrics(metrics), )

        metrics = [('no.time', 192), ('is.fine', 221, time())]
        self.assertEqual(2, len(dest.create_output_from_metrics(metrics)))

    def test_flush(self):
        output = StringIO()
        dest = CsvStream(output)
        metrics = [('logins', 12, 456789), ('mem', 53, 98765)]
        dest.flush(metrics)
        self.assertEqual('"logins","12","456789"\r\n"mem","53","98765"\r\n', output.getvalue())


class TestTextFile(unittest.TestCase):
    def setUp(self):
        _, self.temp_file_name = mkstemp()
        os.remove(self.temp_file_name)

    def tearDown(self):
        if os.path.exists(self.temp_file_name):
            remove(self.temp_file_name)

    def test_flush(self):
        dest = TextFile(self.temp_file_name)
        metrics = [('logins', 12, 456789), ('mem', 53, 98765)]
        dest.flush(metrics)
        self.assertTrue(os.path.exists(self.temp_file_name))
        self.assertFileHasLine('logins 12 456789', self.temp_file_name)
        self.assertFileHasLine('mem 53 98765', self.temp_file_name)

    def assertFileHasLine(self, expected, filename):
        with open(filename) as file_:
            lines = [line.rstrip() for line in file_.readlines()]
            self.assertIn(expected, lines)
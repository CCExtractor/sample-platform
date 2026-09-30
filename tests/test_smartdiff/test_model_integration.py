"""Tests for TestResultFile.generate_smart_diff (the model glue) against real files.

The method is exercised with a lightweight stand-in ``self`` so the test stays a
fast unit test (no database/ORM mapper configuration required).
"""

import os
import tempfile
import unittest
from unittest import mock

from mod_test.models import TestResultFile

_CUE = "1\n00:00:01,000 --> 00:00:04,000\nHello world\n"


def _run(expected_text, got_text, ext='.srt', got='GOT'):
    """
    Write two outputs to a temp dir and run generate_smart_diff over them.

    :param expected_text: Expected output content.
    :type expected_text: str
    :param got_text: Actual output content.
    :type got_text: str
    :param ext: Output file extension.
    :type ext: str
    :param got: The 'got' hash (set to None to simulate no produced output).
    :type got: str
    :return: The smart-diff classification.
    :rtype: dict
    """
    base = tempfile.mkdtemp()
    with open(os.path.join(base, 'EXP' + ext), 'w', encoding='utf-8') as handle:
        handle.write(expected_text)
    with open(os.path.join(base, 'GOT' + ext), 'w', encoding='utf-8') as handle:
        handle.write(got_text)
    stub = mock.Mock()
    stub.expected = 'EXP'
    stub.got = got
    stub.regression_test_output.correct_extension = ext
    stub.read_lines = TestResultFile.read_lines
    return TestResultFile.generate_smart_diff(stub, base)


class GenerateSmartDiffTests(unittest.TestCase):
    """The model method reads the on-disk outputs and classifies the difference."""

    def test_identical(self):
        """Equal on-disk outputs classify as identical."""
        self.assertEqual(_run(_CUE, _CUE)['kind'], 'identical')

    def test_timing_shift(self):
        """A shifted output is classified as a timing shift."""
        shifted = "1\n00:00:01,500 --> 00:00:04,500\nHello world\n"
        self.assertEqual(_run(_CUE, shifted)['kind'], 'timing_shift')

    def test_missing_got_is_identical(self):
        """A null 'got' (no produced output) short-circuits to identical."""
        self.assertEqual(_run(_CUE, _CUE, got=None)['kind'], 'identical')


if __name__ == "__main__":
    unittest.main()

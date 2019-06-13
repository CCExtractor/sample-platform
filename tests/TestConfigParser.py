import json
import unittest

from mock import mock

from config_parser import parse_config
from tests.base import provide_file_at_root


class TestConfigParser(unittest.TestCase):
    def test_parse_config(self):
        file_config = "TEST = 'run'"
        expected_config = {'TEST': 'run'}

        with provide_file_at_root('parse.py', file_config):
            out_config = parse_config('parse')

        self.assertEquals(out_config, expected_config)

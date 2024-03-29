"""Contains tests related to the config handling."""

import json
from unittest import mock

from config_parser import parse_config
from tests.base import BaseTestCase, provide_file_at_root


class TestConfigParser(BaseTestCase):
    """Test config parsing."""

    def test_parse_config(self):
        """Test parse_config function."""
        file_config = "TEST = 'run'"
        expected_config = {'TEST': 'run'}

        with provide_file_at_root('parse.py', file_config, to_delete=False):
            out_config = parse_config('parse')

        self.assertEquals(out_config, expected_config)

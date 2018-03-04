import unittest

from mod_home.models import GeneralData
from tests.base import general_data

from mock import mock


class TestGeneralData(unittest.TestCase):

    def test_that_init_works_correctly(self):
        key = general_data.key2
        value = general_data.value2
        actual = GeneralData(key, value)

        self.assertEqual(actual.key, key)
        self.assertEqual(actual.value, value)

    def test_that_representation_works(self):
        key = general_data.key2
        value = general_data.value2
        actual = GeneralData(key, value)

        expected = '<GeneralData {key}: {value}>'.format(key=key, value=value)

        self.assertEqual(str(actual), expected)

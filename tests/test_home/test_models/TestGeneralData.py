import unittest

from mod_home.models import GeneralData
from tests.base import BaseTestCase

from mock import mock


class TestGeneralData(BaseTestCase):

    def test_that_init_works_correctly(self):
        key = self.general_data2.key
        value = self.general_data2.value
        actual = GeneralData(key, value)

        self.assertEqual(actual.key, key)
        self.assertEqual(actual.value, value)

    def test_that_representation_works(self):
        key = self.general_data2.key
        value = self.general_data2.value
        actual = GeneralData(key, value)

        expected = '<GeneralData {key}: {value}>'.format(key=key, value=value)

        self.assertEqual(str(actual), expected)

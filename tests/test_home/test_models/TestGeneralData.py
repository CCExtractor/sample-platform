import unittest

from mod_home.models import GeneralData

from mock import mock


class TestGeneralData(unittest.TestCase):

    def test_that_init_works_correctly(self):
        key = 'linux'
        value = '22'
        actual = GeneralData(key, value)

        self.assertEqual(actual.key, key)
        self.assertEqual(actual.value, value)

    def test_that_representation_works(self):
        key = 'linux'
        value = '22'
        actual = GeneralData(key, value)

        rep = '<GeneralData {key}: {value}>'.format(key=key, value=value)

        self.assertEqual(str(actual), rep)

import unittest

from mod_home.models import CCExtractorVersion
from datetime import datetime
from tests.base import ccextractor_version

from mock import mock


class TestCCExtractorVersion(unittest.TestCase):

    def test_that_init_works_correctly(self):
        version = ccextractor_version.version
        released = ccextractor_version.released
        released_date = datetime.strptime(released, '%Y-%m-%dT%H:%M:%SZ').date()
        commit = ccextractor_version.commit
        actual = CCExtractorVersion(version, released, commit)

        self.assertEqual(actual.version, version)
        self.assertEqual(actual.released, released_date)
        self.assertEqual(actual.commit, commit)

    def test_that_representation_works(self):
        version = ccextractor_version.version
        released = ccextractor_version.released
        commit = ccextractor_version.commit
        actual = CCExtractorVersion(version, released, commit)

        expected = '<Version {v}>'.format(v=actual.version)

        self.assertEqual(str(actual), expected)

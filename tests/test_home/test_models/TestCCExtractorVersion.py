import unittest

from mod_home.models import CCExtractorVersion
from datetime import datetime

from mock import mock

class TestCCExtractorVersion(unittest.TestCase):
    def test_that_init_works_correctly(self):
        version = '1.2.3'
        released = '2013-02-27T19:35:32Z'
        released_date = datetime.strptime(released, '%Y-%m-%dT%H:%M:%SZ').date()
        commit = '1978060bf7d2edd119736ba3ba88341f3bec3323'
        actual = CCExtractorVersion(version, released, commit)

        self.assertEqual(actual.version, version)
        self.assertEqual(actual.released, released_date)
        self.assertEqual(actual.commit, commit)

    def test_that_representation_works(self):
        version = '1.2.3'
        released = '2013-02-27T19:35:32Z'
        commit = '1978060bf7d2edd119736ba3ba88341f3bec3323'
        actual = CCExtractorVersion(version, released, commit)

        version = '<Version {v}>'.format(v=actual.version)

        self.assertEqual(str(actual), version)

from tests.base import BaseTestCase
from mock import mock

import mod_home.controllers as home
from mod_home.models import GeneralData, CCExtractorVersion


class TestControllers(BaseTestCase):

    def test_root(self):
        response = self.app.test_client().get('/')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('home/index.html')

    def test_about(self):
        response = self.app.test_client().get('/about')
        self.assertEqual(response.status_code, 200)
        self.assert_template_used('home/about.html')

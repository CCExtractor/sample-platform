import unittest
from database import create_session
from mock import mock

import mod_home.controllers as home
from mod_home.models import GeneralData, CCExtractorVersion


def mock_database(db_string, drop_tables=False):
    db = create_session(db_string, drop_tables)
    mock_db = mock.MagicMock(spec=db)
    return mock_db


class TestControllers(unittest.TestCase):

    def setUp(self):
        with mock.patch('database.create_session') as create_session:
            create_session.side_effect = mock_database
            from run import app
            app.config['TESTING'] = True
            self.app = app.test_client()

    def test_root(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.status_code, 200)

    def test_about(self):
        response = self.app.get('/about')
        self.assertEqual(response.status_code, 200)

import unittest
import run
from database import create_session
from flask_testing import TestCase
from database import create_session
from mod_home.models import GeneralData, CCExtractorVersion
from collections import namedtuple
from mock import mock


def load_config():
    return {}
    pass


class BaseTestCase(TestCase):
    @mock.patch('run.app.config.from_pyfile', side_effect=load_config)
    def create_app(self, mock_config):
        """
        Create an instance of the app with the testing configuration
        :return:
        """
        from run import app, g
        app.config['TESTING'] = True
        app.config['DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        with app.app_context():
            self.db = create_session(app.config['DATABASE_URI'])
        app.config['SQLALCHEMY_POOL_SIZE'] = 1
        return app

    def setUp(self):
        general_data = namedtuple('general_data', 'key value')
        self.general_data1 = general_data(
            key='last_commit', value='1978060bf7d2edd119736ba3ba88341f3bec3323')
        self.general_data2 = general_data(key='linux', value='22')
        ccextractor_version = namedtuple(
            'ccextractor_version', 'version released commit')
        self.ccextractor_version = ccextractor_version(version='1.2.3',
                                                       released='2013-02-27T19:35:32Z',
                                                       commit='1978060bf7d2edd119736ba3ba88341f3bec3323')
        pass

    @staticmethod
    def add_last_commit_to_general_data(general_data, db):
        generaldata = GeneralData(general_data.key, general_data.value)
        db.add(generaldata)
        db.commit()
        return

    @staticmethod
    def add_ccextractor_version(ccx_ver, db):
        ccextractorversion = CCExtractorVersion(ccx_ver.version, ccx_ver.released,
                                                ccx_ver.commit)
        db.add(ccextractorversion)
        db.commit()
        return

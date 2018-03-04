import unittest
import run
from run import app, g
from flask_testing import TestCase
from database import create_session
from mod_home.models import GeneralData, CCExtractorVersion


class BaseTestCase(TestCase):

    def create_app(self):
        """
        Create an instance of the app with the testing configuration
        :return:
        """
        app.config['TESTING'] = True
        app.config['DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_POOL_SIZE'] = 1
        return app

    def SetUp(self):
        pass

    @staticmethod
    def add_last_commit_to_general_data():
        generaldata = GeneralData(general_data.key1, general_data.value1)
        g.db.add(generaldata)
        g.db.commit()
        return

    @staticmethod
    def add_ccextractor_version():
        ccextractorversion = CCExtractorVersion(ccextractor_version.version, ccextractor_version.released,
                                                ccextractor_version.commit)
        g.db.add(ccextractorversion)
        g.db.commit()
        return


class ccextractor_version:
    version = '1.2.3'
    released = '2013-02-27T19:35:32Z'
    commit = '1978060bf7d2edd119736ba3ba88341f3bec3323'


class general_data:
    key1 = 'last_commit'
    value1 = '1978060bf7d2edd119736ba3ba88341f3bec3323'
    key2 = 'linux'
    value2 = '22'

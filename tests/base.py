import os

from database import create_session
from flask_testing import TestCase
from database import create_session
from mod_home.models import GeneralData, CCExtractorVersion
from mod_test.models import Fork, Test, TestType, TestPlatform, TestResult, TestResultFile
from mod_regression.models import Category, RegressionTestOutput, RegressionTest, \
                                    regressionTestLinkTable, InputType, OutputType
from mod_sample.models import Sample
from mod_auth.models import User, Role
from unittest import mock
from flask import g


def generate_keys():
    from utility import ROOT_DIR
    secret_csrf_path = "{path}secret_csrf".format(path=os.path.join(ROOT_DIR, ""))
    secret_key_path = "{path}secret_key".format(path=os.path.join(ROOT_DIR, ""))
    if not os.path.exists(secret_csrf_path):
        secret_csrf_cmd = "head -c 24 /dev/urandom > {path}".format(path=secret_csrf_path)
        os.system(secret_csrf_cmd)
    if not os.path.exists(secret_key_path):
        secret_key_cmd = "head -c 24 /dev/urandom > {path}".format(path=secret_key_path)
        os.system(secret_key_cmd)

    return {'secret_csrf_path': secret_csrf_path, 'secret_key_path': secret_key_path}


def load_config(file):
    key_paths = generate_keys()
    with open(key_paths['secret_key_path'], 'rb') as secret_key_file:
        secret_key = secret_key_file.read()
    with open(key_paths['secret_csrf_path'], 'rb') as secret_csrf_file:
        secret_csrf = secret_csrf_file.read()

    return {'Testing': True,
            'DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SQLALCHEMY_POOL_SIZE': 1,
            'GITHUB_DEPLOY_KEY': 'test_deploy',
            'GITHUB_CI_KEY': 'test_ci',
            'GITHUB_TOKEN': '',
            'GITHUB_BOT': '',
            'GITHUB_OWNER': 'test_owner',
            'GITHUB_REPOSITORY': 'test_repo',
            'HMAC_KEY': 'test_key',
            'MIN_PWD_LEN': '10',
            'MAX_PWD_LEN': '500',
            'SECRET_KEY': secret_key,
            'CSRF_SESSION_KEY': secret_csrf
            }


signup_information = {'valid_email': 'someone@example.com',
                      'existing_user_email': 'dummy@example.com',
                      'existing_user_name': 'dummy',
                      'existing_user_pwd': 'dummy_pwd',
                      'existing_user_role': Role.user
                      }

class BaseTestCase(TestCase):
    @mock.patch('config_parser.parse_config', side_effect=load_config)
    def create_app(self, mock_config):
        """
        Create an instance of the app with the testing configuration
        :return:
        """
        from run import app
        return app

    def setUp(self):
        self.app.preprocess_request()
        g.db = create_session(
            self.app.config['DATABASE_URI'], drop_tables=True)
        general_data = GeneralData(
            'last_commit', '1978060bf7d2edd119736ba3ba88341f3bec3323')
        g.db.add(general_data)
        self.ccextractor_version = CCExtractorVersion('1.2.3', '2013-02-27T19:35:32Z',
                                                      '1978060bf7d2edd119736ba3ba88341f3bec3323')
        g.db.add(self.ccextractor_version)
        test = [
            Test(TestPlatform.linux, TestType.pull_request,
                 1, 'master', 'abcdefgh', 1),
            Test(TestPlatform.linux, TestType.pull_request,
                 2, 'master', 'abcdefgh', 1)
        ]
        g.db.add_all(test)
        categories = [
            Category('Broken', 'Samples that are broken'),
            Category('DVB', 'Samples that contain DVB subtitles'),
            Category('DVD', 'Samples that contain DVD subtitles'),
            Category('MP4', 'Samples that are stored in the MP4 format'),
            Category('General', 'General regression samples')
        ]
        g.db.add_all(categories)
        samples = [
            Sample('sample1', 'ts', 'sample1'),
            Sample('sample2', 'ts', 'sample2')
        ]
        g.db.add_all(samples)
        regression_tests = [
            RegressionTest(1, '-autoprogram -out=ttxt -latin1',
                           InputType.file, OutputType.file, 3, 10),
            RegressionTest(2, '-autoprogram -out=ttxt -latin1 -ucla',
                           InputType.file, OutputType.file, 1, 10)
        ]
        g.db.add_all(regression_tests)
        regression_test_outputs = [
            RegressionTestOutput(1, 'sample_out1', '.srt', ''),
            RegressionTestOutput(2, 'sample_out2', '.srt', '')
        ]
        g.db.add_all(regression_test_outputs)
        test_results = [
            TestResult(1, 1, 200, 0, 0),
            TestResult(1, 2, 601, 0, 0),
            TestResult(2, 1, 200, 200, 0),
            TestResult(2, 2, 601, 0, 0)
        ]
        g.db.add_all(test_results)
        test_result_files = [
            TestResultFile(1, 1, 1, 'sample_out1'),
            TestResultFile(1, 2, 2, 'sample_out2'),
            TestResultFile(2, 1, 1, 'sample_out1'),
            TestResultFile(2, 2, 2, 'sample_out2', 'out2')
        ]
        g.db.add_all(test_result_files)
        dummy_user = User(signup_information['existing_user_name'], signup_information['existing_user_role'],
                          signup_information['existing_user_email'], signup_information['existing_user_pwd'])
        g.db.add(dummy_user)
        g.db.commit()

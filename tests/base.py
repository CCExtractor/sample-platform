import os

from collections import namedtuple
from unittest import mock
from flask_testing import TestCase
from flask import g
from database import create_session
from mod_home.models import GeneralData, CCExtractorVersion
from mod_auth.models import User, Role
from mod_test.models import Test, Fork, TestType, TestPlatform, TestResult, \
    TestResultFile, TestProgress, TestStatus
from mod_regression.models import Category, RegressionTestOutput, RegressionTest, InputType, OutputType
from mod_sample.models import Sample, ForbiddenMimeType, ForbiddenExtension
from mod_customized.models import CustomizedTest, TestFork
from mod_upload.models import Upload, Platform


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
            'SAMPLE_REPOSITORY': 'temp',
            'KVM_LINUX_NAME': 'linux-test',
            'KVM_WINDOWS_NAME': 'window-test',
            'SECRET_KEY': secret_key,
            'CSRF_SESSION_KEY': secret_csrf
            }


def MockRequests(url, data=None, timeout=None):
    if url == "https://api.github.com/repos/test/test_repo/commits/abcdef":
        return MockResponse({}, 200)    
    elif url == "https://api.github.com/user":
        return MockResponse({"login": "test"}, 200)
    elif "https://api.github.com/user" in url:
        return MockResponse({"login": url.split("/")[-1]}, 200)
    elif url == "https://api.github.com/repos/test_owner/test_repo/issues":
        return MockResponse({'number': 1,
                             'title': 'test title',
                             'user': {'login': 'test_user'},
                             'created_at': '2011-04-14T16:00:49Z',
                             'state': 'open'}, 201)
    elif url == "https://api.github.com/repos/test/test_repo/commits/mockWillReturn500":
        return MockResponse({}, 500)
    else:
        return MockResponse({}, 404)


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
        user = namedtuple('user', 'name password email github_token')
        self.user = user(name="test", password="test123",
                         email="test@example.com", github_token="abcdefgh")
        from run import app
        return app

    def setUp(self):
        self.app.preprocess_request()
        g.db = create_session(
            self.app.config['DATABASE_URI'], drop_tables=True)
        commit_name_linux = 'fetch_commit_' + TestPlatform.linux.value
        commit_name_windows = 'fetch_commit_' + TestPlatform.windows.value
        general_data = [GeneralData('last_commit', '1978060bf7d2edd119736ba3ba88341f3bec3323'),
                        GeneralData(commit_name_linux,
                                    '1978060bf7d2edd119736ba3ba88341f3bec3323'),
                        GeneralData(commit_name_windows, '1978060bf7d2edd119736ba3ba88341f3bec3323')]
        g.db.add_all(general_data)
        self.ccextractor_version = CCExtractorVersion('1.2.3', '2013-02-27T19:35:32Z',
                                                      '1978060bf7d2edd119736ba3ba88341f3bec3323')
        g.db.add(self.ccextractor_version)
        fork_url = ('https://github.com/{user}/{repo}.git').format(user=g.github['repository_owner'],
                                                                   repo=g.github['repository'])
        fork = Fork(fork_url)
        g.db.add(fork)
        test = [
            Test(TestPlatform.linux, TestType.pull_request,
                 1, 'master', '1978060bf7d2edd119736ba3ba88341f3bec3323', 1),
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
        upload = [
            Upload(1, 1, 1, Platform.windows),
            Upload(1, 2, 1, Platform.linux)
        ]
        g.db.add_all(upload)
        regression_tests = [
            RegressionTest(1, '-autoprogram -out=ttxt -latin1 -2',
                           InputType.file, OutputType.file, 3, 10),
            RegressionTest(2, '-autoprogram -out=ttxt -latin1 -ucla',
                           InputType.file, OutputType.file, 1, 10)
        ]
        categories[0].regression_tests.append(regression_tests[0])
        categories[2].regression_tests.append(regression_tests[1])
        regression_test_outputs = [
            RegressionTestOutput(1, 'sample_out1', '.srt', ''),
            RegressionTestOutput(2, 'sample_out2', '.srt', '')
        ]
        g.db.add_all(regression_test_outputs)
        test_result_progress = [
            TestProgress(1, TestStatus.preparation, "Test 1 preperation"),
            TestProgress(1, TestStatus.building, "Test 1 building"),
            TestProgress(1, TestStatus.testing, "Test 1 testing"),
            TestProgress(1, TestStatus.completed, "Test 1 completed"),
            TestProgress(2, TestStatus.preparation, "Test 2 preperation"),
            TestProgress(2, TestStatus.building, "Test 2 building"),
            TestProgress(2, TestStatus.testing, "Test 2 testing"),
            TestProgress(2, TestStatus.completed, "Test 2 completed")
        ]
        g.db.add_all(test_result_progress)
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
        forbidden_mime = ForbiddenMimeType('application/javascript')
        forbidden_ext = [
            ForbiddenExtension('js'),
            ForbiddenExtension('com')
        ]
        g.db.add(forbidden_mime)
        g.db.add_all(forbidden_ext)
        g.db.commit()

    def create_login_form_data(self, email, password) -> dict:
        """
        Creates the form data for a login event.
        :return: A dictionary containing the name, password and submit fields.
        """
        return {'email': email, 'password': password, 'submit': True}

    def create_customize_form(self, commit_hash, platform, commit_select=['', ''], regression_test=[1, 2]):
        return {'commit_hash': commit_hash,
                'commit_select': commit_select,
                'platform': platform,
                'regression_test': regression_test,
                'add': True}

    def create_forktest(self, commit_hash, platform, regression_tests=None):
        """
        Create a test on fork based on commit and platform
        """
        from flask import g
        fork_url = ('https://github.com/{user}/{repo}.git').format(
            user=self.user.name, repo=g.github['repository'])
        fork = Fork(fork_url)
        g.db.add(fork)
        g.db.commit()
        test = Test(platform, TestType.commit, fork.id, 'master', commit_hash)
        g.db.add(test)
        g.db.commit()
        user = User.query.filter(User.email == self.user.email).first()
        test_fork = TestFork(user.id, test.id)
        g.db.add(test_fork)
        g.db.commit()
        if regression_tests is not None:
            for regression_test in regression_tests:
                customized_test = CustomizedTest(test.id, regression_test)
                g.db.add(customized_test)
                g.db.commit()

    def complete_forktest(self, test_id, regression_tests):
        from flask import g
        test_result_progress = [
            TestProgress(test_id, TestStatus.preparation, ("Test {0} preperation").format(test_id)),
            TestProgress(test_id, TestStatus.building, ("Test {0} building").format(test_id)),
            TestProgress(test_id, TestStatus.testing, ("Test {0} testing").format(test_id)),
            TestProgress(test_id, TestStatus.completed, ("Test {0} completed").format(test_id)),
        ]
        g.db.add_all(test_result_progress)
        test_results = [
            TestResult(test_id, regression_test, 200, 0, 0) for regression_test in regression_tests
        ]
        g.db.add_all(test_results)
        test_result_files = [
            TestResultFile(test_id, regression_test, regression_test, 'sample_output')
            for regression_test in regression_tests
        ]
        g.db.add_all(test_result_files)
        g.db.commit()

    def create_user_with_role(self, user, email, password, role, github_token=None):
        """
        Create a user with specified user details and role.
        """
        from flask import g
        user = User(self.user.name, email=self.user.email,
                    password=User.generate_hash(self.user.password), role=role, github_token=github_token)
        g.db.add(user)
        g.db.commit()

    def create_random_string(self, length=32):
        import random
        import string
        random_string = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(length)])
        return random_string


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

from collections import namedtuple
from unittest import mock
from flask_testing import TestCase
from flask import g
from database import create_session
from mod_home.models import GeneralData, CCExtractorVersion
from mod_auth.models import User
from mod_ci.models import TestPlatform
from mod_test.models import Test, Fork, TestType, TestPlatform, TestResult, \
    TestResultFile, TestProgress, TestStatus
from mod_regression.models import Category, RegressionTestOutput, RegressionTest, \
    regressionTestLinkTable, InputType, OutputType
from mod_sample.models import Sample


def load_config(file):
    return {'Testing': True, 'DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False, 'SQLALCHEMY_POOL_SIZE': 1,
            'GITHUB_DEPLOY_KEY': 'test_deploy', 'GITHUB_CI_KEY': 'test_ci',
            'GITHUB_TOKEN': '', 'GITHUB_BOT': '',
            'GITHUB_OWNER': 'test_owner', 'GITHUB_REPOSITORY': 'test_repo',
            'SECRET_KEY': 'test124', 'SAMPLE_REPOSITORY': 'temp',
            'KVM_LINUX_NAME': 'linux-test', 'KVM_WINDOWS_NAME': 'window-test'}


def MockRequests(url):
    if url == "https://api.github.com/repos/test/test_repo/commits/abcdef":
        return MockResponse({}, 200)
    elif url == "https://api.github.com/user":
        return MockResponse({"login": "test"}, 200)
    else:
        return MockResponse({}, 404)


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
        test_result_progress = [
            TestProgress(1, TestStatus.preparation, "Test 1 preperation"),
            TestProgress(1, TestStatus.building, "Test 1 building"),
            TestProgress(1, TestStatus.testing, "Test 1 testing"),
            TestProgress(1, TestStatus.completed, "Test 1 testing"),
            TestProgress(2, TestStatus.preparation, "Test 2 preperation"),
            TestProgress(2, TestStatus.building, "Test 2 building"),
            TestProgress(2, TestStatus.testing, "Test 2 testing"),
            TestProgress(2, TestStatus.completed, "Test 2 testing")
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
        g.db.commit()

    def create_login_form_data(self, email, password) -> dict:
        """
        Creates the form data for a login event.
        :return: A dictionary containing the name, password and submit fields.
        """
        return {'email': email, 'password': password, 'submit': True}

    def create_customize_form(self, commit_hash, platform, commit_select=['', '']):
        return {'commit_hash': commit_hash, 'commit_select': commit_select, 'platform': platform, 'add': True}

    def create_forktest(self, commit_hash, platform):
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

    def create_user_with_role(self, user, email, password, role):
        """
        Create a user with specified user details and role.
        """
        from flask import g
        user = User(self.user.name, email=self.user.email,
                    password=User.generate_hash(self.user.password), role=role)
        g.db.add(user)
        g.db.commit()


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

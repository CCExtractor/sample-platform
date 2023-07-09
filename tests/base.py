"""Contains base test case with needed setup and helpers."""

import os
from collections import namedtuple
from contextlib import contextmanager
from unittest import mock

from flask import g
from flask_testing import TestCase
from werkzeug.datastructures import Headers

from database import create_session
from mod_auth.models import Role, User
from mod_customized.models import CustomizedTest, TestFork
from mod_home.models import CCExtractorVersion, GeneralData
from mod_regression.models import (Category, InputType, OutputType,
                                   RegressionTest, RegressionTestOutput,
                                   RegressionTestOutputFiles)
from mod_sample.models import ForbiddenExtension, ForbiddenMimeType, Sample
from mod_test.models import (Fork, Test, TestPlatform, TestProgress,
                             TestResult, TestResultFile, TestStatus, TestType)
from mod_upload.models import Platform, Upload


@contextmanager
def provide_file_at_root(file_name, to_write=None, to_delete=True):
    """Provide file with name file_name at application root."""
    if to_write is None:
        to_write = "DATABASE_URI = 'sqlite:///:memory:'"

    with open(file_name, 'w+') as f:
        f.write(to_write)
    yield
    if to_delete:
        os.remove(file_name)


def load_file_lines(filepath):
    """
    Load lines of the file passed.

    :param filepath: path to the file
    :type filepath: str
    """
    with open(filepath, 'r') as f:
        contents = f.readlines()

    return contents


def mock_decorator(f):
    """Mock login_required decorator."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


def generate_keys():
    """Generate CSRF session and secret keys."""
    from utility import ROOT_DIR
    secret_csrf_path = f"{os.path.join(ROOT_DIR, '')}secret_csrf"
    secret_key_path = f"{os.path.join(ROOT_DIR, '')}secret_key"
    if not os.path.exists(secret_csrf_path):
        secret_csrf_cmd = f"head -c 24 /dev/urandom > {secret_csrf_path}"
        os.system(secret_csrf_cmd)
    if not os.path.exists(secret_key_path):
        secret_key_cmd = f"head -c 24 /dev/urandom > {secret_key_path}"
        os.system(secret_key_cmd)

    open(f"{os.path.join(ROOT_DIR, '')}parse.py", 'w+')

    return {'secret_csrf_path': secret_csrf_path, 'secret_key_path': secret_key_path}


def mock_gcs_client(file):
    """Mock Google Cloud Storage Client object."""
    class gcs_client:
        def bucket(bucket_name):
            class bucket:
                def blob(file_path):
                    class blob:
                        def patch():
                            pass

                        def generate_signed_url(**kwargs):
                            return "https://www.test.com"
                        content_disposition = None
                    return blob
            return bucket
    return gcs_client


def load_config(file):
    """Load start config."""
    key_paths = generate_keys()
    with open(key_paths['secret_key_path'], 'rb') as secret_key_file:
        secret_key = secret_key_file.read()
    with open(key_paths['secret_csrf_path'], 'rb') as secret_csrf_file:
        secret_csrf = secret_csrf_file.read()

    return {
        'Testing': True,
        'DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_POOL_SIZE': 1,
        'GITHUB_DEPLOY_KEY': "test_deploy",
        'GITHUB_CI_KEY': "test_ci",
        'GITHUB_TOKEN': "",
        'GITHUB_BOT': "",
        'GITHUB_OWNER': "test_owner",
        'GITHUB_REPOSITORY': "test_repo",
        'HMAC_KEY': "test_key",
        'MIN_PWD_LEN': 10,
        'MAX_PWD_LEN': 500,
        'SAMPLE_REPOSITORY': "temp",
        'SECRET_KEY': secret_key,
        'CSRF_SESSION_KEY': secret_csrf,
        'ZONE': "test_zone",
        'PROJECT_NAME': "test_zone",
        'GCS_SIGNED_URL_EXPIRY_LIMIT': 720
    }


def mock_api_request_github(url=None, *args, **kwargs):
    """Mock all responses to the GitHub API."""
    if url == "https://api.github.com/meta":
        return MockResponse({'verifiable_password_authentication': True,
                             'github_services_sha': "abcdefg",
                             'hooks': [
                                 "192.30.252.0/22",
                                 "185.199.108.0/22"
                             ]}, 200)
    return MockResponse({}, 404)


# TODO: replace this with something smarter
signup_information = {
    'valid_email': "someone@example.com",
    'existing_user_email': "dummy@example.com",
    'existing_user_name': "dummy",
    'existing_user_pwd': "dummy_pwd",
    'existing_user_role': Role.user
}


def generate_signature(data, private_key):
    """
    Generate signature token of hook request.

    :param data: Signature's data
    :param private_key: Signature's token
    """
    import hashlib
    import hmac
    algorithm = hashlib.__dict__.get('sha1')
    encoded_key = bytes(private_key, 'latin-1')
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return mac.hexdigest()


def generate_git_api_header(event, sig):
    """
    Create header for GitHub API Request, based on header information from https://developer.github.com/webhooks/.

    :param event: Name of the event type that triggered the delivery.
    :param sig: The HMAC hex digest of the response body. The HMAC hex digest is generated
                using the sha1 hash function and the secret as the HMAC key.
    """
    return Headers([
        ('X-GitHub-Event', event),
        ('X-GitHub-Delivery', "72d3162e-cc78-11e3-81ab-4c9367dc0958"),
        ('X-Hub-Signature', f"sha1={sig}"),
        ('User-Agent', "GitHub-Hookshot/044aadd"),
        ('Content-Type', "application/json"),
        ('Content-Length', 6615)
    ])


class BaseTestCase(TestCase):
    """Base setup for all test cases."""

    @mock.patch('google.cloud.storage.Client.from_service_account_json', side_effect=mock_gcs_client)
    @mock.patch('config_parser.parse_config', side_effect=load_config)
    def create_app(self, mock_config, mock_storage_client):
        """Create an instance of the app with the testing configuration."""
        user = namedtuple('user', "name password email github_token")
        self.user = user(name="test", password="test123",
                         email="test@example.com", github_token="abcdefgh")
        from run import app
        return app

    def setUp(self):
        """Set up all entities."""
        self.app.preprocess_request()
        g.db = create_session(
            self.app.config['DATABASE_URI'], drop_tables=True)
        # enable Foreign keys for unit tests
        g.db.execute('pragma foreign_keys=on')

        general_data = [
            GeneralData('last_commit', "1978060bf7d2edd119736ba3ba88341f3bec3323"),
            GeneralData(f'fetch_commit_{TestPlatform.linux.value}', "1978060bf7d2edd119736ba3ba88341f3bec3323"),
            GeneralData(f'fetch_commit_{TestPlatform.windows.value}', "1978060bf7d2edd119736ba3ba88341f3bec3323")
        ]
        g.db.add_all(general_data)
        g.db.commit()

        self.ccextractor_version = CCExtractorVersion(
            "1.2.3", "2013-02-27T19:35:32Z", "1978060bf7d2edd119736ba3ba88341f3bec3323")
        g.db.add(self.ccextractor_version)
        g.db.commit()

        fork = Fork(f"https://github.com/{g.github['repository_owner']}/{g.github['repository']}.git")
        g.db.add(fork)
        g.db.commit()

        dummy_user = User(signup_information['existing_user_name'], signup_information['existing_user_role'],
                          signup_information['existing_user_email'], signup_information['existing_user_pwd'])
        g.db.add(dummy_user)
        g.db.commit()

        commit_hash = '1978060bf7d2edd119736ba3ba88341f3bec3323'
        test = [
            Test(TestPlatform.linux, TestType.pull_request, 1, "pull_request", commit_hash, 1),
            Test(TestPlatform.linux, TestType.pull_request, 1, "pull_request", "abcdefgh", 1)
        ]
        g.db.add_all(test)
        g.db.commit()

        categories = [
            Category("Broken", "Samples that are broken"),
            Category("DVB", "Samples that contain DVB subtitles"),
            Category("DVD", "Samples that contain DVD subtitles"),
            Category("MP4", "Samples that are stored in the MP4 format"),
            Category("General", "General regression samples")
        ]
        g.db.add_all(categories)
        g.db.commit()

        samples = [
            Sample("sample1", "ts", "sample1"),
            Sample("sample2", "ts", "sample2")
        ]
        g.db.add_all(samples)
        g.db.commit()

        upload = [
            Upload(1, 1, 1, Platform.windows),
            Upload(1, 2, 1, Platform.linux)
        ]
        g.db.add_all(upload)
        g.db.commit()

        regression_tests = [
            RegressionTest(1, "-autoprogram -out=ttxt -latin1 -2", InputType.file, OutputType.file, 3, 10),
            RegressionTest(2, "-autoprogram -out=ttxt -latin1 -ucla", InputType.file, OutputType.file, 1, 10)
        ]
        g.db.add_all(regression_tests)
        g.db.commit()

        categories[0].regression_tests.append(regression_tests[0])
        categories[2].regression_tests.append(regression_tests[1])
        regression_test_outputs = [
            RegressionTestOutput(1, "sample_out1", ".srt", ""),
            RegressionTestOutput(2, "sample_out2", ".srt", "")
        ]
        g.db.add_all(regression_test_outputs)
        g.db.commit()

        rtof = RegressionTestOutputFiles("bluedabadee", 2)
        g.db.add(rtof)
        g.db.commit()

        test_result_progress = [
            TestProgress(1, TestStatus.preparation, "Test 1 preparation"),
            TestProgress(1, TestStatus.testing, "Test 1 testing"),
            TestProgress(1, TestStatus.completed, "Test 1 completed"),
            TestProgress(2, TestStatus.preparation, "Test 2 preparation"),
            TestProgress(2, TestStatus.testing, "Test 2 testing"),
            TestProgress(2, TestStatus.completed, "Test 2 completed")
        ]
        g.db.add_all(test_result_progress)
        g.db.commit()

        test_results = [
            TestResult(1, 1, 200, 0, 0),
            TestResult(1, 2, 601, 0, 0),
            TestResult(2, 1, 200, 200, 0),
            TestResult(2, 2, 601, 0, 0)
        ]
        g.db.add_all(test_results)
        g.db.commit()

        test_result_files = [
            TestResultFile(1, 1, 1, "sample_out1"),
            TestResultFile(1, 2, 2, "sample_out2"),
            TestResultFile(2, 1, 1, "sample_out1"),
            TestResultFile(2, 2, 2, "sample_out2", "out2")
        ]
        g.db.add_all(test_result_files)
        g.db.commit()

        forbidden_mime = ForbiddenMimeType("application/javascript")
        forbidden_ext = [
            ForbiddenExtension("js"),
            ForbiddenExtension("com")
        ]
        g.db.add(forbidden_mime)
        g.db.add_all(forbidden_ext)
        g.db.commit()

    @staticmethod
    def create_login_form_data(email, password) -> dict:
        """
        Create the form data for a login event.

        :return: A dictionary containing the name, password and submit fields.
        """
        return {'email': email, 'password': password, 'submit': True}

    @staticmethod
    def create_customize_form(commit_hash, platform, commit_select=None, regression_test=None):
        """Create the request form part."""
        if regression_test is None:
            regression_test = [1, 2]
        if commit_select is None:
            commit_select = ['', '']
        return {
            'commit_hash': commit_hash,
            'commit_select': commit_select,
            'platform': platform,
            'regression_test': regression_test,
            'add': True
        }

    def create_forktest(self, commit_hash, platform, regression_tests=None):
        """Create a test on fork based on commit and platform."""
        from flask import g
        fork_url = f"https://github.com/{self.user.name}/{g.github['repository']}.git"
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

    def create_user_with_role(self, user, email, password, role, github_token=None):
        """Create a user with specified user details and role."""
        from flask import g
        user = User(self.user.name, email=self.user.email,
                    password=User.generate_hash(self.user.password), role=role, github_token=github_token)
        g.db.add(user)
        g.db.commit()

    @staticmethod
    def create_random_string(length=32):
        """Generate random string of ASCII symbols."""
        import random
        import string
        random_string = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(length)])
        return random_string


class MockResponse:
    """A class to mock HTTP response."""

    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        """Mock response json method."""
        return self.json_data

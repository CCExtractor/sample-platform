"""
mod_test Models
===================
In this module, we are trying to maintain all models used
for storing Test information, progress and report.
List of models corresponding to mysql tables: ['Fork' => 'fork',
 'TestProgress' => 'test_progress', 'TestResult' => 'test_result',
 'TestResultFile' => 'test_result_file']
"""

import datetime
import pytz
import os
import string

from sqlalchemy import (Column, Integer, String, Text, ForeignKey,
                        DateTime, orm)
from sqlalchemy.orm import relationship
from tzlocal import get_localzone

from database import Base, DeclEnum
from mod_test.nicediff import diff
from mod_regression.models import RegressionTest


class TestPlatform(DeclEnum):
    linux = "linux", "Linux"
    windows = "windows", "Windows"


class TestType(DeclEnum):
    commit = "commit", "Commit"
    pull_request = "pr", "Pull Request"


class TestStatus(DeclEnum):
    preparation = "preparation", "Preparation"
    building = "building", "Building"
    testing = "testing", "Testing"
    completed = "completed", "Completed"
    canceled = "canceled", "Canceled/Error"

    @staticmethod
    def progress_step(inst):
        try:
            return TestStatus.stages().index(inst)
        except ValueError:
            return -1

    @staticmethod
    def stages():
        return [TestStatus.preparation, TestStatus.building,
                TestStatus.testing, TestStatus.completed]


class Fork(Base):
    __tablename__ = 'fork'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    github = Column(String(256), unique=True)
    tests = relationship('Test', back_populates='fork')

    def __init__(self, github):
        self.github = github

    def __repr__(self):
        return '<Fork {id}>'.format(id=self.id)

    @property
    def github_url(self):
        return self.github.replace('.git', '')

    @property
    def github_name(self):
        return self.github_url.replace('https://github.com/', '')


class Test(Base):
    __tablename__ = 'test'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    platform = Column(TestPlatform.db_type(), nullable=False)
    test_type = Column(TestType.db_type(), nullable=False)
    token = Column(String(64), unique=True)
    fork_id = Column(Integer, ForeignKey('fork.id', onupdate="CASCADE", ondelete="RESTRICT"))
    fork = relationship('Fork', uselist=False, back_populates='tests')
    branch = Column(Text(), nullable=False)
    commit = Column(String(64), nullable=False)
    pr_nr = Column(Integer(), nullable=False, default=0)
    customized_tests = relationship('CustomizedTest', back_populates='test')
    progress = relationship('TestProgress', back_populates='test', order_by='TestProgress.id')
    results = relationship('TestResult', back_populates='test')

    def __init__(self, platform, test_type, fork_id, branch, commit, pr_nr=0, token=None):
        """
        Parametrized constructor for the Test model

        :param platform: The value of the 'platform' field of Test model
        :type platform: TestPlatform
        :param test_type: The value of the 'test_type' field of Test model
        :type test_type: TestType
        :param fork_id: The value of the 'fork_id' field of Test model
        :type fork_id: int
        :param branch: The value of the 'branch' field of Test model
        :type branch: str
        :param commit: The value of the 'commit' field of Test model
        :type commit: str
        :param pr_nr: The value of the 'pr_nr' field of Test model (0 by default)
        :type pr_nr: int
        :param token: The value of the 'token' field of Test model (None by default)
        :type token: str
        """
        self.platform = platform
        self.test_type = test_type
        self.fork_id = fork_id
        self.branch = branch
        self.commit = commit
        self.pr_nr = pr_nr
        if token is None:
            # Auto-generate token
            token = self.create_token(64)
        self.token = token

    def __repr__(self):
        """
        Representation function
        Represent a Test Model by its 'id' Field.

        :return: Returns the string containing 'id' field of the Test model
        :rtype: str
        """
        return '<TestEntry {id}>'.format(id=self.id)

    @property
    def finished(self):
        """
        Verifies if a Test is finished

        :return: Checks if Test is completed or cancelled
        :rtype: boolean
        """
        if len(self.progress) > 0:
            return self.progress[-1].status in [TestStatus.completed, TestStatus.canceled]
        return False

    @property
    def failed(self):
        """
        Verifies if a Test is failed

        :return: Checks if Test is canceled
        :rtype: boolean
        """
        if len(self.progress) > 0:
            return self.progress[-1].status == TestStatus.canceled
        return False

    @property
    def github_link(self):
        """
        Generate github link to view the pr or commit

        :return: url
        :rtype: str
        """
        if self.test_type == TestType.commit:
            test_type = 'commit'
            test_id = self.commit
        else:
            test_type = 'pull'
            test_id = self.pr_nr

        return "{base}/{test_type}/{test_id}".format(base=self.fork.github_url, test_type=test_type, test_id=test_id)

    def progress_data(self):
        """
        Generate progress report for the Test Model

        :return: progress, stages, start and end time of Test Model
        :rtype: dict
        """
        result = {
            'progress': {
                'state': 'error',
                'step': -1
            },
            'stages': TestStatus.stages(),
            'start': '-',
            'end': '-'
        }

        if len(self.progress) > 0:
            result['start'] = self.progress[0].timestamp
            last_status = self.progress[-1]

            if last_status.status in [TestStatus.completed, TestStatus.canceled]:
                result['end'] = last_status.timestamp

            if last_status.status == TestStatus.canceled:
                if len(self.progress) > 1:
                    result['progress']['step'] = TestStatus.progress_step(self.progress[-2].status)

            else:
                result['progress']['state'] = 'ok'
                result['progress']['step'] = TestStatus.progress_step(last_status.status)

        return result

    @staticmethod
    def create_token(length=64):
        """
        Creates a random token for a given length (default: 64).

        :param length: The length of the created token.
        :type length: int
        :return: Randomly generated token
        :rtype: str
        """
        chars = string.ascii_letters + string.digits
        import os
        return ''.join(chars[ord(os.urandom(1)) % len(chars)] for i in range(length))

    def get_customized_regressiontests(self):
        """
        Output all customized regression ids of the test
        return: Regression IDs
        rtype: list
        """
        customized_test = self.customized_tests
        if len(customized_test) != 0:
            regression_ids = [r.regression_id for r in customized_test]
        else:
            regression_ids = [r.id for r in RegressionTest.query.all()]
        return regression_ids


class TestProgress(Base):
    __tablename__ = 'test_progress'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey('test.id', onupdate="CASCADE", ondelete="CASCADE"))
    test = relationship('Test', uselist=False, back_populates='progress')
    status = Column(TestStatus.db_type(), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    message = Column(Text(), nullable=False)

    def __init__(self, test_id, status, message, timestamp=None):
        """
        Parametrized constructor for the TestProgress model

        :param test_id: The value of the 'test_id' field of TestProgress model
        :type test_id: int
        :param status: The value of the 'status' field of TestProgress model
        :type status: TestStatus
        :param message: The value of the 'message' field of TestProgress model
        :type message: str
        :param timestamp: The value of the 'timestamp' field of TestProgress model (None by default)
        :type timestamp: datetime
        """
        self.test_id = test_id
        self.status = status
        tz = get_localzone()

        if timestamp is None:
            timestamp = tz.localize(datetime.datetime.now(), is_dst=None)
            timestamp = timestamp.astimezone(pytz.UTC)

        if timestamp.tzinfo is None:
            timestamp = pytz.utc.localize(timestamp, is_dst=None)

        self.timestamp = timestamp
        self.message = message

    def __repr__(self):
        """
        Representation function
        Represent a TestProgress Model by its 'id' and 'status' Field.

        :return: Returns the string containing 'id' and 'status' field of the Test model
        :rtype: str
        """
        return '<TestStatus {id}: {status}>'.format(id=self.test_id, status=self.status)

    @orm.reconstructor
    def may_the_timezone_be_with_it(self):
        """
        Localize the timestamp to utc
        """
        self.timestamp = pytz.utc.localize(self.timestamp, is_dst=None)


class TestResult(Base):
    __tablename__ = 'test_result'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    test_id = Column(Integer, ForeignKey('test.id', onupdate="CASCADE", ondelete="CASCADE"), primary_key=True)
    test = relationship('Test', uselist=False, back_populates='results')
    regression_test_id = Column(
        Integer, ForeignKey('regression_test.id', onupdate="CASCADE", ondelete="CASCADE"), primary_key=True
    )
    regression_test = relationship('RegressionTest', uselist=False)
    runtime = Column(Integer)  # Runtime in ms
    exit_code = Column(Integer)
    expected_rc = Column(Integer)

    def __init__(self, test_id, regression_test_id, runtime, exit_code, expected_rc):
        """
        Parametrized constructor for the TestResult model

        :param test_id: The value of the 'test_id' field of TestResult model
        :type test_id: int
        :param regression_test_id: The value of the 'regression_test_id' field of TestResult model
        :type regression_test_id: int
        :param runtime: The value of the 'runtime' field of TestResult model
        :type runtime: int
        :param exit_code: The value of the 'exit_code' field of TestResult model
        :type exit_code: int
        :param expected_rc: The value of the 'expected_rc' field of TestResult model
        :type expected_rc: int
        """
        self.test_id = test_id
        self.regression_test_id = regression_test_id
        self.runtime = runtime
        self.exit_code = exit_code
        self.expected_rc = expected_rc

    def __repr__(self):
        """
        Representation function
        Represent a TestResult Model by its 'test_id','expected_rc', 'regression_test_id' and 'status' Field.

        :return: Returns the string containing the 'id' , 'exit_code', 'regression_test_id', 'expected_rc',
        'runtime' field of the TestResult model.
        :rtype: str
        """
        return '<TestResult {tid},{rid}: {code} (expected {expected} in {time} ms>'.format(
            tid=self.test_id,
            rid=self.regression_test_id,
            code=self.exit_code,
            expected=self.expected_rc,
            time=self.runtime
        )


class TestResultFile(Base):
    __tablename__ = 'test_result_file'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    test_id = Column(Integer, ForeignKey('test.id', onupdate="CASCADE", ondelete="CASCADE"), primary_key=True)
    test = relationship('Test', uselist=False)
    regression_test_id = Column(
        Integer, ForeignKey('regression_test.id', onupdate="CASCADE", ondelete="CASCADE"), primary_key=True
    )
    regression_test = relationship('RegressionTest', uselist=False)
    regression_test_output_id = Column(
        Integer, ForeignKey('regression_test_output.id', onupdate="CASCADE", ondelete="CASCADE"), primary_key=True
    )
    regression_test_output = relationship('RegressionTestOutput', uselist=False)
    expected = Column(Text(), nullable=False)  # Keep track of which sample was 'correct' at the time the test ran.
    got = Column(Text(), nullable=True)  # If null/empty, it's equal to the expected version

    def __init__(self, test_id, regression_test_id, regression_test_output_id, expected, got=None):
        """
        Parametrized constructor for the TestResultFile model

        :param test_id: The value of the 'test_id' field of TestResultFile model
        :type test_id: int
        :param regression_test_id: The value of the 'regression_test_id' field of TestResultFile model
        :type regression_test_id: int
        :param regression_test_output_id: The value of the 'regression_test_output_id' field of TestResultFile model
        :type regression_test_id: int
        :param expected: The value of the 'expected' field of TestResultFile model
        :type expected: str
        :param got: The value of the 'got' field of TestResultFile model
        :type got: str
        """
        self.test_id = test_id
        self.regression_test_id = regression_test_id
        self.regression_test_output_id = regression_test_output_id
        self.expected = expected
        self.got = got

    def __repr__(self):
        """
        Representation function
        Represent a TestResultFile Model by its 'test_id',
         'regression_test_id', 'regression_test_output_id' and 'got' Field.

        :return: Returns the string containing the 'id' , 'regression_test_id', 'regression_test_output_id', 'got'
        field of the TestResultFile model
        :rtype: str
        """
        return '<TestResultFile {tid},{rid},{oid}: {equal}>'.format(
            tid=self.test_id,
            rid=self.regression_test_id,
            oid=self.regression_test_output_id,
            equal="Equal" if self.got is None else "Unequal"
        )

    def generate_html_diff(self, base_path):
        """
        Generate diff between correct and test regression_test_output

        :param base_path: The base path for the files location.
        :type base_path: str
        :return: An HTML formatted string.
        :rtype: str
        """
        file_ok = os.path.join(base_path, self.expected + self.regression_test_output.correct_extension)
        file_fail = os.path.join(base_path, self.got + self.regression_test_output.correct_extension)
        lines_ok = open(file_ok, 'U').readlines()
        lines_fail = open(file_fail, 'U').readlines()

        return diff.get_html_diff(lines_ok, lines_fail)

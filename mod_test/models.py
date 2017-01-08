import datetime
import pytz
import os
import string

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, orm
from sqlalchemy.orm import relationship
from tzlocal import get_localzone

from database import Base, DeclEnum
from mod_test.nicediff import diff


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
        return '<Fork %r>' % self.id

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
    fork_id = Column(Integer, ForeignKey('fork.id', onupdate="CASCADE",
                                         ondelete="RESTRICT"))
    fork = relationship('Fork', uselist=False, back_populates='tests')
    branch = Column(Text(), nullable=False)
    commit = Column(String(64), nullable=False)
    pr_nr = Column(Integer(), nullable=False, default=0)
    progress = relationship('TestProgress', back_populates='test',
                            order_by='TestProgress.id')
    results = relationship('TestResult', back_populates='test')

    def __init__(self, platform, test_type, fork_id, branch, commit,
                 pr_nr=0, token=None):
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
        return '<TestEntry %r>' % self.id

    @property
    def finished(self):
        if len(self.progress) > 0:
            return self.progress[-1].status in [
                TestStatus.completed, TestStatus.canceled]
        return False
    
    @property
    def failed(self):
        if len(self.progress) > 0:
            return self.progress[-1].status == TestStatus.canceled
        return False

    @property
    def github_link(self):
        if self.test_type == TestType.commit:
            test_type = 'commit'
            test_id = self.commit
        else:
            test_type = 'pull'
            test_id = self.pr_nr

        return "{base}/{test_type}/{test_id}".format(
            base=self.fork.github_url, test_type=test_type, test_id=test_id)

    def progress_data(self):
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
            if last_status.status in [TestStatus.completed,
                                      TestStatus.canceled]:
                result['end'] = last_status.timestamp
            if last_status.status == TestStatus.canceled:
                if len(self.progress) > 1:
                    result['progress']['step'] = TestStatus.progress_step(
                        self.progress[-2].status)
            else:
                result['progress']['state'] = 'ok'
                result['progress']['step'] = TestStatus.progress_step(
                    last_status.status)
        return result

    @staticmethod
    def create_token(length=64):
        chars = string.ascii_letters + string.digits
        import os
        return ''.join(chars[ord(os.urandom(1)) % len(chars)] for i in
                       range(length))


class TestProgress(Base):
    __tablename__ = 'test_progress'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey('test.id', onupdate="CASCADE",
                                         ondelete="CASCADE"))
    test = relationship('Test', uselist=False, back_populates='progress')
    status = Column(TestStatus.db_type(), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    message = Column(Text(), nullable=False)

    def __init__(self, test_id, status, message, timestamp=None):
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
        return '<TestStatus %r: %r>' % self.test_id, self.status
    
    @orm.reconstructor
    def may_the_timezone_be_with_it(self):
        self.timestamp = pytz.utc.localize(self.timestamp, is_dst=None)


class TestResult(Base):
    __tablename__ = 'test_result'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    test_id = Column(Integer, ForeignKey('test.id', onupdate="CASCADE",
                                         ondelete="CASCADE"),
                     primary_key=True)
    test = relationship('Test', uselist=False, back_populates='results')
    regression_test_id = Column(
        Integer, ForeignKey('regression_test.id', onupdate="CASCADE",
                            ondelete="CASCADE"), primary_key=True
    )
    regression_test = relationship('RegressionTest', uselist=False)
    runtime = Column(Integer)  # Runtime in ms
    exit_code = Column(Integer)
    expected_rc = Column(Integer)

    def __init__(self, test_id, regression_test_id, runtime, exit_code,
                 expected_rc):
        self.test_id = test_id
        self.regression_test_id = regression_test_id
        self.runtime = runtime
        self.exit_code = exit_code
        self.expected_rc = expected_rc

    def __repr__(self):
        return '<TestResult {tid},{rid}: {code} (expected {expected} in ' \
               '{time} ms>'.format(tid=self.test_id,
                                   rid=self.regression_test_id,
                                   code=self.exit_code,
                                   expected=self.expected_rc,
                                   time=self.runtime)


class TestResultFile(Base):
    __tablename__ = 'test_result_file'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    test_id = Column(
        Integer, ForeignKey('test.id', onupdate="CASCADE",
                            ondelete="CASCADE"), primary_key=True
    )
    test = relationship('Test', uselist=False)
    regression_test_id = Column(
        Integer, ForeignKey('regression_test.id', onupdate="CASCADE",
                            ondelete="CASCADE"), primary_key=True
    )
    regression_test = relationship('RegressionTest', uselist=False)
    regression_test_output_id = Column(
        Integer, ForeignKey('regression_test_output.id', onupdate="CASCADE",
                            ondelete="CASCADE"), primary_key=True
    )
    regression_test_output = relationship(
        'RegressionTestOutput', uselist=False)
    expected = Column(Text(), nullable=False)  # If the test changes in the
    # future, we need to keep track of which sample was 'correct' at the
    # time the test ran.
    got = Column(Text(), nullable=True)  # If null/empty, it's equal to the
    #  expected version

    def __init__(self, test_id, regression_test_id,
                 regression_test_output_id, expected, got=None):
        self.test_id = test_id
        self.regression_test_id = regression_test_id
        self.regression_test_output_id = regression_test_output_id
        self.expected = expected
        self.got = got

    def __repr__(self):
        return '<TestResultFile {tid},{rid},{oid}: {equal}>'.format(
            tid=self.test_id, rid=self.regression_test_id,
            oid=self.regression_test_output_id,
            equal="Equal" if self.got is None else "Unequal"
        )

    def generate_html_diff(self, base_path):
        # TODO: use difflib.SequenceMatcher and generate own HTML diff
        file_ok = os.path.join(
            base_path,
            self.expected + self.regression_test_output.correct_extension)
        file_fail = os.path.join(
            base_path,
            self.got + self.regression_test_output.correct_extension)
        lines_ok = open(file_ok, 'U').readlines()
        lines_fail = open(file_fail, 'U').readlines()

        return diff.get_html_diff(lines_ok, lines_fail)

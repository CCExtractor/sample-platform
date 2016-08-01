import datetime
import string

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base, DeclEnum
from mod_auth.models import User


class TestPlatform(DeclEnum):
    linux = "linux", "Linux"
    windows = "windows", "Windows"


class TestType(DeclEnum):
    commit = "commit", "Commit"
    pull_request = "pr", "Pull Request"


class TestStatus(DeclEnum):
    queued = "queued", "Queued"
    preparation = "preparation", "Preparation"
    building = "building", "Building"
    testing = "testing", "Testing"
    completed = "completed", "Completed"
    canceled = "canceled", "Canceled"


class Fork(Base):
    __tablename__ = 'fork'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    github = Column(String(256), unique=True)
    tests = relationship('Test', back_populates='fork')


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
    progress = relationship('TestProgress', back_populates='test',
                            order_by='TestProgress.id')
    result = relationship('TestResult', back_populates='test',
                          uselist=False)
    result_files = relationship('TestResultFile', back_populates='test')

    def __init__(self, platform, test_type, fork_id, branch, commit,
                 token=None):
        self.platform = platform
        self.test_type = test_type
        self.fork_id = fork_id
        self.branch = branch
        self.commit = commit
        if token is None:
            # Auto-generate token
            token = self.create_token(64)
        self.token = token

    def __repr__(self):
        return '<TestEntry %r>' % self.id

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
    timestamp = Column(DateTime(), nullable=False)
    message = Column(Text(), nullable=False)

    def __init__(self, test_id, status, message, timestamp=None):
        self.test_id = test_id
        self.status = status
        if timestamp is None:
            timestamp = datetime.datetime.now()
        self.timestamp = timestamp
        self.message = message

    def __repr__(self):
        return '<TestStatus %r: %r>' % self.test_id, self.status


class TestResult(Base):
    __tablename__ = 'test_result'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    test_id = Column(Integer, ForeignKey('test.id', onupdate="CASCADE",
                                         ondelete="CASCADE"),
                     primary_key=True)
    test = relationship('Test', uselist=False, back_populates='result')
    regression_test_id = Column(
        Integer, ForeignKey('regression_test.id', onupdate="CASCADE",
                            ondelete="CASCADE"), primary_key=True
    )
    regression_test = relationship('RegressionTest', uselist=False)
    runtime = Column(Integer)  # Runtime in ms
    exit_code = Column(Integer)

    def __init__(self, test_id, regression_test_id, runtime, exit_code):
        self.test_id = test_id
        self.regression_test_id = regression_test_id
        self.runtime = runtime
        self.exit_code = exit_code

    def __repr__(self):
        return '<TestResult {tid},{rid}: {code} in {time} ms>'.format(
            tid=self.test_id, rid=self.regression_test_id,
            code=self.exit_code, time=self.runtime)


class TestResultFile(Base):
    __tablename__ = 'test_result_file'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    test_id = Column(
        Integer, ForeignKey('test.id', onupdate="CASCADE",
                            ondelete="CASCADE"), primary_key=True
    )
    test = relationship('Test', uselist=False, back_populates='result_files')
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

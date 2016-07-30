import datetime
import string

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
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

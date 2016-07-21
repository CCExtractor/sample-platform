import string

from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from database import Base, DeclEnum


class Platform(DeclEnum):
    linux = "linux", "Linux"
    windows = "windows", "Windows"
    mac = "mac", "Mac"
    bsd = "bsd", "BSD"


class Upload(Base):
    __tablename__ = 'upload'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(
        'user.id', onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)
    sample_id = Column(Integer, ForeignKey(
        'sample.id', onupdate="CASCADE", ondelete="CASCADE"))
    sample = relationship('Sample', uselist=False, back_populates='upload')
    version_id = Column(Integer, ForeignKey(
        'ccextractor_version.id', onupdate="CASCADE", ondelete="RESTRICT"))
    version = relationship('CCExtractorVersion', uselist=False)
    platform = Column(Platform.db_type(), nullable=False)
    parameters = Column(Text(), nullable=False)
    notes = Column(Text(), nullable=False)

    def __init__(self, user_id, sample_id, version_id, platform,
                 parameters='', notes=''):
        self.user_id = user_id
        self.sample_id = sample_id
        self.version_id = version_id
        self.platform = platform
        self.parameters = parameters
        self.notes = notes

    def __repr__(self):
        return '<Upload %r>' % self.id


class QueuedSample(Base):
    __tablename__ = 'upload_queue'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sha = Column(String(128), unique=True)
    extension = Column(String(64), nullable=False)  # contains the dot!
    original_name = Column(Text(), nullable=False)
    user_id = Column(Integer, ForeignKey(
        'user.id', onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)

    def __init__(self, sha, extension, original_name, user_id):
        self.sha = sha
        self.extension = extension
        self.original_name = original_name
        self.user_id = user_id

    @property
    def filename(self):
        return "{sha}{extension}".format(
            sha=self.sha, extension=self.extension)


class UploadLog(Base):
    __tablename__ = 'upload_log'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    message = Column(Text(), nullable=False)
    user_id = Column(Integer, ForeignKey(
        'user.id', onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)

    def __init__(self, message, user_id):
        self.message = message
        self.user_id = user_id


class FTPActive(DeclEnum):
    disabled = '0', 'Disabled'
    enabled = '1', 'Enabled'


class FTPCredentials(Base):
    __tablename__ = 'ftpd'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    user_id = Column(Integer, ForeignKey(
        'user.id', onupdate="CASCADE", ondelete="RESTRICT"), primary_key=True)
    user = relationship('User', uselist=False)
    user_name = Column(String(32), nullable=False)
    status = Column(FTPActive.db_type(), nullable=False)
    # Password is not encrypted/hashed, but it's random generated and
    # unchangeable, so there is no real risk in case of a data leak.
    password = Column(String(64), nullable=False)
    dir = Column(String(128), nullable=False)
    ip_access = Column(String(16), nullable=False)
    quota_files = Column(Integer, nullable=False)

    def __init__(self, user_id, user_name=None, status=FTPActive.enabled,
                 password=None, home_directory=None, ip_access="*",
                 quota_files=20):
        self.user_id = user_id
        self.status = status
        self.ip_access = ip_access
        self.quota_files = quota_files

        if user_name is None:
            user_name = self._create_random_string(32)
        self.user_name = user_name

        if password is None:
            password = self._create_random_string(64)
        self.password = password

        if home_directory is None:
            home_directory = '/home/{uid}'.format(uid=user_id)
        self.dir = home_directory

    @staticmethod
    def _create_random_string(length=16):
        chars = string.ascii_letters + string.digits
        import os
        return ''.join(chars[ord(os.urandom(1)) % len(chars)] for i in
                       range(length))

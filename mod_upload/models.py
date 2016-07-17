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
    extension = Column(String(64), nullable=False)
    original_name = Column(Text(), nullable=False)
    user_id = Column(Integer, ForeignKey(
        'user.id', onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)

    def __init__(self, sha, extension, original_name, user_id):
        self.sha = sha
        self.extension = extension
        self.original_name = original_name
        self.user_id = user_id


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

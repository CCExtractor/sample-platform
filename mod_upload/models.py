"""
Maintain all models used for storing Test information, progress and report.

List of models corresponding to mysql tables:
    [
        'Upload' => 'upload',
        'QueuedSample' => 'upload_queue',
        'UploadLog' => 'upload_log',
        'FTPCredentials' => 'ftpd'
    ]
"""

import string
from typing import Any, Dict, Tuple, Type

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

import database
from database import Base, DeclEnum


class Platform(DeclEnum):
    """Enum for platform data."""

    linux = "linux", "Linux"
    windows = "windows", "Windows"
    mac = "mac", "Mac"
    bsd = "bsd", "BSD"


class Upload(Base):
    """Model to manage and store upload."""

    __tablename__ = 'upload'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id', onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)
    sample_id = Column(Integer, ForeignKey('sample.id', onupdate="CASCADE", ondelete="CASCADE"))
    sample = relationship('Sample', uselist=False, back_populates='upload')
    version_id = Column(Integer, ForeignKey('ccextractor_version.id', onupdate="CASCADE", ondelete="RESTRICT"))
    version = relationship('CCExtractorVersion', uselist=False)
    platform = Column(Platform.db_type(), nullable=False)
    parameters = Column(Text(), nullable=False)
    notes = Column(Text(), nullable=False)

    def __init__(self, user_id, sample_id, version_id, platform, parameters='', notes='') -> None:
        """
        Parametrized constructor for the Upload model.

        :param user_id: The value of the 'user_id' field of Upload model
        :type user_id: int
        :param sample_id: The value of the 'sample_id' field of Upload model
        :type sample_id: int
        :param version_id: The value of the 'version_id' field of Upload model
        :type version_id: int
        :param platform: The value of the 'platform' field of Upload model
        :type platform: Platform
        :param parameters: The value of the 'parameters' field of Upload model (empty by default)
        :type parameters: str
        :param notes: The value of the 'notes' field of Upload model (empty by default)
        :type notes: str
        """
        self.user_id = user_id
        self.sample_id = sample_id
        self.version_id = version_id
        self.platform = platform
        self.parameters = parameters
        self.notes = notes

    def __repr__(self) -> str:
        """
        Represent a Upload Model by its 'id' Field.

        :return: Returns the string containing 'id' field of the Upload model
        :rtype: str
        """
        return f"<Upload {self.id}>"


class QueuedSample(Base):
    """Model to manage and store sample queue."""

    __tablename__ = 'upload_queue'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sha = Column(String(128), unique=True)
    extension = Column(String(64), nullable=False)  # contains the dot!
    original_name = Column(Text(), nullable=False)
    user_id = Column(Integer, ForeignKey(
        'user.id', onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)

    def __init__(self, sha, extension, original_name, user_id) -> None:
        """
        Parametrized constructor for the QueuedSample model.

        :param sha: The value of the 'sha' field of QueuedSample model
        :type sha: str
        :param extension: The value of the 'extension' field of QueuedSample model
        :type extension: str
        :param original_name: The value of the 'original_name' field of QueuedSample model
        :type original_name: str
        :param user_id: The value of the 'user_id' field of QueuedSample model (empty by default)
        :type user_id: int
        """
        self.sha = sha
        self.extension = extension
        self.original_name = original_name
        self.user_id = user_id

    @property
    def filename(self):
        """
        Return filename with the format sha.extension.

        :return: Returns the string containing 'sha' and 'extension' field of the QueuedSample model
        :rtype: str
        """
        return f"{self.sha}{self.extension}"


class UploadLog(Base):
    """Model to maintain upload logs."""

    __tablename__ = 'upload_log'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    message = Column(Text(), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id', onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)

    def __init__(self, message, user_id) -> None:
        """
        Parametrized constructor for the UploadLog model.

        :param message: The value of the 'message' field of UploadLog model
        :type message: str
        :param user_id: The value of the 'user_id' field of UploadLog model
        :type user_id: str
        """
        self.message = message
        self.user_id = user_id


class FTPActive(DeclEnum):
    """Enum to set FTP status."""

    disabled = '0', 'Disabled'
    enabled = '1', 'Enabled'


class FTPCredentials(Base):
    """Model to manage and store FTP credential."""

    __tablename__ = 'ftpd'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    user_id = Column(Integer, ForeignKey('user.id', onupdate="CASCADE", ondelete="RESTRICT"), primary_key=True)
    user = relationship('User', uselist=False)
    user_name = Column(String(32), nullable=False)
    status = Column(FTPActive.db_type(), nullable=False)
    # Password is not encrypted/hashed, but it's random generated and unchangeable, so there is no real risk in case
    # of a data leak.
    password = Column(String(64), nullable=False)
    dir = Column(String(128), nullable=False)
    ip_access = Column(String(16), nullable=False)
    quota_files = Column(Integer, nullable=False)
    uid = Column(Integer, nullable=False, default=2015)
    gid = Column(Integer, nullable=False, default=2015)

    def __init__(self, user_id, user_name=None, status=FTPActive.enabled, password=None, home_directory=None,
                 ip_access="*", quota_files=20) -> None:
        """
        Parametrized constructor for the FTPCredentials model.

        :param user_id: The value of the 'user_id' field of FTPCredentials model
        :type user_id: int
        :param user_name: The value of the 'user_name' field of FTPCredentials model (None by default)
        :type user_name: str
        :param status: The value of the 'status' field of FTPCredentials model (FTPActive.enabled by default)
        :type status: FTPActive
        :param password: The value of the 'password' field of FTPCredentials model (None by default)
        :type password: str
        :param home_directory: The value of the 'home_directory' field of FTPCredentials model (None by default)
        :type home_directory: str
        :param ip_access: The value of the 'ip_access' field of FTPCredentials model ("*" by default)
        :type ip_access: str
        :param quota_files: The value of the 'quota_files' field of FTPCredentials model (20 by default)
        :type quota_files: int
        """
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
            home_directory = f'/repository/ftpd/{user_id}'
        self.dir = home_directory

    @staticmethod
    def _create_random_string(length=16) -> str:
        """
        Create a random string with a given length (a default of 16).

        :param length: The length of the random string to create.
        :type length: int
        :return: A string of the given length containing only letters and digits.
        :rtype: str
        """
        chars = string.ascii_letters + string.digits
        import os
        return ''.join(chars[ord(os.urandom(1)) % len(chars)] for i in range(length))

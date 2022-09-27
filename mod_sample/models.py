"""Maintain database models regarding various sample, ExtraFile, ForbiddenExtension, ForbiddenMimeType, Issue."""

from datetime import datetime
from typing import Any, Dict, Type

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

import database
from database import Base, DeclEnum


def get_extension(extension: str) -> str:
    """
    Return the extension with a dot.

    :param extension: The extension to format.
    :type extension: str
    :return: Return the extension with a dot or empty if no extension.
    :rtype: str
    """
    return ("." + extension) if len(extension) > 0 else ""


class Sample(Base):
    """Model to store and manage sample."""

    __tablename__ = 'sample'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sha = Column(String(128), unique=True)
    extension = Column(String(64), nullable=False)
    original_name = Column(Text(), nullable=False)
    extra_files = relationship('ExtraFile', back_populates='sample')
    tests = relationship('RegressionTest', back_populates='sample')
    upload = relationship('Upload', uselist=False, back_populates='sample')

    def __init__(self, sha, extension, original_name) -> None:
        """
        Parametrized constructor for the Sample model.

        :param sha: The value of the 'sha' field of Sample model
        :type sha: str
        :param extension: The value of the 'extension' field of Sample model
        :type extension: str
        :param original_name: The value of the 'original_name' field of Sample model
        :type original_name: str
        """
        self.sha = sha
        self.extension = extension
        self.original_name = original_name

    def __repr__(self) -> str:
        """
        Represent a Sample Model by its 'sha' Field.

        :return: Returns the string containing 'sha' field of the Category model
        :rtype: str
        """
        return f"<Sample {self.sha}>"

    @property
    def filename(self):
        """Return the full filename of the sample."""
        return f'{self.sha}{get_extension(self.extension)}'


class ExtraFile(Base):
    """Model to store and manage sample extra data."""

    __tablename__ = 'sample_extra'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey('sample.id', onupdate="CASCADE", ondelete="CASCADE"))
    sample = relationship('Sample', uselist=False, back_populates='extra_files')

    original_name = Column(Text(), nullable=False)
    extension = Column(String(64), nullable=False)

    def __init__(self, sample_id, extension, original_name) -> None:
        """
        Parametrized constructor for the ExtraFile model.

        :param sample_id: The value of the 'sha' field of ExtraFile model
        :type sample_id: int
        :param extension: The value of the 'extension' field of ExtraFile model
        :type extension: str
        :param original_name: The value of the 'original_name' field of ExtraFile model
        :type original_name: str
        """
        self.sample_id = sample_id
        self.extension = extension
        self.original_name = original_name

    def __repr__(self) -> str:
        """
        Represent a ExtraFile Model by its 'sample_id' Field.

        :return: Returns the string containing 'sha' field of the ExtraFile model
        :rtype: str
        """
        return f"<Sample extra for {self.sample_id}>"

    @property
    def short_name(self, length=5):
        """
        Return the short name of an additional file.

        :param length: How many characters of the hash should be retained for the short name? Defaults to 5.
        :type length: int
        :return: A short name consisting of the first x characters of the hash, the id and the file extension.
        :rtype: str
        """
        return f"{self.sample.sha[:length]}_{self.id}.{get_extension(self.extension)}"

    @property
    def filename(self):
        """
        Return filename.

        :return: Returns the full name of the file using the hash, id and file extension.
        :rtype: str
        """
        return f"{self.sample.sha}_{self.id}{get_extension(self.extension)}"


class ForbiddenExtension(Base):
    """Model to store and manage forbidden extensions."""

    __tablename__ = 'extension_forbidden'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    extension = Column(String(32), primary_key=True)

    def __init__(self, extension) -> None:
        """
        Parametrized constructor for the ForbiddenExtension model.

        :param extension: The value of the 'extension' field of ForbiddenExtension model
        :type extension: str
        """
        self.extension = extension

    def __repr__(self) -> str:
        """
        Represent a ForbiddenExtension Model by its 'extension' Field.

        :return: Returns the string containing 'extension' field of the ForbiddenExtension model
        :rtype: str
        """
        return f"<Forbidden extension {self.extension}>"


class ForbiddenMimeType(Base):
    """Model to store and manage forbidden mime-type."""

    __tablename__ = 'mimetype_forbidden'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    mimetype = Column(String(64), primary_key=True)

    def __init__(self, mime_type) -> None:
        """
        Parametrized constructor for the ForbiddenMimeType model.

        :param mime_type: The value of the 'mime-type' field of ForbiddenMimeType model
        :type mime_type: str
        """
        self.mimetype = mime_type

    def __repr__(self) -> str:
        """
        Represent a ForbiddenMimeType Model by its 'mime-type' Field.

        :return: Returns the string containing 'mime-type' field of the ForbiddenMimeType model
        :rtype: str
        """
        return f"<Forbidden MimeType {self.mimetype}>"


class Issue(Base):
    """Model to store and manage sample issue."""

    __tablename__ = 'sample_issue'
    __table_args__ = {'mysql_engine': 'InnoDB'}

    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey('sample.id', onupdate="CASCADE",
                                           ondelete="CASCADE"))
    sample = relationship('Sample', uselist=False)
    issue_id = Column(Integer, nullable=False)
    title = Column(Text(), nullable=False)
    user = Column(Text(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(Text(), nullable=False)

    def __init__(self, sample_id, issue_id, date, title, user, status) -> None:
        """
        Parametrized constructor for the Issue model.

        :param sample_id: The value of the 'sample_id' field of Issue model
        :type sample_id: int
        :param issue_id: The value of the 'issue_id' field of Issue model
        :type issue_id: int
        :param date: The value of the 'created_at' field of Issue model
        :type date: datetime
        :param title: The value of the 'title' field of Issue model
        :type title: str
        :param user: The value of the 'user' field of Issue model
        :type user: str
        :param status: The value of the 'status' field of Issue model
        :type status: str
        """
        self.sample_id = sample_id
        self.issue_id = issue_id
        self.created_at = datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ')
        self.title = title
        self.user = user
        self.status = status

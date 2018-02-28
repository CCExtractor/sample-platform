"""
mod_sample Models
===================
In this module, we are trying to maintain database regarding various
sample, ExtraFile, ForbiddenExtension, ForbiddenMimeType, Issue
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base, DeclEnum
from datetime import datetime


class Sample(Base):
    __tablename__ = 'sample'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sha = Column(String(128), unique=True)
    extension = Column(String(64), nullable=False)
    original_name = Column(Text(), nullable=False)
    extra_files = relationship('ExtraFile', back_populates='sample')
    tests = relationship('RegressionTest', back_populates='sample')
    upload = relationship('Upload', uselist=False, back_populates='sample')

    def __init__(self, sha, extension, original_name):
        """
        Parametrized constructor for the Sample model

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

    def __repr__(self):
        """
        Representation function
        Represent a Sample Model by its 'sha' Field.

        :return: Returns the string containing 'sha' field of the Category model
        :rtype: str
        """
        return '<Sample {hash}>'.format(hash=self.sha)

    @property
    def filename(self):
        """
        Return the full filename of the sample
        """
        extension = ("." + self.extension) if len(self.extension) > 0 else ""
        return "{sha}{extension}".format(sha=self.sha, extension=extension)


class ExtraFile(Base):
    __tablename__ = 'sample_extra'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey('sample.id', onupdate="CASCADE", ondelete="CASCADE"))
    sample = relationship('Sample', uselist=False, back_populates='extra_files')

    original_name = Column(Text(), nullable=False)
    extension = Column(String(64), nullable=False)

    def __init__(self, sample_id, extension, original_name):
        """
        Parametrized constructor for the ExtraFile model

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

    def __repr__(self):
        """
        Representation function
        Represent a ExtraFile Model by its 'sample_id' Field.

        :return: Returns the string containing 'sha' field of the ExtraFile model
        :rtype: str
        """
        return '<Sample extra for {id}>'.format(id=self.sample_id)

    @property
    def short_name(self, length=5):
        """
        Function to return the short name of an additional file.

        :param length: How many characters of the hash should be retained for the short name? Defaults to 5.
        :type length: int
        :return: A short name consisting of the first x characters of the hash, the id and the file extension.
        :rtype: str
        """
        return "{short}_{id}.{extension}".format(
            short=self.sample.sha[:length], id=self.id,
            extension=self.extension
        )

    @property
    def filename(self):
        """
        Function to return filename

        :return: Returns the full name of the file using the hash, id and file extension.
        :rtype: str
        """
        extension = ("." + self.extension) if len(self.extension) > 0 else ""
        return "{sha}_{id}{extension}".format(sha=self.sample.sha, id=self.id,  extension=extension)


class ForbiddenExtension(Base):
    __tablename__ = 'extension_forbidden'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    extension = Column(String(32), primary_key=True)

    def __init__(self, extension):
        """
        Parametrized constructor for the ForbiddenExtension model

        :param extension: The value of the 'extension' field of ForbiddenExtension model
        :type extension: str
        """
        self.extension = extension

    def __repr__(self):
        """
        Representation function
        Represent a ForbiddenExtension Model by its 'extension' Field.

        :return: Returns the string containing 'extension' field of the ForbiddenExtension model
        :rtype: str
        """
        return '<Forbidden extension {extension}>'.format(extension=self.extension)


class ForbiddenMimeType(Base):
    __tablename__ = 'mimetype_forbidden'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    mimetype = Column(String(64), primary_key=True)

    def __init__(self, mimetype):
        """
        Parametrized constructor for the ForbiddenMimeType model

        :param mimetype: The value of the 'mimetype' field of ForbiddenMimeType model
        :type mimetype: str
        """
        self.mimetype = mimetype

    def __repr__(self):
        """
        Representation function
        Represent a ForbiddenMimeType Model by its 'mimetype' Field.

        :return: Returns the string containing 'mimetype' field of the ForbiddenMimeType model
        :rtype: str
        """
        return '<Forbidden MimeType {mime}>'.format(mime=self.mimetype)


class Issue(Base):
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

    def __init__(self, sample_id, issue_id, date, title, user, status):
        """
        Parametrized constructor for the Issue model

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

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
        self.sha = sha
        self.extension = extension
        self.original_name = original_name

    def __repr__(self):
        return '<Sample %r>' % self.sha

    @property
    def filename(self):
        extension = ("." + self.extension) if len(self.extension) > 0 else ""
        return "{sha}{extension}".format(sha=self.sha, extension=extension)


class ExtraFile(Base):
    __tablename__ = 'sample_extra'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey('sample.id', onupdate="CASCADE",
                                           ondelete="CASCADE"))
    sample = relationship('Sample', uselist=False,
                          back_populates='extra_files')

    original_name = Column(Text(), nullable=False)
    extension = Column(String(64), nullable=False)

    def __init__(self, sample_id, extension, original_name):
        self.sample_id = sample_id
        self.extension = extension
        self.original_name = original_name

    def __repr__(self):
        return '<Sample extra for %r>' % self.sample_id

    @property
    def short_name(self, length=5):
        return "{short}_{id}.{extension}".format(
            short=self.sample.sha[:length], id=self.id,
            extension=self.extension
        )

    @property
    def filename(self):
        extension = ("." + self.extension) if len(self.extension) > 0 else ""
        return "{sha}_{id}{extension}".format(
            sha=self.sample.sha, id=self.id,  extension=extension
        )


class ForbiddenExtension(Base):
    __tablename__ = 'extension_forbidden'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    extension = Column(String(32), primary_key=True)

    def __init__(self, extension):
        self.extension = extension

    def __repr__(self):
        return '<Forbidden extension %r>' % self.extension


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
        self.sample_id = sample_id
        self.issue_id = issue_id
        self.created_at = datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ')
        self.title = title
        self.user = user
        self.status = status

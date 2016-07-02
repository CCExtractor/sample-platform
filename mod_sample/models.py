from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from database import Base, DeclEnum
from mod_regression.models import RegressionTest


class Sample(Base):
    __tablename__ = 'sample'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sha = Column(String(128), unique=True)
    extension = Column(String(64), nullable=False)
    original_name = Column(Text(), nullable=False)
    extra_files = relationship(ExtraFile)
    tests = relationship(RegressionTest, back_populates=RegressionTest.sample)

    def __init__(self, sha, extension, original_name):
        self.sha = sha
        self.extension = extension
        self.original_name = original_name

    def __repr__(self):
        return '<Sample %r>' % self.sha


class ExtraFile(Base):
    __tablename__ = 'sample_extra'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey('sample.id', onupdate="CASCADE",
                                           ondelete="CASCADE"))
    sample = relationship(Sample, back_populates=Sample.extra_files)

    original_name = Column(Text(), nullable=False)
    extension = Column(String(64), nullable=False)

    def __init__(self, sample_id, extension, original_name):
        self.sample_id = sample_id
        self.extension = extension
        self.original_name = original_name

    def __repr__(self):
        return '<Sample extra for %r>' % self.sample_id


class ForbiddenExtension(Base):
    __tablename__ = 'extension_forbidden'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    extension = Column(String(32), primary_key=True)

    def __init__(self, extension):
        self.extension = extension

    def __repr__(self):
        return '<Forbidden extension %r>' % self.extension

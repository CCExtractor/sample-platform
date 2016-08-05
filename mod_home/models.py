from sqlalchemy import Column, Integer, String, Text, Date

from database import Base, DeclEnum


class CCExtractorVersion(Base):
    __tablename__ = 'ccextractor_version'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    version = Column(String(10), unique=True)
    released = Column(Date(), unique=True)
    commit = Column(String(64), unique=True)

    def __init__(self, version, released, commit):
        self.version = version
        self.released = released
        self.commit = commit

    def __repr__(self):
        return '<Version %r>' % self.version


class GeneralData(Base):
    __tablename__ = 'general_data'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True)
    value = Column(Text(), nullable=False)

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __repr__(self):
        return '<GeneralData %r: %r>' % (self.key, self.value)

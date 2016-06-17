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

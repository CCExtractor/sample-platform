import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship

from database import Base
from mod_test.models import Test, TestPlatform


class Kvm(Base):
    __tablename__ = 'kvm'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    name = Column(String(64), primary_key=True)
    test_id = Column(Integer, ForeignKey(Test.id, onupdate="CASCADE",
                                         ondelete="RESTRICT"))
    test = relationship('Test', uselist=False)
    timestamp = Column(DateTime(), nullable=False)

    def __init__(self, name, test_id, timestamp=None):
        self.name = name
        self.test_id = test_id
        if timestamp is None:
            timestamp = datetime.datetime.now()
        self.timestamp = timestamp

    def __repr__(self):
        return '<KVM test running: %r>' % self.test_id


class MaintenanceMode(Base):
    __tablename__ = 'maintenance_mode'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    platform = Column(TestPlatform.db_type(), nullable=False)
    disabled = Column(Boolean, nullable=False, default=False)

    def __init__(self, platform, mode):
        self.platform = platform
        self.disabled = mode

    def __repr__(self):
        return '<Platform {platform}, maintenance {status}>'.format(
            platform=self.platform.description, status=self.disabled)

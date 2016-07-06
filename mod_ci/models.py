import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from database import Base
from mod_test.models import Test


class Kvm(Base):
    __tablename__ = 'kvm'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    name = Column(String(64), primary_key=True)
    test_id = Column(Integer, ForeignKey(Test.id, onupdate="CASCADE",
                                         ondelete="RESTRICT"))
    test = relationship('Test')
    timestamp = Column(DateTime(), nullable=False)

    def __init__(self, name, test_id, timestamp=None):
        self.name = name
        self.test_id = test_id
        if timestamp is None:
            timestamp = datetime.datetime.now()
        self.timestamp = timestamp

    def __repr__(self):
        return '<KVM test running: %r>' % self.test_id

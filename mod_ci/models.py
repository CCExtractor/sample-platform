import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from database import Base
from mod_test.models import Test


class Kvm(Base):
    """
    Store all the tests in progress
    """
    __tablename__ = 'kvm'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    name = Column(String(64), primary_key=True)
    test_id = Column(Integer, ForeignKey(Test.id, onupdate="CASCADE",
                                         ondelete="RESTRICT"))
    test = relationship('Test', uselist=False)
    timestamp = Column(DateTime(), nullable=False)

    def __init__(self, name, test_id, timestamp=None):
        """
        Constructor for Kvm class

        :param name: The value of the 'name' field of Kvm model
        :type name: str
        :param test_id: The value of the 'test_id' field of Kvm model
        :type test_id: integer
        :param timestamp: the datetime when test is started
        :type timestamp: datetime
        """
        self.name = name
        self.test_id = test_id
        if timestamp is None:
            timestamp = datetime.datetime.now()
        self.timestamp = timestamp

    def __repr__(self):
        """
        Representation function
        Represent a Kvm Model by its 'test_id' Field.
        :return <KCM test running: test_id>: Returns the 'test_id'
            field of Kvm Model
        :rtype: string
        """
        return '<KVM test running: %r>' % self.test_id

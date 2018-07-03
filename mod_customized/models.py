"""
mod_customized Models
===================
In this module, we are trying to maintain database regarding tests run
by users.
List of models corresponding to mysql tables: ['GeneralData' => 'general_data']
"""
from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey
from sqlalchemy.orm import relationship

from database import Base, DeclEnum
from mod_test.models import Test, TestPlatform
from mod_auth.models import User


class TestFork(Base):
    __tablename__ = 'test_fork'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(User.id, onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)
    test_id = Column(Integer, ForeignKey(Test.id, onupdate="CASCADE", ondelete="RESTRICT"))
    test = relationship('Test', uselist=False)

    def __init__(self, user_id, test_id):
        """
        Parametrized constructor for the CCExtractorVersion model

        :param user_id: The value of the 'user_id' field of
         TestFork model
        :type version: int
        :param test_id: The value of the 'test_id' field of
         TestFork model
        :type test_id: int
        """
        self.user_id = user_id
        self.test_id = test_id

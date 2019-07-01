"""
Maintain models for database operations regarding custom tests run by users.

List of models corresponding to mysql tables: ['TestFork' => 'test_fork',
                                               'CustomizedTest' => 'customized_test']
"""

from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from database import Base
from mod_auth.models import User
from mod_regression.models import RegressionTest
from mod_test.models import Test
import mod_auth.models
import mod_regression.models
import mod_test.models
from typing import Any
from typing import Dict
from typing import Type


class TestFork(Base):
    """Model to manage custom [set of] test by user."""

    __tablename__ = 'test_fork'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(User.id, onupdate="CASCADE", ondelete="RESTRICT"))
    user = relationship('User', uselist=False)
    test_id = Column(Integer, ForeignKey(Test.id, onupdate="CASCADE", ondelete="RESTRICT"))
    test = relationship('Test', uselist=False)

    def __init__(self, user_id, test_id) -> None:
        """
        Parametrized constructor for the CCExtractorVersion model.

        :param user_id: The value of the 'user_id' field of
         TestFork model
        :type version: int
        :param test_id: The value of the 'test_id' field of
         TestFork model
        :type test_id: int
        """
        self.user_id = user_id
        self.test_id = test_id


class CustomizedTest(Base):
    """Store custom tests pertaining to a test."""

    __tablename__ = 'customized_test'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey(Test.id, onupdate="CASCADE", ondelete="RESTRICT"))
    test = relationship('Test', back_populates='customized_tests')
    regression_id = Column(Integer, ForeignKey(RegressionTest.id, onupdate='CASCADE', ondelete='CASCADE'))
    regression_test = relationship('RegressionTest', uselist=False)

    def __init__(self, test_id, regression_id) -> None:
        """
        Parametrized constructor for the CustomizedTest model.

        :param test_id: The value of the 'test_id' field of
            CustomizedTest model
        :type test_id: int
        :param regression_id: The value of the 'regression_id' field of
            CustomizedTest model
        :type regression_id: int
        """
        self.test_id = test_id
        self.regression_id = regression_id

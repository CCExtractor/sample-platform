"""
Maintain all database related virtual machines and their status.

List of models corresponding to mysql tables:
[
    'Kvm' => 'kvm',
    'Maintenance mode' => 'maintenance_mode'
]
"""

import datetime
from typing import Any, Dict, Type

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Text)
from sqlalchemy.orm import relationship

import mod_test.models
from database import Base
from mod_test.models import Test, TestPlatform


class BlockedUsers(Base):
    """Model to maintain blocker users."""

    __tablename__ = 'blocked_users'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    # user_id refers to the ID from https://api.github.com/users/your_username
    user_id = Column(Integer, primary_key=True)
    comment = Column(Text())

    def __init__(self, user_id, comment) -> None:
        self.user_id = user_id
        self.comment = comment

    def __repr__(self) -> str:
        """Represent  blocked users with id and comment."""
        return f"<BlockedUsers(user_id='{self.user_id}', comment='{self.comment}')>"


class Kvm(Base):
    """Model to store KVMs."""

    __tablename__ = 'kvm'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    name = Column(String(64), primary_key=True)
    test_id = Column(Integer, ForeignKey(Test.id, onupdate="CASCADE", ondelete="RESTRICT"))
    test = relationship('Test', uselist=False)
    timestamp = Column(DateTime(), nullable=False)
    timestamp_prep_finished = Column(DateTime(), nullable=True)
    timestamp_build_finished = Column(DateTime(), nullable=True)

    def __init__(self, name, test_id, timestamp=None) -> None:
        """
        Parametrized constructor for the Kvm model.

        :param name: The value of the 'name' field of Kvm model
        :type name: str
        :param test_id: The value of the 'test_id' field of Kvm model
        :type test_id: int
        :param timestamp: The value of the 'timestamp' field of TestProgress
         model (None by default)
        :type timestamp: datetime
        """
        self.name = name
        self.test_id = test_id
        if timestamp is None:
            timestamp = datetime.datetime.now()
        self.timestamp = timestamp

    def __repr__(self) -> str:
        """
        Represent a Kvm Model by its 'test_id' Field.

        :return str(test_id): Returns the string containing
         'test_id' field of the Kvm model
        :rtype str(test_id): str
        """
        return f'<KVM test running: {self.test_id}>'


class MaintenanceMode(Base):
    """Model to maintain maintenance status of platforms."""

    __tablename__ = 'maintenance_mode'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    platform = Column(TestPlatform.db_type(), nullable=False)
    disabled = Column(Boolean, nullable=False, default=False)

    def __init__(self, platform, mode) -> None:
        """
        Parametrized constructor for the MaintenanceMode model.

        :param platform: The value of the 'platform' field of MaintenanceMode model
        :type platform: TestPlatform
        :param mode: Should the platform be in maintenance mode?
        :type mode: bool
        """
        self.platform = platform
        self.disabled = mode

    def __repr__(self) -> str:
        """
        Represent a MaintenanceMode Model by its platform and status Field.

        :return str(platform, status): Returns the string containing
         'platform' and 'status' field of the MaintenanceMode model
        :rtype str(platform, status): str
        """
        return f"<Platform {self.platform.description}, maintenance {self.disabled}>"

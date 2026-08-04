"""
Maintain all database related virtual machines and their status.

List of models corresponding to mysql tables:
[
    'Gcp Instance' => 'gcp_instance',
    'Pending Deletion' => 'pending_deletion',
    'Maintenance mode' => 'maintenance_mode'
]
"""

import datetime
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional, Type

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Text)
from sqlalchemy.orm import relationship

from database import Base
from mod_regression.models import RegressionTest
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


class GcpInstance(Base):
    """Model to store GCP Instances."""

    __tablename__ = 'gcp_instance'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    name = Column(String(64), primary_key=True)
    test_id = Column(Integer, ForeignKey(Test.id, onupdate="CASCADE", ondelete="RESTRICT"))
    test = relationship('Test', uselist=False)
    timestamp = Column(DateTime(), nullable=False)
    timestamp_prep_finished = Column(DateTime(), nullable=True)

    def __init__(self, name, test_id, timestamp=None) -> None:
        """
        Parametrized constructor for the GcpInstance model.

        :param name: The value of the 'name' field of GcpInstance model
        :type name: str
        :param test_id: The value of the 'test_id' field of GcpInstance model
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
        Represent a GcpInstance Model by its 'test_id' Field.

        :return str(test_id): Returns the string containing
         'test_id' field of the GcpInstance model
        :rtype str(test_id): str
        """
        return f'<GcpInstance test running: {self.test_id}>'


class PendingDeletion(Base):
    """Model to track pending VM deletion operations for verification."""

    __tablename__ = 'pending_deletion'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    vm_name = Column(String(64), primary_key=True)
    operation_name = Column(String(128), nullable=False)
    created_at = Column(DateTime(), nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)

    # Max retries before we give up and just try to force delete
    MAX_RETRIES: ClassVar[int] = 5

    def __init__(self, vm_name, operation_name, created_at=None) -> None:
        """
        Parametrized constructor for the PendingDeletion model.

        :param vm_name: The name of the VM being deleted
        :type vm_name: str
        :param operation_name: The GCP operation name/ID for tracking
        :type operation_name: str
        :param created_at: When the deletion was initiated (None for now)
        :type created_at: datetime
        """
        self.vm_name = vm_name
        self.operation_name = operation_name
        if created_at is None:
            created_at = datetime.datetime.now()
        self.created_at = created_at
        self.retry_count = 0

    def __repr__(self) -> str:
        """Represent a PendingDeletion by its vm_name."""
        return f'<PendingDeletion vm={self.vm_name} op={self.operation_name} retries={self.retry_count}>'


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


@dataclass
class CategoryTestInfo:
    """Contains information about the number of successful tests for a specific category during a specific test run."""

    # the test category being referred to
    category: str
    # the total number of tests in this category
    total: int
    # the number of successful tests - None if no tests were successful
    success: Optional[int]


class Status:
    """Define different states for the tests."""

    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    FAILURE = "failure"


@dataclass
class PrCommentInfo:
    """Contains info about a test run that is useful for displaying a PR comment."""

    # info about successes and failures for each category
    category_stats: List[CategoryTestInfo]
    extra_failed_tests: List[RegressionTest]
    fixed_tests: List[RegressionTest]
    common_failed_tests: List[RegressionTest]
    last_test_master: Test

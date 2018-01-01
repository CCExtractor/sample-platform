"""
mod_ci Models
===================
In this module, we are trying to maintain all database related virtual
machines and their status.
List of models corresponding to mysql tables: ['Kvm' => 'kvm',
 'Maintenance mode' => 'maintenance_mode']
"""

import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Da"""
mod_ci Models
===================
In this module, we are trying to maintain all database related virtual
machines and their status.
List of models corresponding to mysql tables: ['Kvm' => 'kvm',
 'Maintenance mode' => 'maintenance_mode']
"""

import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship

from database import Base
from mod_test.models import Test, TestPlatform


class Kvm(Base):
    __tablename__ = 'kvm'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    name = Column(String(64), primary_key=True)
    test_id = Column(Integer, ForeignKey(
        Test.id, onupdate="CASCADE", ondelete="RESTRICT"))
    test = relationship('Test', uselist=False)
    timestamp = Column(DateTime(), nullable=False)

    def __init__(self, name, test_id, timestamp=None):
        """
        Parametrized constructor for the Kvm model

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

    def __repr__(self):
        """
        Representation function
        Represent a Kvm Model by its 'test_id' Field.

        :return str(test_id): Returns the string containing
         'test_id' field of the Kvm model
        :rtype str(test_id): str
        """
        return '<KVM test running: {id}>'.format(id=self.test_id)


class MaintenanceMode(Base):
    __tablename__ = 'maintenance_mode'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    platform = Column(TestPlatform.db_type(), nullable=False)
    disabled = Column(Boolean, nullable=False, default=False)

    def __init__(self, platform, mode):
        """
        Parametrized constructor for the MaintenanceMode model

        :param platform: The value of the 'platform' field of
         MaintenanceMode model
        :type platform: TestPlatform
        :param disabled: mode
        :type disabled: bool
        """
        self.platform = platform
        self.disabled = mode

    def __repr__(self):
        """
        Representation function
        Represent a MaintenanceMode Model by its platform and status Field.

        :return str(platform, status): Returns the string containing
         'platform' and 'status' field of the MaintenanceMode model
        :rtype str(platform, status): str
        """
        return '<Platform {p}, maintenance {status}>'.format(p=self.platform.description, status=self.disabled)


class blacklisted_users(Base):
    __tablename__ = 'blacklisted_users'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    # user_id is the user's id GitHub assigns.
    user_id = Column(Integer, primary_key=True)
    # username refers to the username of the user.
    username = Column(String(41), unique=True)
    # name refers to the name property from GitHub's api.
    name = Column(String(64))

    def __repr__(self):
        return "<blacklisted_users(user_id='{id}', name='{name}', username='{username}')>".format(
            id=self.id, name=self.name, username=self.username)

teTime, Boolean
from sqlalchemy.orm import relationship

from database import Base
from mod_test.models import Test, TestPlatform


class Kvm(Base):
    __tablename__ = 'kvm'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    name = Column(String(64), primary_key=True)
    test_id = Column(Integer, ForeignKey(
        Test.id, onupdate="CASCADE", ondelete="RESTRICT"))
    test = relationship('Test', uselist=False)
    timestamp = Column(DateTime(), nullable=False)

    def __init__(self, name, test_id, timestamp=None):
        """
        Parametrized constructor for the Kvm model

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

    def __repr__(self):
        """
        Representation function
        Represent a Kvm Model by its 'test_id' Field.

        :return str(test_id): Returns the string containing
         'test_id' field of the Kvm model
        :rtype str(test_id): str
        """
        return '<KVM test running: {id}>'.format(id=self.test_id)


class MaintenanceMode(Base):
    __tablename__ = 'maintenance_mode'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    platform = Column(TestPlatform.db_type(), nullable=False)
    disabled = Column(Boolean, nullable=False, default=False)

    def __init__(self, platform, mode):
        """
        Parametrized constructor for the MaintenanceMode model

        :param platform: The value of the 'platform' field of
         MaintenanceMode model
        :type platform: TestPlatform
        :param disabled: mode
        :type disabled: bool
        """
        self.platform = platform
        self.disabled = mode

    def __repr__(self):
        """
        Representation function
        Represent a MaintenanceMode Model by its platform and status Field.

        :return str(platform, status): Returns the string containing
         'platform' and 'status' field of the MaintenanceMode model
        :rtype str(platform, status): str
        """
        return '<Platform {p}, maintenance {status}>'.format(p=self.platform.description, status=self.disabled)


class blacklisted_users(Base):
    __tablename__ = 'blacklisted_users'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    # user_id is the user's id GitHub assigns.
    user_id = Column(Integer, primary_key=True)
    # username refers to the username of the user.
    username = Column(String(41), unique=True)
    # name refers to the name property from GitHub's api.
    name = Column(String(64))

    def __repr__(self):
        return "<blacklisted_users(user_id='{id}', name='{name}', username='{username}')>".format(
            id=self.id, name=self.name, username=self.username)

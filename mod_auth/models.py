"""
mod_auth Models
===================
In this module, we are trying to maintain all database models used
for authentication.
List of models corresponding to mysql tables: ['User' => 'user']
"""

import string

from passlib.apps import custom_app_context as pwd_context
from sqlalchemy import Column, Integer, String, Text

from database import Base, DeclEnum


class Role(DeclEnum):
    admin = "admin", "Admin"
    user = "user", "User"
    contributor = "contributor", "Contributor"
    tester = "tester", "Tester"


class User(Base):
    __tablename__ = 'user'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True)
    email = Column(String(255), unique=True, nullable=True)
    github_token = Column(Text(), nullable=True)
    password = Column(String(255), unique=False, nullable=False)
    role = Column(Role.db_type())

    def __init__(self, name, role=Role.user, email=None, password=''):
        """
        Parametrized constructor for the User model

        :param name: The value of the 'name' field of User model
        :type name: str
        :param role: The value of the 'role' field of User model
        :type role: Role
        :param email: The value of the 'email' field of User model (None by
        default)
        :type email: str
        :param password: The value of the 'password' field of User model (
        empty by default)
        :type password: str
        """
        self.name = name
        self.email = email
        self.password = password
        self.role = role

    def __repr__(self):
        """
        Representation function
        Represent a User Model by its 'name' Field.

        :return str(name): Returns the string containing 'name' field
         of the User model
        :rtype str(name): str
        """
        return '<User {name}>'.format(name=self.name)

    @staticmethod
    def generate_hash(password):
        """
        Generates a Hash value for a password

        :param password: The password to be hashed
        :type password: str
        :return : The hashed password
        :rtype : str
        """
        # Go for increased strength no matter what
        return pwd_context.encrypt(password, category='admin')

    @staticmethod
    def create_random_password(length=16):
        """
        Creates a random password of default length 16

        :param length: If parameter is passed, length will be the parameter.
        16 by default
        :type length: int
        :return : Randomly generated password
        :rtype : str
        """
        chars = string.ascii_letters + string.digits + '!@#$%^&*()'
        import os
        return ''.join(chars[ord(os.urandom(1)) % len(chars)] for i in range(length))

    def is_password_valid(self, password):
        """
        Checks the validity of the password

        :param password: The password to be validated
        :type password: str
        :return : Validity of password
        :rtype : boolean
        """
        return pwd_context.verify(password, self.password)

    def update_password(self, new_password):
        """
        Updates the password to a new one

        :param new_password: The new password to be updated
        :type new_password: str
        """
        self.password = self.generate_hash(new_password)

    @property
    def is_admin(self):
        """
        Verifies if a User is the admin

        :return : Checks if User has an admin role
        :rtype: boolean
        """
        return self.role == Role.admin

    def has_role(self, name):
        """
        Checks whether the User has a particular role

        :param name: Role of the user
        :type name: str
        :return : Checks whether a User has 'name' role
        :rtype: boolean
        """
        return self.role.value == name or self.is_admin

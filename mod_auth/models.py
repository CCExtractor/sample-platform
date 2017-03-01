import string

from passlib.apps import custom_app_context as pwd_context
from sqlalchemy import Column, Integer, String, Text

from database import Base, DeclEnum


class Role(DeclEnum):
    admin = "admin", "Admin"
    user = "user", "User"
    contributor = "contributor", "Contributor"


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
	'''
	Parametrized constructor for the User model
	'''
        self.name = name
        self.email = email
        self.password = password
        self.role = role

    def __repr__(self):
	'''
	Representation function
	Represent a User Model by its 'name' Field.
	'''
        return '<User %r>' % self.name

    @staticmethod
    def generate_hash(password):
	'''
	Generates a Hash value for a password
	:param password: The password to be hashed
	:type password: str
	'''
        # Go for increased strength no matter what
        return pwd_context.encrypt(password, category='admin')

    @staticmethod
    def create_random_password(length=16):
	'''
	Creates a random password of default length 16
	:param length: If parameter is passed, length will be the parameter. 16 by default
	:type length: int
	'''
        chars = string.ascii_letters + string.digits + '!@#$%^&*()'
        import os
        return ''.join(chars[ord(os.urandom(1)) % len(chars)] for i in
                       range(length))

    def is_password_valid(self, password):
	'''
	Checks the validity of the password
	:param password: The password to be validated
	:type password: str
	'''
        return pwd_context.verify(password, self.password)

    def update_password(self, new_password):
	'''
	Updates the password to a new one
	:param new_password: The new password to be updated
	:type new_password: str
	'''
        self.password = self.generate_hash(new_password)

    @property
    def is_admin(self):
	'''
	Verifies if a User is the admin
	'''
        return self.role == Role.admin

    def has_role(self, name):
	'''
	Checks whether the User has a particular role
	:param name: Name of the user
	:type name: str
	'''
        return self.role.value == name or self.is_admin

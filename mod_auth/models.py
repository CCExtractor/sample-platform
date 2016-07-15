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
        self.name = name
        self.email = email
        self.password = password
        self.role = role

    def __repr__(self):
        return '<User %r>' % self.name

    @staticmethod
    def generate_hash(password):
        # Go for increased strength no matter what
        return pwd_context.encrypt(password, category='admin')

    @staticmethod
    def create_random_password(length=16):
        chars = string.ascii_letters + string.digits + '!@#$%^&*()'
        import os
        return ''.join(chars[ord(os.urandom(1)) % len(chars)] for i in
                       range(length))

    def is_password_valid(self, password):
        return pwd_context.verify(password, self.password)

    def update_password(self, new_password):
        self.password = self.generate_hash(new_password)

    @property
    def is_admin(self):
        return self.role == Role.admin

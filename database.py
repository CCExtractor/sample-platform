"""handles database session and data-type across app."""

import re
from abc import ABCMeta

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.sql.sqltypes import Enum, SchemaType, TypeDecorator


class DeclarativeABCMeta(DeclarativeMeta, ABCMeta):
    """Empty class to create a mixin between DeclarativeMeta and ABCMeta."""

    pass


Base = declarative_base(metaclass=DeclarativeMeta)
Base.query = None
db_engine = None


def create_session(db_string, drop_tables=False):
    """
    Create a new DB session using the scoped_session that SQLAlchemy provides.

    :param db_string: The connection string.
    :type db_string: str
    :param drop_tables: Drop existing tables?
    :type drop_tables: bool
    :return: A SQLAlchemy session object
    :rtype: sqlalchemy.orm.scoped_session
    """
    import os
    global db_engine, Base

    # In testing, we want to maintain same memory variable
    if db_engine is None or 'TESTING' not in os.environ or os.environ['TESTING'] == 'False':
        db_engine = create_engine(db_string, convert_unicode=True)
    db_session = scoped_session(sessionmaker(bind=db_engine))
    Base.query = db_session.query_property()

    if drop_tables:
        Base.metadata.drop_all(bind=db_engine)

    Base.metadata.create_all(bind=db_engine)

    return db_session


class EnumSymbol(object):
    """Define a fixed symbol tied to a parent class."""

    def __init__(self, cls_, name, value, description):
        """Initilize EnumSymbol with class, name, value and description."""
        self.cls_ = cls_
        self.name = name
        self.value = value
        self.description = description

    def __reduce__(self):
        """
        Allow unpickling to return the symbol linked to the DeclEnum class.

        :return: method and object reference to unpickle with
        :rtype: method, (class, attribute)
        """
        return getattr, (self.cls_, self.name)

    def __iter__(self):
        """
        Provide iterator for the class.

        :return: iterator
        :rtype: iter
        """
        return iter([self.value, self.description])

    def __repr__(self):
        """
        Define object representation when used with display method such as print.

        :return: object representation
        :rtype: str
        """
        return "<{name}>".format(name=self.name)


class EnumMeta(type):
    """Generate new DeclEnum classes."""

    def __init__(self, classname, bases, dict_):
        """Initilize EnumMeta with class, name, value and description."""
        self._reg = reg = self._reg.copy()
        for k, v in dict_.items():
            if isinstance(v, tuple):
                sym = reg[v[0]] = EnumSymbol(self, k, *v)
                setattr(self, k, sym)
        return type.__init__(self, classname, bases, dict_)

    def __iter__(self):
        """
        Provide iterator for the class.

        :return: iterator
        :rtype: iter
        """
        return iter(self._reg.values())


class DeclEnum(object, metaclass=EnumMeta):
    """Declarative enumeration."""

    _reg = {}   # type: dict

    @classmethod
    def from_string(cls, value):
        """
        Get value from _reg dict of the class.

        :param value: dict key
        :type value: string
        :raises ValueError: if value is not a valid key
        :return: dict element for key value
        :rtype: dynamic
        """
        try:
            return cls._reg[value]
        except KeyError:
            raise ValueError("Invalid value for {name}: {value}".format(name=cls.__name__, value=value))

    @classmethod
    def values(cls):
        """
        Get list of keys for the _reg dict of the class.

        :return: list of dictionary keys
        :rtype: set
        """
        return cls._reg.keys()

    @classmethod
    def db_type(cls):
        """Get type of database."""
        return DeclEnumType(cls)


class DeclEnumType(SchemaType, TypeDecorator):
    """Declarative enumeration type."""

    def __init__(self, enum):
        self.enum = enum
        self.impl = Enum(
            *enum.values(),
            name="ck{0}".format(re.sub('([A-Z])', lambda m: "_" + m.group(1).lower(), enum.__name__))
        )

    def _set_table(self, table, column):
        self.impl._set_table(table, column)

    def copy(self):
        """Get enumeration type of self."""
        return DeclEnumType(self.enum)

    def process_bind_param(self, value, dialect):
        """Get process bind parameter."""
        if value is None:
            return None
        return value.value

    def process_result_value(self, value, dialect):
        """Get process result value."""
        if value is None:
            return None
        return self.enum.from_string(value.strip())

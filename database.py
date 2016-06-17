import re
from abc import ABCMeta

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.sql.sqltypes import SchemaType, Enum, TypeDecorator


class DeclarativeABCMeta(DeclarativeMeta, ABCMeta):
    """
    Empty class to create a mixin between DeclarativeMeta and ABCMeta
    """
    pass

Base = declarative_base(metaclass=DeclarativeMeta)
Base.query = None
db_engine = None


def create_session(db_string, drop_tables=False):
    """
    Creates a new DB session using the scoped_session that SQLAlchemy
    provices.

    :param db_string: The connection string.
    :type db_string: str
    :param drop_tables: Drop existing tables?
    :type drop_tables: bool
    :return: A SQLAlchemy session object
    :rtype: sqlalchemy.orm.scoped_session
    """
    global db_engine, Base

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
        self.cls_ = cls_
        self.name = name
        self.value = value
        self.description = description

    def __reduce__(self):
        """Allow unpickling to return the symbol linked to the DeclEnum
        class."""
        return getattr, (self.cls_, self.name)

    def __iter__(self):
        return iter([self.value, self.description])

    def __repr__(self):
        return "<%s>" % self.name


class EnumMeta(type):
    """Generate new DeclEnum classes."""

    def __init__(cls, classname, bases, dict_):
        cls._reg = reg = cls._reg.copy()
        for k, v in dict_.items():
            if isinstance(v, tuple):
                sym = reg[v[0]] = EnumSymbol(cls, k, *v)
                setattr(cls, k, sym)
        return type.__init__(cls, classname, bases, dict_)

    def __iter__(cls):
        return iter(cls._reg.values())


class DeclEnum(object):
    """Declarative enumeration."""

    __metaclass__ = EnumMeta

    _reg = {}

    @classmethod
    def from_string(cls, value):
        try:
            return cls._reg[value]
        except KeyError:
            raise ValueError(
                    "Invalid value for %r: %r" %
                    (cls.__name__, value)
                )

    @classmethod
    def values(cls):
        return cls._reg.keys()

    @classmethod
    def db_type(cls):
        return DeclEnumType(cls)


class DeclEnumType(SchemaType, TypeDecorator):
        def __init__(self, enum):
            self.enum = enum
            self.impl = Enum(
                *enum.values(),
                name="ck%s" % re.sub(
                    '([A-Z])',
                    lambda m: "_" + m.group(1).lower(),
                    enum.__name__)
            )

        def _set_table(self, table, column):
            self.impl._set_table(table, column)

        def copy(self):
            return DeclEnumType(self.enum)

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            return value.value

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            return self.enum.from_string(value.strip())

"""handles database session and data-type across app."""
from __future__ import annotations

import re
import traceback
from abc import ABCMeta
from typing import Any, Dict, Iterator, Tuple, Type, Union

from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.sql.schema import Column, Table
from sqlalchemy.sql.sqltypes import Enum, SchemaType, TypeDecorator

from exceptions import EnumParsingException, FailedToSpawnDBSession


class DeclarativeABCMeta(DeclarativeMeta, ABCMeta):
    """Empty class to create a mixin between DeclarativeMeta and ABCMeta."""

    pass


Base = declarative_base(metaclass=DeclarativeMeta)
Base.query = None
db_engine = None


def create_session(db_string: str, drop_tables: bool = False) -> scoped_session:
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

    try:
        # In testing, we want to maintain same memory variable
        if db_engine is None or 'TESTING' not in os.environ or os.environ['TESTING'] == 'False':
            db_engine = create_engine(db_string, convert_unicode=True)
        db_session = scoped_session(sessionmaker(bind=db_engine))
        Base.query = db_session.query_property()

        if drop_tables:
            Base.metadata.drop_all(bind=db_engine)

        Base.metadata.create_all(bind=db_engine)

        return db_session
    except SQLAlchemyError:
        traceback.print_exc()
        raise FailedToSpawnDBSession()


class EnumSymbol(object):
    """Define a fixed symbol tied to a parent class."""

    def __init__(self, cls_: Any, name: str, value: str, description: str) -> None:
        """Initialize EnumSymbol with class, name, value and description."""
        self.cls_ = cls_
        self.name = name
        self.value = value
        self.description = description

    def __reduce__(self) -> Tuple[Any, Tuple[Any, str]]:
        """
        Allow unpickling to return the symbol linked to the DeclEnum class.

        :return: method and object reference to unpickle with
        :rtype: method, (class, attribute)
        """
        return getattr, (self.cls_, self.name)

    def __iter__(self) -> Iterator:
        """
        Provide iterator for the class.

        :return: iterator
        :rtype: iter
        """
        return iter([self.value, self.description])

    def __repr__(self) -> str:
        """
        Define object representation when used with display method such as print.

        :return: object representation
        :rtype: str
        """
        return f"<{self.name}>"


class EnumMeta(type):
    """Generate new DeclEnum classes."""

    def __init__(self, classname: str, bases: Union[Tuple[Type[DeclEnum]], Tuple[Type[object]]],
                 dict_: Dict[str, Union[str, Tuple[str, str], classmethod, staticmethod]]) -> None:
        """Initialize EnumMeta with class, name, value and description."""
        self._reg: Dict
        self._reg = reg = self._reg.copy()
        for k, v in dict_.items():
            if isinstance(v, tuple):
                sym = reg[v[0]] = EnumSymbol(self, k, *v)
                setattr(self, k, sym)
        return type.__init__(self, classname, bases, dict_)

    def __iter__(self) -> Iterator:
        """
        Provide iterator for the class.

        :return: iterator
        :rtype: iter
        """
        return iter(self._reg.values())


class DeclEnum(object, metaclass=EnumMeta):
    """Declarative enumeration."""

    _reg: Dict = {}

    @classmethod
    def from_string(cls, value: str) -> EnumSymbol:
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
            print(f"Invalid value for {cls.__name__}: {value}")
            raise EnumParsingException

    @classmethod
    def values(cls):
        """
        Get list of keys for the _reg dict of the class.

        :return: list of dictionary keys
        :rtype: set
        """
        return cls._reg.keys()

    @classmethod
    def db_type(cls) -> DeclEnumType:
        """Get type of database."""
        return DeclEnumType(cls)


class DeclEnumType(SchemaType, TypeDecorator):
    """Declarative enumeration type."""

    cache_ok = True

    def __init__(self, enum: Any) -> None:
        self.enum = enum
        self.impl = Enum(
            *enum.values(),
            name="ck{0}".format(re.sub('([A-Z])', lambda m: "_" + m.group(1).lower(), enum.__name__))
        )

    def _set_table(self, table: Column, column: Table) -> None:
        self.impl._set_table(table, column)

    def copy(self) -> DeclEnumType:
        """Get enumeration type of self."""
        return DeclEnumType(self.enum)

    def process_bind_param(self, value: EnumSymbol, dialect: SQLiteDialect_pysqlite) -> str:
        """Get process bind parameter."""
        if value is None:
            return None
        return value.value

    def process_result_value(self, value: str, dialect: SQLiteDialect_pysqlite) -> EnumSymbol:
        """Get process result value."""
        if value is None:
            return None
        return self.enum.from_string(value.strip())

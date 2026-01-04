"""handles database session and data-type across app."""
from __future__ import annotations

import re
import traceback
from abc import ABCMeta
from typing import Any, Dict, Iterator, Optional, Tuple, Type, Union

from sqlalchemy import create_engine
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import (DeclarativeBase, DeclarativeMeta, scoped_session,
                            sessionmaker)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.sqltypes import String, TypeDecorator

from exceptions import EnumParsingException, FailedToSpawnDBSession


class DeclarativeABCMeta(DeclarativeMeta, ABCMeta):
    """Empty class to create a mixin between DeclarativeMeta and ABCMeta."""

    pass


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


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
        # Only create engine if it doesn't exist
        # For SQLite in-memory, we must reuse the engine to share the database
        if db_engine is None:
            # For SQLite in-memory databases, use StaticPool to share connection
            if db_string == 'sqlite:///:memory:':
                db_engine = create_engine(
                    db_string,
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool
                )
            else:
                db_engine = create_engine(db_string)
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
            # Skip dunder attributes (Python 3.13+ adds __static_attributes__ tuple)
            # and validate tuple has exactly 2 elements (value, description)
            if isinstance(v, tuple) and not k.startswith('_') and len(v) == 2:
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


class DeclEnumType(TypeDecorator):
    """Declarative enumeration type."""

    cache_ok = True
    impl = String(50)

    def __init__(self, enum: Any) -> None:
        self.enum = enum
        super().__init__()

    def copy(self, **kwargs: Any) -> DeclEnumType:
        """Get enumeration type of self."""
        return DeclEnumType(self.enum)

    def process_bind_param(self, value: Optional[EnumSymbol], dialect: Dialect) -> Optional[str]:
        """Get process bind parameter."""
        if value is None:
            return None
        return value.value

    def process_result_value(self, value: Optional[str], dialect: Dialect) -> Optional[EnumSymbol]:
        """Get process result value."""
        if value is None:
            return None
        return self.enum.from_string(value.strip())

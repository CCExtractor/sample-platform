"""
Maintains database models regarding general information.

Includes version, released date, commit about main repository (CCExtractor).

List of models corresponding to mysql tables:
    [
        'CCExtractorVersion' => 'ccextractor_version',
        'GeneralData' => 'general_data'
    ]
"""
from datetime import datetime
from typing import Any, Dict, Type

from sqlalchemy import Column, Date, Integer, String, Text

import database
from database import Base, DeclEnum


class CCExtractorVersion(Base):
    """Model to manage CCExtractor version and release data."""

    __tablename__ = 'ccextractor_version'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    version = Column(String(10), unique=True)
    released = Column(Date(), unique=True)
    commit = Column(String(64), unique=True)

    def __init__(self, version, released, commit) -> None:
        """
        Parametrized constructor for the CCExtractorVersion model.

        :param version: The value of the 'version' field of
         CCExtractorVersion model
        :type version: str
        :param released: The value of the 'released' field of
         CCExtractorVersion model
        :type released: datetime
        :param commit: The value of the 'timestamp' field of
         CCExtractorVersion model
        :type commit: str
        """
        self.version = version
        self.released = datetime.strptime(released, '%Y-%m-%dT%H:%M:%SZ').date()
        self.commit = commit

    def __repr__(self) -> str:
        """
        Represent a CCExtractorVersion Model by its 'version' Field.

        :return str(version): Returns the string containing
         'version' field of the CCExtractorVersion model
        :rtype str(version): str
        """
        return f"<Version {self.version}>"


class GeneralData(Base):
    """Model to manage general data."""

    __tablename__ = 'general_data'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True)
    value = Column(Text(), nullable=False)

    def __init__(self, key, value) -> None:
        """
        Parametrized constructor for the GeneralData model.

        :param key: The value of the 'key' field of
         GeneralData model
        :type key: str
        :param value: The value of the 'value' field of
         GeneralData model
        :type value: str
        """
        self.key = key
        self.value = value

    def __repr__(self) -> str:
        """
        Represent a GeneralData Model by its 'key' and 'value' Field.

        :return str(key,version): Returns the string containing
         'key' and 'version' field of the GeneralData model
        :rtype str(key,version): str
        """
        return f"<GeneralData {self.key}: {self.value}>"

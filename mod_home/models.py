"""
mod_home Models
===================
In this module, we are trying to maintain database regarding general
information such as version, released date, commit about main
repository(CCextractor) and other general data.
List of models corresponding to mysql tables: ['CCExtractorVersion' =>
 'ccextractor_version','GeneralData' => 'general_data']
"""
from sqlalchemy import Column, Integer, String, Text, Date

from database import Base, DeclEnum


class CCExtractorVersion(Base):
    __tablename__ = 'ccextractor_version'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    version = Column(String(10), unique=True)
    released = Column(Date(), unique=True)
    commit = Column(String(64), unique=True)

    def __init__(self, version, released, commit):
        """
        Parametrized constructor for the CCExtractorVersion model

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
        self.released = released
        self.commit = commit

    def __repr__(self):
        """
        Representation function
        Represent a CCExtractorVersion Model by its 'version' Field.

        :return str(version): Returns the string containing
         'version' field of the CCExtractorVersion model
        :rtype str(version): str
        """
        return '<Version {v}>'.format(v=self.version)


class GeneralData(Base):
    __tablename__ = 'general_data'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True)
    value = Column(Text(), nullable=False)

    def __init__(self, key, value):
        """
        Parametrized constructor for the GeneralData model

        :param key: The value of the 'key' field of
         GeneralData model
        :type key: str
        :param value: The value of the 'value' field of
         GeneralData model
        :type value: str
        """
        self.key = key
        self.value = value

    def __repr__(self):
        """
        Representation function
        Represent a GeneralData Model by its 'key' and 'value' Field.

        :return str(key,version): Returns the string containing
         'key' and 'version' field of the GeneralData model
        :rtype str(key,version): str
        """
        return '<GeneralData {key}: {value}>'.format(key=self.key, value=self.value)

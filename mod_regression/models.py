"""
Maintain database models regarding various regression tests, categories, storing output of tests.

List of models corresponding to mysql tables:
    [
        'Category' => 'category',
        'RegressionTest' => 'regression_test',
        'RegressionTestOutput' => 'regression_test_output'
        'RegressionTestOutputFiles' => 'regression_test_output_files'
    ]
"""

from typing import Any, Dict, Tuple, Type

from sqlalchemy import (Boolean, Column, ForeignKey, Integer, String, Table,
                        Text)
from sqlalchemy.orm import relationship

import database
from database import Base, DeclEnum

regressionTestLinkTable = Table(
    'regression_test_category',
    Base.metadata,
    Column('regression_id', Integer, ForeignKey('regression_test.id', onupdate='CASCADE', ondelete='RESTRICT')),
    Column('category_id', Integer, ForeignKey('category.id', onupdate='CASCADE', ondelete='RESTRICT'))
)


class Category(Base):
    """Model to store categories of regression tests."""

    __tablename__ = 'category'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    description = Column(Text(), nullable=False)
    regression_tests = relationship('RegressionTest', secondary=regressionTestLinkTable, back_populates='categories')

    def __init__(self, name, description) -> None:
        """
        Parametrized constructor for the Category model.

        :param name: The value of the 'name' field of Category model
        :type name: str
        :param description: The value of the 'description' field of Category model
        :type description: str
        """
        self.name = name
        self.description = description

    def __repr__(self) -> str:
        """
        Represent a Category Model by its 'name' Field.

        :return: Returns the string containing 'name' field of the Category model
        :rtype: str
        """
        return f"<Category {self.name}>"


class InputType(DeclEnum):
    """Enumerator types for input."""

    file = "file", "File"
    stdin = "stdin", "Stdin"
    udp = "udp", "UDP"


class OutputType(DeclEnum):
    """Enumerator types for input."""

    file = "file", "File"
    null = "null", "Null"
    tcp = "tcp", "TCP"
    cea708 = "cea708", "CEA-708"
    multi_program = "multiprogram", "Multi-program"
    stdout = "stdout", "Stdout"
    report = "report", "Report"


class RegressionTest(Base):
    """Model to store regression tests."""

    __tablename__ = 'regression_test'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey('sample.id', onupdate='CASCADE', ondelete='CASCADE'))
    sample = relationship('Sample', uselist=False, back_populates='tests')
    command = Column(Text(), nullable=False)
    input_type = Column(InputType.db_type())
    output_type = Column(OutputType.db_type())
    categories = relationship('Category', secondary=regressionTestLinkTable, back_populates='regression_tests')
    output_files = relationship('RegressionTestOutput', back_populates='regression_test')
    expected_rc = Column(Integer)
    active = Column(Boolean(), default=True)
    last_passed_on_windows = Column(Integer, ForeignKey('test.id', onupdate="CASCADE", ondelete="SET NULL"))
    last_passed_on_linux = Column(Integer, ForeignKey('test.id', onupdate="CASCADE", ondelete="SET NULL"))
    description = Column(String(length=1024))

    def __init__(self, sample_id, command, input_type, output_type, category_id, expected_rc,
                 active=True, description="") -> None:
        """
        Parametrized constructor for the RegressionTest model.

        :param sample_id: The value of the 'name' field of RegressionTest model
        :type sample_id: int
        :param command: The value of the 'command' field of RegressionTest model
        :type command: str
        :param input_type: The value of the 'input_type' field of RegressionTest model
        :type input_type: InputType
        :param output_type: The value of the 'output_type' field of RegressionTest model
        :type output_type: OutputType
        :param category_id: The value of the 'category_id' field of RegressionTest model
        :type category_id: int
        :param expected_rc: The value of the 'expected_rc' field of RegressionTest model
        :type expected_rc: int
        :param active: The value of the 'active' field of RegressionTest model
        :type active: bool

        """
        self.sample_id = sample_id
        self.command = command
        self.input_type = input_type
        self.output_type = output_type
        self.category_id = category_id
        self.expected_rc = expected_rc
        self.active = active
        self.description = description

    def __repr__(self) -> str:
        """
        Represent a RegressionTest Model by its 'id' Field.

        :return: Returns the string containing 'id' field of the RegressionTest model
        :rtype: str
        """
        return f"<RegressionTest {self.id}>"


class RegressionTestOutput(Base):
    """Model to store output of regression test."""

    __tablename__ = 'regression_test_output'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    regression_id = Column(Integer, ForeignKey('regression_test.id', onupdate='CASCADE', ondelete='RESTRICT'))
    regression_test = relationship('RegressionTest', back_populates='output_files')
    correct = Column(Text())
    correct_extension = Column(String(64), nullable=False)  # contains the .
    expected_filename = Column(Text())
    ignore = Column(Boolean(), default=False)
    multiple_files = relationship('RegressionTestOutputFiles', back_populates='output')

    def __init__(self, regression_id, correct, correct_extension, expected_filename, ignore=False) -> None:
        """
        Parametrized constructor for the RegressionTestOutput model.

        :param regression_id: The value of the 'regression_id' field of RegressionTestOutput model
        :type regression_id: int
        :param correct: The value of the 'correct' field of RegressionTestOutput model
        :type correct: str
        :param correct_extension: The value of the 'correct_extension' field of RegressionTestOutput model
        :type correct_extension: str
        :param expected_filename: The value of the 'expected_filename' field of RegressionTestOutput model
        :type expected_filename: str
        :param ignore: The value of the 'ignore' field of RegressionTestOutput model (False by default)
        :type ignore: bool
        """
        self.regression_id = regression_id
        self.correct = correct
        self.correct_extension = correct_extension
        self.expected_filename = expected_filename
        self.ignore = ignore

    def __repr__(self) -> str:
        """
        Represent a RegressionTestOutput Model by its 'id' Field.

        :return: Returns the string containing 'id' field of the RegressionTestOutput model.
        :rtype: str
        """
        return f"<RegressionTestOutput {self.id}>"

    @property
    def filename_correct(self):
        """
        Return the filename of a particular regression output.

        :return: String containing name and particular extension
        :rtype: str
        """
        return self.create_correct_filename(self.correct)

    def filename_expected(self, sample_hash) -> str:
        """
        Return expected filename.

        :param sample_hash: sample_hash of RegressionTestOutput
        :type name: str
        :return: String containing name, expected filename, particular extension
        :rtype: str
        """
        return f"{sample_hash}{self.expected_filename}{self.correct_extension}"

    def create_correct_filename(self, name) -> str:
        """
        Create correct filename.

        :param name: name of the file
        :type name: str
        :return: correct file name with extension
        :rtype: str
        """
        return f"{name}{self.correct_extension}"


class RegressionTestOutputFiles(Base):
    """Model to store multiple correct output files for a regression_test."""

    __tablename__ = 'regression_test_output_files'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    file_hashes = Column(Text())
    regression_test_output_id = Column(
        Integer,
        ForeignKey('regression_test_output.id', onupdate='CASCADE', ondelete='RESTRICT')
    )
    output = relationship('RegressionTestOutput', back_populates='multiple_files')

    def __init__(self, file_hashes, regression_test_output_id) -> None:
        """
        Parametrized constructor for the RegressionTestOutput model.

        :param regression_test_output_id: ForeignKey refering to id of RegressionTestOutput model
        :type regression_id: int
        :param file_hashes: The value of the 'file_hashes' field of RegressionTestOutputFiles model
        :type correct: str
        """
        self.file_hashes = file_hashes
        self.regression_test_output_id = regression_test_output_id

    def __repr__(self) -> str:
        """
        Represent a RegressionTestOutputFile Model by its 'id' Field.

        :return: Returns the string containing 'id' field of the RegressionTestOutputFile model.
        :rtype: str
        """
        return f"{self.id}"

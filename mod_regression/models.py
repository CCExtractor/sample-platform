from sqlalchemy import Boolean
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy import Table
from sqlalchemy.orm import relationship

from database import Base, DeclEnum

regressionTestCategoryLinkTable = Table(
    'regression_test_category', Base.metadata,
    Column('regression_id', Integer, ForeignKey(
        'regression_test.id', onupdate='CASCADE', ondelete='RESTRICT')),
    Column('category_id', Integer, ForeignKey(
        'category.id', onupdate='CASCADE', ondelete='RESTRICT'))
)


class Category(Base):
    __tablename__ = 'category'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    description = Column(Text(), nullable=False)
    regression_tests = relationship(
        'RegressionTest', secondary=regressionTestCategoryLinkTable,
        back_populates='categories')

    def __init__(self, name, description):
        self.name = name
        self.description = description

    def __repr__(self):
        return '<Category %r>' % self.name


class InputType(DeclEnum):
    file = "file", "File"
    stdin = "stdin", "Stdin"
    udp = "udp", "UDP"


class OutputType(DeclEnum):
    file = "file", "File"
    null = "null", "Null"
    tcp = "tcp", "TCP"
    cea708 = "cea708", "CEA-708"
    multi_program = "multiprogram", "Multi-program"
    stdout = "stdout", "Stdout"
    report = "report", "Report"


class RegressionTest(Base):
    __tablename__ = 'regression_test'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey('sample.id', onupdate='CASCADE',
                                           ondelete='CASCADE'))
    sample = relationship('Sample', uselist=False, back_populates='tests')
    command = Column(Text(), nullable=False)
    input_type = Column(InputType.db_type())
    output_type = Column(OutputType.db_type())
    categories = relationship(
        'Category', secondary=regressionTestCategoryLinkTable,
        back_populates='regression_tests')
    output_files = relationship('RegressionTestOutput',
                                back_populates='regression_test')

    def __init__(self, sample_id, command, input_type, output_type,
                 category_id):
        self.sample_id = sample_id
        self.command = command
        self.input_type = input_type
        self.output_type = output_type
        self.category_id = category_id

    def __repr__(self):
        return '<RegressionTest %r>' % self.id


class RegressionTestOutput(Base):
    __tablename__ = 'regression_test_output'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    regression_id = Column(Integer, ForeignKey(
        'regression_test.id', onupdate='CASCADE', ondelete='RESTRICT'))
    regression_test = relationship('RegressionTest',
                                   back_populates='output_files')
    correct = Column(Text())
    correct_extension = Column(String(64), nullable=False)  # contains the .
    expected_filename = Column(Text())
    ignore = Column(Boolean())

    def __init__(self, regression_id, correct, correct_extension,
                 expected_filename, ignore=False):
        self.sample_id = regression_id
        self.correct = correct
        self.correct_extension = correct_extension
        self.expected_filename = expected_filename
        self.ignore = ignore

    def __repr__(self):
        return '<RegressionTestOutput %r>' % self.id

    @property
    def filename_correct(self):
        return "{name}{extension}".format(
            name=self.correct, extension=self.correct_extension)

    def filename_expected(self, sample_hash):
        return "{sha}{extra}{extension}".format(
            sha=sample_hash, extra=self.expected_filename,
            extension=self.correct_extension)

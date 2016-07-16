from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from database import Base, DeclEnum
from mod_sample.models import Sample


class Category(Base):
    __tablename__ = 'category'
    __table_args__ = {'mysql_engine': 'InnoDB'}
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    description = Column(Text(), nullable=False)
    regression_tests = relationship(
        'RegressionTest', back_populates='categories')

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
                                           ondelete='RESTRICT'))
    sample = relationship('Sample', uselist=False, back_populates='tests')
    command = Column(Text(), nullable=False)
    input_type = Column(InputType.db_type())
    output_type = Column(OutputType.db_type())
    category_id = Column(
        Integer,
        ForeignKey('category.id', onupdate='CASCADE', ondelete='RESTRICT')
    )
    categories = relationship('Category', back_populates='regression_tests')

    def __init__(self):
        # TODO: finish
        pass

    def __repr__(self):
        return '<RegressionTest %r>' % self.id

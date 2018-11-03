from flask_wtf import FlaskForm
from wtforms import Form, StringField, SubmitField, SelectField, validators,IntegerField
from wtforms.validators import DataRequired, Email, ValidationError, NumberRange
from mod_sample.models import Sample
from mod_regression.models import InputType, OutputType, Category

class AddCategoryForm(FlaskForm):
    """
    Flask form to Add Category
    """
    category_name = StringField('Category Name', [DataRequired(message="Category name can't be empty")])
    category_description = StringField('Description')
    submit = SubmitField("Add Category")

class AddTestForm(FlaskForm):
    """
    Flask form to Add Regression Test
    """
    sample_id = SelectField(u'Sample', choices=[(' ',' ')], default=' ')
    command = StringField('Command')
    input_type = SelectField(u'Input Type', choices = [(InputType.file,"File"),(InputType.stdin,"Stdin"),(InputType.udp,"UDP")])
    output_type = SelectField(u'Output Type', choices = [(OutputType.file,"File"),(OutputType.null,"Null"),(OutputType.tcp,"TCP"),
        (OutputType.cea708,"CEA-708"),(OutputType.multi_program,"Multi-Program"),(OutputType.stdout,"Stdout"),(OutputType.report,"Report")])
    category_id = SelectField(u'Category', choices=[(' ',' ')], default=' ')
    expected_rc = IntegerField('Expected Runtime Code', [NumberRange(min=0,message="Expected Runtime Code must be greater than 0")])
    submit = SubmitField("Add Regression Test")

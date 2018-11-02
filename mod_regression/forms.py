from flask_wtf import FlaskForm
from wtforms import Form, StringField, SubmitField, SelectField, validators,IntegerField
from wtforms.validators import DataRequired, Email, ValidationError, NumberRange

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
    sample_id = IntegerField('Sample Id', [DataRequired(message="Sample Id can't be empty")])
    command = StringField('Command')
    category_id = IntegerField('Category Id', [DataRequired(message="Category Id can't be empty")])
    expected_rc = IntegerField('Expected Runtime Code', [NumberRange(min=0,message="Expected Runtime Code must be greater than 0")])
    submit = SubmitField("Add Regression Test")

from flask_wtf import FlaskForm
from wtforms import Form, StringField, SubmitField, SelectField, validators, IntegerField, HiddenField
from wtforms.validators import DataRequired, Email, ValidationError, NumberRange
from mod_sample.models import Sample
from mod_regression.models import InputType, OutputType, Category

class AddCategoryForm(FlaskForm):
    """
    Flask form to Add Category
    """
    category_name = StringField("Category Name", [DataRequired(message="Category name can't be empty")])
    category_description = StringField("Description")
    submit = SubmitField("Add Category")

class AddTestForm(FlaskForm):
    """
    Flask form to Add Regression Test
    """
    sample_id = SelectField("Sample", coerce=int)
    command = StringField("Command")
    input_type = SelectField(
        "Input Type",
        [DataRequired(message="Input Type is not selected")],
        coerce=str,
        choices=[(i.value, i.description) for i in InputType]
    )
    output_type = SelectField(
        "Output Type",
        [DataRequired(message="Output Type is not selected")],
        coerce=str,
        choices=[(o.value, o.description) for o in OutputType]
    )
    category_id = SelectField("Category", coerce=int)
    expected_rc = IntegerField("Expected Runtime Code",
        [DataRequired(message="Expected Runtime Code can't be empty")])
    submit = SubmitField("Add Regression Test")

class ConfirmationForm(FlaskForm):
    """
    Flask Form Used for Asking Confirmations
    """
    confirm = HiddenField('nesho', default='yes') # nesho = something
    submit = SubmitField('Confirm')

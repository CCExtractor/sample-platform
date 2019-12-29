"""Maintain forms related to CRUD operations on regression tests."""

from flask_wtf import FlaskForm
from wtforms import (Form, HiddenField, IntegerField, SelectField, StringField,
                     SubmitField, validators)
from wtforms.validators import (DataRequired, Email, NumberRange,
                                ValidationError)

from mod_regression.models import Category, InputType, OutputType
from mod_sample.models import Sample


class AddCategoryForm(FlaskForm):
    """Flask form to Add Category."""

    category_name = StringField("Category Name", [DataRequired(message="Category name can't be empty")])
    category_description = StringField("Description")
    submit = SubmitField("Add Category")


class CommonTestForm(FlaskForm):
    """Flask form to Add Regression Test."""

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
    expected_rc = IntegerField("Expected Runtime Code", [DataRequired(message="Expected Runtime Code can't be empty")])


class AddTestForm(CommonTestForm):
    submit = SubmitField("Add Regression Test")


class EditTestForm(CommonTestForm):
    submit = SubmitField("Edit Regression Test")


class ConfirmationForm(FlaskForm):
    """Flask Form Used for Asking Confirmations."""

    confirm = HiddenField('confirm', default='yes')
    submit = SubmitField('Confirm')

"""Maintain forms related to CRUD operations on regression tests."""

from flask_wtf import FlaskForm
from wtforms import (HiddenField, IntegerField, SelectField, StringField,
                     SubmitField)
from wtforms.validators import DataRequired, InputRequired

from mod_regression.models import InputType, OutputType


class AddCategoryForm(FlaskForm):
    """Flask form to Add Category."""

    category_name = StringField("Category Name", [DataRequired(message="Category name can't be empty")])
    category_description = StringField("Description")
    submit = SubmitField("Add Category")


class CommonTestForm(FlaskForm):
    """Common Flask form to manage a Regression Test."""

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
    expected_rc = IntegerField("Expected Runtime Code", [InputRequired(message="Expected Runtime Code can't be empty")])


class AddTestForm(CommonTestForm):
    """Flask form to add a Regression Test."""

    submit = SubmitField("Add Regression Test")


class EditTestForm(CommonTestForm):
    """Flask form to edit a Regression Test."""

    submit = SubmitField("Edit Regression Test")


class ConfirmationForm(FlaskForm):
    """Flask Form Used for Asking Confirmations."""

    confirm = HiddenField('confirm', default='yes')
    submit = SubmitField('Confirm')


class AddCorrectOutputForm(FlaskForm):
    """Flask form to Add correct output."""
    output_file = SelectField(
        "Choose an original file to which the variant file should be attached to",
        [DataRequired(message="Output cannot be empty")],
        coerce=int
        )
    test_id = SelectField(
        "Choose a Result file from previous Test runs",
        [DataRequired(message="Output cannot be empty")]
        )
    submit = SubmitField("Add Output")


class RemoveCorrectOutputForm(FlaskForm):
    """Flask form to Remove correct output."""
    output_file = SelectField(
        "Choose an output file (variant)",
        [DataRequired(message="Output cannot be empty")],
        coerce=int
        )
    submit = SubmitField("Remove Output")

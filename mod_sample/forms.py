"""Maintains forms related to sample CRUD operations."""

from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, ValidationError

from mod_upload.models import Platform


class EditSampleForm(FlaskForm):
    """Form to edit sample."""

    notes = TextAreaField('Notes', [DataRequired(message='Notes are not filled in')])
    parameters = TextAreaField('Parameters', [DataRequired(message='Parameters are not filled in')])
    platform = SelectField(
        'Platform',
        [DataRequired(message='Platform is not selected')],
        coerce=str,
        choices=[(p.value, p.description) for p in Platform]
    )
    version = SelectField('Version', [DataRequired(message='Version is not selected')], coerce=int)
    submit = SubmitField('Update sample')


class DeleteSampleForm(FlaskForm):
    """Form to delete sample."""

    submit = SubmitField('Delete sample')


class DeleteAdditionalSampleForm(FlaskForm):
    """Form to delete sample's additional file."""

    submit = SubmitField('Delete extra file')

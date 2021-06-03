"""Maintains forms related to sample CRUD operations."""

from flask_wtf import FlaskForm
from wtforms import SubmitField

from mod_upload.forms import CommonSampleForm


class EditSampleForm(CommonSampleForm):
    """Form to edit sample."""

    submit = SubmitField('Update sample')


class DeleteSampleForm(FlaskForm):
    """Form to delete sample."""

    submit = SubmitField('Delete sample')


class DeleteAdditionalSampleForm(FlaskForm):
    """Form to delete sample's additional file."""

    submit = SubmitField('Delete extra file')

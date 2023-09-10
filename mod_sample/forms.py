"""Maintains forms related to sample CRUD operations."""

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, ValidationError

from mod_upload.forms import CommonSampleForm

from .models import Tag


class EditSampleForm(CommonSampleForm):
    """Form to edit sample."""

    submit = SubmitField('Update sample')


class AddTagForm(FlaskForm):
    """Form to add tags."""

    name = StringField('Name', validators=[DataRequired(message="Tag name is required.")])
    description = TextAreaField('Description')
    submit = SubmitField('Add Tag')

    @staticmethod
    def validate_name(form, field) -> None:
        """
        Validate tag name (case-insensitive).

        :param form: form data
        :type form: AddTagForm
        :param field: field to validate
        :type field: form field
        :raises ValidationError: when the same tag already exists
        """
        existing_tag = Tag.query.filter(Tag.name.ilike(field.data)).first()
        if existing_tag:
            raise ValidationError("Tag with the same name already exists.")


class DeleteSampleForm(FlaskForm):
    """Form to delete sample."""

    submit = SubmitField('Delete sample')


class DeleteAdditionalSampleForm(FlaskForm):
    """Form to delete sample's additional file."""

    submit = SubmitField('Delete extra file')

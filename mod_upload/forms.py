"""Maintain forms to perform CRUD operations on uploads and related database."""

import mimetypes
import os
from typing import Any, Type

import magic
from flask_wtf import FlaskForm
from wtforms import FileField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, ValidationError

import mod_home.models
import mod_sample.models
import mod_upload.models
from mod_home.models import CCExtractorVersion
from mod_sample.models import ForbiddenExtension, ForbiddenMimeType
from mod_upload.models import Platform


class UploadForm(FlaskForm):
    """Form to make a new sample upload."""

    accept = '.ts, .txt, .srt, .png, video/*'

    file = FileField('File to upload', [DataRequired(message='No file was provided.')], render_kw={'accept': accept})
    submit = SubmitField('Upload file')

    @staticmethod
    def validate_file(form, field) -> None:
        """
        Validate sample being uploaded.

        :param form: form data
        :type form: UploadForm
        :param field: field to validate
        :type field: form field
        :raises ValidationError: when extension is not allowed
        :raises ValidationError: when mimetype is not allowed
        :raises ValidationError: when extension not provided and not supported
        """
        # File cannot end with a forbidden extension
        filename, file_extension = os.path.splitext(field.data.filename)
        if len(file_extension) > 0:
            forbidden_ext = ForbiddenExtension.query.filter(ForbiddenExtension.extension == file_extension[1:]).first()
            if forbidden_ext is not None:
                raise ValidationError('Extension not allowed')
        mimetype = magic.from_buffer(field.data.read(1024), mime=True)
        # File Pointer returns to beginning
        field.data.seek(0, 0)
        # Check for permitted mimetype
        forbidden_mime = ForbiddenMimeType.query.filter(ForbiddenMimeType.mimetype == mimetype).first()
        if forbidden_mime is not None:
            raise ValidationError('File MimeType not allowed')
        extension = mimetypes.guess_extension(mimetype)
        if extension is not None:
            forbidden_real = ForbiddenExtension.query.filter(ForbiddenExtension.extension == extension[1:]).first()
            if forbidden_real is not None:
                raise ValidationError('Extension not allowed')


class DeleteQueuedSampleForm(FlaskForm):
    """Form to delete a queued sample."""

    submit = SubmitField('Delete queued file')


class CommonSampleForm(FlaskForm):
    """Form to submit common sample data."""

    notes = TextAreaField('Notes', [DataRequired(message='Notes are not filled in')])
    parameters = TextAreaField('Parameters', [DataRequired(message='Parameters are not filled in')])
    platform = SelectField(
        'Platform',
        [DataRequired(message='Platform is not selected')],
        coerce=str,
        choices=[(p.value, p.description) for p in Platform]
    )
    version = SelectField('Version', [DataRequired(message='Version is not selected')], coerce=int)

    @staticmethod
    def validate_version(form, field) -> None:
        """
        Validate CCExtractor version.

        :param form: form data
        :type form: CommonSampleForms
        :param field: field to validate
        :type field: form field
        :raises ValidationError: when invalid version selected
        """
        version = CCExtractorVersion.query.filter(CCExtractorVersion.id == field.data).first()
        if version is None:
            raise ValidationError('Invalid version selected')


class FinishQueuedSampleForm(CommonSampleForm):
    """Form to finalize sample queue."""

    report = SelectField('Do you want to report an issue on GitHub?', choices=[('n', 'No'), ('y', 'Yes')])
    IssueTitle = TextAreaField('Issue Title', [DataRequired(message='Title is not filled in')])
    IssueBody = TextAreaField('Issue Content', [DataRequired(message='Content is not filled in')])
    submit = SubmitField('Finalize sample')

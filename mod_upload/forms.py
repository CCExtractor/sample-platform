import os
import magic
import mimetypes

from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField, TextAreaField, SelectField
from wtforms.validators import DataRequired, ValidationError

from mod_home.models import CCExtractorVersion
from mod_sample.models import ForbiddenExtension, ForbiddenMimeType
from mod_upload.models import Platform


class UploadForm(FlaskForm):
    accept = '.ts, .txt, .srt, .png, video/*'

    file = FileField('File to upload', [DataRequired(message='No file was provided.')], render_kw={'accept': accept})
    submit = SubmitField('Upload file')

    @staticmethod
    def validate_file(form, field):
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
    submit = SubmitField('Delete queued file')


class CommonSampleForm(FlaskForm):
    notes = TextAreaField('Notes', [DataRequired(message='Notes are not filled in')])
    parameters = TextAreaField('Parameters', [DataRequired(message='Parameters are not filled in')])
    platform = SelectField(
        'Platform',
        [DataRequired(message='Platform is not selected')],
        coerce=str,
        choices=[(p.value, p.description) for p in Platform]
    )
    version = SelectField('Version', [DataRequired(message='Version is not selected')], coerce=int)
    report = SelectField('Do you want to report Issue on GitHub?', choices=[('n', 'No'), ('y', 'Yes')])
    IssueTitle = TextAreaField('Issue Title', [DataRequired(message='Title is not filled in')])
    IssueBody = TextAreaField('Issue Content', [DataRequired(message='Content is not filled in')])

    @staticmethod
    def validate_version(form, field):
        version = CCExtractorVersion.query.filter(CCExtractorVersion.id == field.data).first()
        if version is None:
            raise ValidationError('Invalid version selected')


class FinishQueuedSampleForm(CommonSampleForm):
    submit = SubmitField('Finalize sample')

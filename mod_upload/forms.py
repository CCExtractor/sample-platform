import os

from flask_wtf import Form
from wtforms import FileField, SubmitField
from wtforms.validators import DataRequired, ValidationError

from mod_sample.models import ForbiddenExtension


class UploadForm(Form):
    accept = '.ts, .txt, .srt, .png, video/*'

    file = FileField('File to upload', [
        DataRequired(message='No file was provided.')
    ], render_kw={'accept': accept})
    submit = SubmitField('Upload file')

    @staticmethod
    def validate_file(form, field):
        # File cannot end with a forbidden extension
        filename, file_extension = os.path.splitext(field.data.filename)
        if len(file_extension) > 0:
            forbidden = ForbiddenExtension.query.filter(
                ForbiddenExtension.extension == file_extension[1:]).first()
            if forbidden is not None:
                raise ValidationError('Extension not allowed')


class DeleteQueuedSampleForm(Form):
    submit = SubmitField('Delete queued file')


class FinishQueuedSampleForm(Form):
    # TODO: finish
    submit = SubmitField('Create sample')

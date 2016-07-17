from flask_wtf import Form
from wtforms import StringField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, ValidationError

from mod_home.models import CCExtractorVersion
from mod_upload.models import Platform


class EditSampleForm(Form):
    notes = TextAreaField(
        'Notes', [DataRequired(message='Notes are not filled in')])
    parameters = TextAreaField(
        'Parameters', [DataRequired(message='Parameters are not filled in')])
    platform = SelectField(
        'Platform', [DataRequired(message='Platform is not selected')],
        coerce=str, choices=[(p.value, p.description) for p in Platform])
    version = SelectField(
        'Version', [DataRequired(message='Version is not selected')],
        coerce=int)
    submit = SubmitField('Update sample')

    @staticmethod
    def validate_version(form, field):
        v = CCExtractorVersion.query.filter(
            CCExtractorVersion.id == field.data).first()
        if v is None:
            raise ValidationError('Invalid version selected')

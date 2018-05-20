from flask_wtf import FlaskForm
from wtforms import SubmitField

from mod_upload.forms import CommonSampleForm


class EditSampleForm(CommonSampleForm):
    submit = SubmitField('Update sample')


class DeleteSampleForm(FlaskForm):
    submit = SubmitField('Delete sample')


class DeleteAdditionalSampleForm(FlaskForm):
    submit = SubmitField('Delete extra file')

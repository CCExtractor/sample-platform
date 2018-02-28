from flask_wtf import Form
from wtforms import SubmitField
from mod_upload.forms import CommonSampleForm


class EditSampleForm(CommonSampleForm):
    submit = SubmitField('Update sample')


class DeleteSampleForm(Form):
    submit = SubmitField('Delete sample')


class DeleteAdditionalSampleForm(Form):
    submit = SubmitField('Delete extra file')

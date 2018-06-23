from flask_wtf import FlaskForm
from wtforms import widgets, StringField, SubmitField, SelectMultipleField, RadioField
from wtforms.validators import DataRequired, url
from mod_test.models import TestPlatform


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class TestForkForm(FlaskForm):
    commit_hash = StringField('Commit Hash', [DataRequired(message='Commit hash is not filled in')])
    commit_select = RadioField('Choose Commit', choices=[('', '')], default='')
    platform = MultiCheckboxField('Platform', validators=[DataRequired()], choices=[(
        platform, platform) for platform in TestPlatform.values()])
    add = SubmitField('Run Test')

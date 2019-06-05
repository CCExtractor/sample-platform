"""contains forms related to creating customized tests."""

from flask_wtf import FlaskForm
from wtforms import (RadioField, SelectMultipleField, StringField, SubmitField,
                     widgets)
from wtforms.validators import DataRequired, url

from mod_regression.models import RegressionTest
from mod_test.models import TestPlatform


class MultiCheckboxField(SelectMultipleField):
    """Provide multi-input checkbox."""

    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class TestForkForm(FlaskForm):
    """Form to test user's fork."""

    commit_hash = StringField('Commit Hash', [DataRequired(message='Commit hash is not filled in')])
    commit_select = RadioField('Choose Commit', choices=[('', '')], default='')
    platform = MultiCheckboxField('Platform', validators=[DataRequired()], choices=[(
        platform, platform) for platform in TestPlatform.values()])
    regression_test = MultiCheckboxField('Regression Test', validators=[DataRequired(
        message='Please add one or more Regression Tests')], coerce=int)
    add = SubmitField('Run Test')

from flask import g
from flask_wtf import FlaskForm
from wtforms import widgets, StringField, SubmitField, SelectMultipleField, RadioField, validators
from wtforms.validators import DataRequired, url
from mod_test.models import TestPlatform
from mod_regression.models import RegressionTest
from mod_auth.controllers import fetch_username_from_token
import requests

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class TestForkForm(FlaskForm):
    commit_hash = StringField('Commit Hash', [DataRequired(message='Commit hash is not filled in'), validators.Required()])
    commit_select = RadioField('Choose Commit', choices=[('', '')], default='')
    platform = MultiCheckboxField('Platform', validators=[DataRequired()], choices=[(
        platform, platform) for platform in TestPlatform.values()])
    regression_test = MultiCheckboxField('Regression Test', validators=[DataRequired(
                        message='Please add one or more Regression Tests')], coerce=int)
    add = SubmitField('Run Test')

    def __init__(self, *args, **kwargs):
        FlaskForm.__init__(self, *args, **kwargs)

    def validate(self):
        rv = FlaskForm.validate(self)
        if not rv:
            return False
        username = fetch_username_from_token()
        repository = g.github['repository']
        api_url = ('https://api.github.com/repos/{user}/{repo}/commits/{hash}').format(
            user=username, repo=repository, hash=self.commit_hash.data
        )
        response = requests.get(api_url)
        if response.status_code == 422:
            self.commit_hash.errors.append("Wrong commit hash")
            return False
        return True

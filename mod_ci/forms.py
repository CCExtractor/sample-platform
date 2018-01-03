from flask_wtf import Form
from wtforms import IntegerField, StringField, SubmitField, SelectField
from wtforms.validators import DataRequired, ValidationError


class AddUsersToBlacklist(Form):
    userID = IntegerField('Add User', [DataRequired(
        message='GitHub User ID not filled in')])
    submit = SubmitField('Login')

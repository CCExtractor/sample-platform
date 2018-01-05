from flask_wtf import Form
from wtforms import IntegerField, SubmitField
from wtforms.validators import DataRequired


class AddUsersToBlacklist(Form):
    userID = IntegerField('User ID', [DataRequired(
        message='GitHub User ID not filled in')])
    submit = SubmitField('Add User')


class RemoveUsersFromBlacklist(Form):
    userID = IntegerField('User ID', [DataRequired(
        message='GitHub User ID not filled in')])
    submit = SubmitField('Remove User')

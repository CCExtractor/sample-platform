"""contains forms related to continuous integration operations."""

from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired


class AddUsersToBlacklist(FlaskForm):
    """Form to add user to blacklist."""

    user_id = IntegerField('User ID', [DataRequired(message='GitHub User ID not filled in')])
    comment = StringField('Comment')
    add = SubmitField('Add User')


class DeleteUserForm(FlaskForm):
    """Form to remove user from blacklist."""

    submit = SubmitField('Remove')

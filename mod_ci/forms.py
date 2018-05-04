from flask_wtf import FlaskForm
from wtforms import IntegerField, SubmitField, StringField
from wtforms.validators import DataRequired


class AddUsersToBlacklist(FlaskForm):
    user_id = IntegerField('User ID', [DataRequired(message='GitHub User ID not filled in')])
    comment = StringField('Comment')
    add = SubmitField('Add User')


class RemoveUsersFromBlacklist(FlaskForm):
    user_id = IntegerField('User ID', [DataRequired(message='GitHub User ID not filled in')])
    remove = SubmitField('Remove User')

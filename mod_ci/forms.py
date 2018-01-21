from flask_wtf import Form
from wtforms import IntegerField, SubmitField, StringField
from wtforms.validators import DataRequired


class AddUsersToBlacklist(Form):
    user_id = IntegerField('User ID', [DataRequired(message='GitHub User ID not filled in')])
    comment = StringField('Comment')
    add = SubmitField('Add User')


class RemoveUsersFromBlacklist(Form):
    user_id = IntegerField('User ID', [DataRequired(message='GitHub User ID not filled in')])
    remove = SubmitField('Remove User')

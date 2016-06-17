from flask_wtf import Form
from wtforms import PasswordField, StringField, SubmitField, SelectField
from wtforms.fields.html5 import EmailField
from wtforms.validators import DataRequired, Email, ValidationError

from mod_auth.models import User, Role


def unique_username(form, field):
    # Check if a user already exists with this name
    user = User.query.filter(User.name == field.data).first()
    if user is not None:
        raise ValidationError('there is already a user with this name')


def valid_password(form, field):
    if len(field.data) == 0:
        raise ValidationError('new password cannot be empty')
    if len(field.data) < 10 or len(field.data) > 500:
        raise ValidationError('password needs to be between 10 and 500 '
                              'characters long (you entered %s characters'
                              % len(field.data))


def email_not_in_use(has_user_field=False):
    def _email_not_in_use(form, field):
        user_id = -1 if not has_user_field else form.user.id
        # Check if email is not already in use
        user = User.query.filter(User.email == field.data).first()
        if user is not None and user.id != user_id and len(field.data) > 0:
            raise ValidationError('this address is already in use')
    return _email_not_in_use


def role_id_is_valid(form, field):
    role = Role.query.filter(Role.id == field.data).first()
    if role is None:
        raise ValidationError('role id is invalid')


class LoginForm(Form):
    email = StringField('Email', [DataRequired(
        message='Email is not filled in.')])
    password = PasswordField('Password', [
        DataRequired(message='Password cannot be empty.')])
    submit = SubmitField('Login')


class SignupForm(Form):
    email = StringField('Email', [DataRequired(
        message='Email is not filled in.')])
    submit = SubmitField('Register')


class DeactivationForm(Form):
    submit = SubmitField('Deactivate account')


class RoleChangeForm(Form):
    role = SelectField('Select a role', [DataRequired(
        message='Role is not filled in.')], coerce=str)
    submit = SubmitField('Change role')


class CompleteSignupForm(Form):
    name = StringField('Name', [DataRequired(
        message='Name is not filled in.')])
    password = PasswordField('Password', [DataRequired(
        message='Password is not filled in.'), valid_password])
    password_repeat = PasswordField('Repeat password', [DataRequired(
        message='Repeated password is not filled in.')])
    submit = SubmitField('Register')

    @staticmethod
    def validate_password_repeat(form, field):
        if field.data != form.password.data:
            raise ValidationError('the password needs to match the new '
                                  'password')


class AccountForm(Form):
    def __init__(self, formdata=None, obj=None, prefix='', *args, **kwargs):
        super(AccountForm, self).__init__(formdata, obj, prefix, *args,
                                          **kwargs)
        self.user = obj

    current_password = PasswordField('Current password', [
        DataRequired(message='current password cannot be empty')
    ])
    new_password = PasswordField('New password')
    new_password_repeat = PasswordField('Repeat new password')
    name = StringField('Name', [DataRequired(
        message='Name is not filled in.')])
    email = EmailField('Email', [
        DataRequired(message='email address is not filled in'),
        Email(message='entered value is not a valid email address'),
        email_not_in_use(True)
    ])
    submit = SubmitField('Update account')

    @staticmethod
    def validate_current_password(form, field):
        if form.user is not None:
            if not form.user.is_password_valid(field.data):
                raise ValidationError('invalid password')
        else:
            raise ValidationError('user instance not passed to form '
                                  'validation')

    @staticmethod
    def validate_new_password(form, field):
        if len(field.data) == 0 and \
                        len(form.new_password_repeat.data) == 0:
            return

        valid_password(form, field)

    @staticmethod
    def validate_new_password_repeat(form, field):
        if form.email is not None:
            # Email form is present, so it's optional
            if len(field.data) == 0 and len(form.new_password.data) == 0:
                return

        if field.data != form.new_password.data:
            raise ValidationError('the password needs to match the new '
                                  'password')


class ResetForm(Form):
    email = EmailField('Email', [
        DataRequired(message='email address is not filled in'),
        Email(message='entered value is not a valid email address')
    ])
    submit = SubmitField('Request reset instructions')


class CompleteResetForm(Form):
    password = PasswordField('Password', [DataRequired(
        message='Password is not filled in.'), valid_password])
    password_repeat = PasswordField('Repeat password', [DataRequired(
        message='Repeated password is not filled in.')])
    submit = SubmitField('Reset password')

    @staticmethod
    def validate_password_repeat(form, field):
        if field.data != form.password.data:
            raise ValidationError('the password needs to match the new '
                                  'password')

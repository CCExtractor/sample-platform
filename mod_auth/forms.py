from flask_wtf import Form
from wtforms import PasswordField, StringField, SubmitField, SelectField
from wtforms.fields.html5 import EmailField
from wtforms.validators import DataRequired, Email, ValidationError

from mod_auth.models import User, Role


def unique_username(form, field):
    '''
	Check if a user already exists with this name
	'''
    user = User.query.filter(User.name == field.data).first()
    if user is not None:
        raise ValidationError('There is already a user with this name')


def valid_password(form, field):
	'''
	Function to check for validity of a password
	'''
    if len(field.data) == 0:
        raise ValidationError('new password cannot be empty')
    if len(field.data) < 10 or len(field.data) > 500:
        raise ValidationError('Password needs to be between 10 and 500 '
                              'characters long (you entered %s characters'
                              % len(field.data))


def email_not_in_use(has_user_field=False):
    def _email_not_in_use(form, field):
        user_id = -1 if not has_user_field else form.user.id
        # Check if email is not already in use
        user = User.query.filter(User.email == field.data).first()
        if user is not None and user.id != user_id and len(field.data) > 0:
            raise ValidationError('This address is already in use')
    return _email_not_in_use


def role_id_is_valid(form, field):
	'''
	Checks for validity of User's Role
	'''
    role = Role.query.filter(Role.id == field.data).first()
    if role is None:
        raise ValidationError('Role id is invalid')


class LoginForm(Form):
	'''
	Form for Login

	attr email: user's email
	type email: EmailField
	attr password: user's password
	type: PasswordField
	attr submit: Submit button
	type submit: SubmitField
	'''
    email = EmailField('Email', [
        DataRequired(message='Email address is not filled in'),
        Email(message='Entered value is not a valid email address')
    ])
    password = PasswordField('Password', [
        DataRequired(message='Password cannot be empty.')])
    submit = SubmitField('Login')


class SignupForm(Form):
	'''
	Sign up for new Users.

	attr email: Email entered during sign up
	type email: EmailField
	attr submit: Submit button
	type submit: SubmitField
	'''
    email = EmailField('Email', [
        DataRequired(message='Email address is not filled in'),
        Email(message='Entered value is not a valid email address')
    ])
    submit = SubmitField('Register')


class DeactivationForm(Form):
	'''
	Deactivate existing account
	'''
    submit = SubmitField('Deactivate account')


class RoleChangeForm(Form):
	'''
	Changing the Role

	attr role: New role to be changed to
	type role: SelectField
	'''
    role = SelectField('Select a role', [DataRequired(
        message='Role is not filled in.')], coerce=str)
    submit = SubmitField('Change role')


class CompleteSignupForm(Form):
	'''
	The Complete Sign up form for new users.

	attr name: Username
	type name: StringField
	attr password, password_repeat: The password and the repeated password
	type password, password_repeat: PasswordField
	'''
    name = StringField('Name', [DataRequired(
        message='Name is not filled in.')])
    password = PasswordField('Password', [DataRequired(
        message='Password is not filled in.'), valid_password])
    password_repeat = PasswordField('Repeat password', [DataRequired(
        message='Repeated password is not filled in.')])
    submit = SubmitField('Register')

    @staticmethod
    def validate_password_repeat(form, field):
	'''
	Validates if the repeated password is the same as 'password'
	'''
        if field.data != form.password.data:
            raise ValidationError('The password needs to match the new '
                                  'password')


class AccountForm(Form):
	'''
	Form for editing current Account
	
	attr current_password, new_password, new_password_repeat : The respective passwords.
	type current_password, new_password, new_password_repeat: PasswordField
	attr name: Username
	type name: StringField
	attr email: User's email
	type email: EmailField
	'''
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
	'''
	Validates current password entered with the password stored in database
	'''
        if form.user is not None:
            if not form.user.is_password_valid(field.data):
                raise ValidationError('Invalid password')
        else:
            raise ValidationError('User instance not passed to form '
                                  'validation')

    @staticmethod
    def validate_new_password(form, field):
	'''
	Validates the new password entered
	'''
        if len(field.data) == 0 and \
                        len(form.new_password_repeat.data) == 0:
            return

        valid_password(form, field)

    @staticmethod
    def validate_new_password_repeat(form, field):
	'''
	Validates new password repeat and checks if it matches 'new_password'
	'''
        if form.email is not None:
            # Email form is present, so it's optional
            if len(field.data) == 0 and len(form.new_password.data) == 0:
                return

        if field.data != form.new_password.data:
            raise ValidationError('The password needs to match the new '
                                  'password')


class ResetForm(Form):
	'''
	Form for resetting password

	attr email: User's email
	type email: EmailField
	'''
    email = EmailField('Email', [
        DataRequired(message='Email address is not filled in'),
        Email(message='Entered value is not a valid email address')
    ])
    submit = SubmitField('Request reset instructions')


class CompleteResetForm(Form):
	'''
	Resetting password after clicking on the link in the email

	attr password, password_repeat: The new password and its repeat
	type password, password_repeat: PasswordField
	'''
    password = PasswordField('Password', [DataRequired(
        message='Password is not filled in.'), valid_password])
    password_repeat = PasswordField('Repeat password', [DataRequired(
        message='Repeated password is not filled in.')])
    submit = SubmitField('Reset password')

    @staticmethod
    def validate_password_repeat(form, field):
	'''
	Validates new password repeat and checks if it matches 'password'
	'''
        if field.data != form.password.data:
            raise ValidationError('The password needs to match the new '
                                  'password')

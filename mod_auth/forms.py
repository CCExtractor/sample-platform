from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField, SelectField
from wtforms.fields.html5 import EmailField
from wtforms.validators import DataRequired, Email, ValidationError

from mod_auth.models import User, Role


def unique_username(form, field):
    """
    Check if a user already exists with this name

    :param form: The form which is being passed in
    :type form: Form
    :param field: The data value for the 'name' inserted by new User
    :type field : StringField
    """
    user = User.query.filter(User.name == field.data).first()
    if user is not None:
        raise ValidationError('There is already a user with this name')


def valid_password(form, field):
    """
    Function to check for validity of a password

    :param form: The form which is being passed in
    :type form: Form
    :param field: The data value for the 'password' inserted by User
    :type field : PasswordField
    """
    from run import config
    min_pwd_len = int(config['MIN_PWD_LEN'])
    max_pwd_len = int(config['MAX_PWD_LEN'])
    pass_size = len(field.data)
    if pass_size == 0:
        raise ValidationError('new password cannot be empty')
    if pass_size < min_pwd_len or pass_size > max_pwd_len:
        raise ValidationError(
            'Password needs to be between {min_pwd_len} and {max_pwd_len} characters long (you entered {char})'.format(
                min_pwd_len=min_pwd_len, max_pwd_len=max_pwd_len, char=pass_size)
        )


def email_not_in_use(has_user_field=False):
    """
    Function to check if the passed email is already in use.

    :param has_user_field : Whether an email has an existing User (False by
    default)
    :type has_user_field : boolean
    """
    def _email_not_in_use(form, field):
        user_id = -1 if not has_user_field else form.user.id
        # Check if email is not already in use
        user = User.query.filter(User.email == field.data).first()
        if user is not None and user.id != user_id and len(field.data) > 0:
            raise ValidationError('This address is already in use')

    return _email_not_in_use


def role_id_is_valid(form, field):
    """
    Checks for validity of User's Role

    :param form: The form which is being passed in
    :type form: Form
    :param field : The data value for the 'role' inserted by User
    :type field : SelectField
    """
    role = Role.query.filter(Role.id == field.data).first()
    if role is None:
        raise ValidationError('Role id is invalid')


class LoginForm(FlaskForm):
    """
    The form rendered when a User has to enter Log in credentials
    """
    email = EmailField('Email', [
        DataRequired(message='Email address is not filled in'),
        Email(message='Entered value is not a valid email address')
    ])
    password = PasswordField('Password', [DataRequired(message='Password cannot be empty.')])
    submit = SubmitField('Login')


class SignupForm(FlaskForm):
    """
    Sign up form for new Users.
    """
    email = EmailField('Email', [
        DataRequired(message='Email address is not filled in'),
        Email(message='Entered value is not a valid email address')
    ])
    submit = SubmitField('Register')


class DeactivationForm(FlaskForm):
    """
    Deactivate existing account
    """
    submit = SubmitField('Deactivate account')


class RoleChangeForm(FlaskForm):
    """
    Changing the Role
    """
    role = SelectField('Select a role', [DataRequired(message='Role is not filled in.')], coerce=str)
    submit = SubmitField('Change role')


class CompleteSignupForm(FlaskForm):
    """
    The Complete Sign up form for new users.
    """
    name = StringField('Name', [DataRequired(message='Name is not filled in.')])
    password = PasswordField('Password', [DataRequired(message='Password is not filled in.'), valid_password])
    password_repeat = PasswordField('Repeat password', [DataRequired(message='Repeated password is not filled in.')])
    submit = SubmitField('Register')

    @staticmethod
    def validate_password_repeat(form, field):
        """
        Validates if the repeated password is the same as 'password'

        :param form: The form which is being passed in
        :type form: CompleteSignupForm
        :param field : The data value for the 'password' entered by User
        :type field : PasswordField
        """
        if field.data != form.password.data:
            raise ValidationError('The password needs to match the new password')


class AccountForm(FlaskForm):
    """
    Form for editing current Account
    """
    def __init__(self, formdata=None, obj=None, prefix='', *args, **kwargs):
        super(AccountForm, self).__init__(formdata=formdata, obj=obj, prefix=prefix, *args, **kwargs)
        self.user = obj

    current_password = PasswordField('Current password', [DataRequired(message='current password cannot be empty')])
    new_password = PasswordField('New password')
    new_password_repeat = PasswordField('Repeat new password')
    name = StringField('Name', [DataRequired(message='Name is not filled in.')])
    email = EmailField('Email', [
        DataRequired(message='email address is not filled in'),
        Email(message='entered value is not a valid email address'),
        email_not_in_use(True)
    ])
    submit = SubmitField('Update account')

    @staticmethod
    def validate_current_password(form, field):
        """
        Validates current password entered with the password stored in
        database

        :param form: The form which is being passed in
        :type form: AccountForm
        :param field: The data value for the 'password' entered by User
        :type field : PasswordField
        """
        if form.user is not None:
            if not form.user.is_password_valid(field.data):
                raise ValidationError('Invalid password')
        else:
            raise ValidationError('User instance not passed to form validation')

    @staticmethod
    def validate_new_password(form, field):
        """
        Validates the new password entered

        :param form: The form which is being passed in
        :type form: AccountForm
        :param field: The data value for the 'password' entered by User
        :type field : PasswordField
        """
        if len(field.data) == 0 and len(form.new_password_repeat.data) == 0:
            return

        valid_password(form, field)

    @staticmethod
    def validate_new_password_repeat(form, field):
        """
        Validates new password repeat and checks if it matches 'new_password'

        :param form: The form which is being passed in
        :type form: AccountForm
        :param field: The data value for the 'password' entered by User
        :type field : PasswordField
        """
        if form.email is not None:
            # Email form is present, so it's optional
            if len(field.data) == 0 and len(form.new_password.data) == 0:
                return

        if field.data != form.new_password.data:
            raise ValidationError('The password needs to match the new password')


class ResetForm(FlaskForm):
    """
    Form for resetting password
    """
    email = EmailField('Email', [
        DataRequired(message='Email address is not filled in'),
        Email(message='Entered value is not a valid email address')
    ])
    submit = SubmitField('Request reset instructions')


class CompleteResetForm(FlaskForm):
    """
    Resetting password after clicking on the link in the email
    """
    password = PasswordField('Password', [DataRequired(message='Password is not filled in.'), valid_password])
    password_repeat = PasswordField('Repeat password', [DataRequired(message='Repeated password is not filled in.')])
    submit = SubmitField('Reset password')

    @staticmethod
    def validate_password_repeat(form, field):
        """
        Validates new password repeat and checks if it matches 'password'

        :param form: The form which is being passed in
        :type form: CompleteResetForm
        :param field: The data value for the 'password' entered by User
        :type field : PasswordField
        """
        if field.data != form.password.data:
            raise ValidationError('The password needs to match the new password')

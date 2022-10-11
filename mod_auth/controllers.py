"""contains all the logic related to authentication and account functionality."""

import hashlib
import hmac
import time
from functools import wraps
from typing import (Any, Callable, Dict, List, Optional, Sequence, Tuple, Type,
                    Union)

import requests
from flask import (Blueprint, abort, flash, g, redirect, request, session,
                   url_for)
from pyisemail import is_email
from werkzeug.wrappers.response import Response

from database import EnumSymbol
from decorators import get_menu_entries, template_renderer
from mod_auth.forms import (AccountForm, CompleteResetForm, CompleteSignupForm,
                            DeactivationForm, LoginForm, ResetForm,
                            RoleChangeForm, SignupForm)
from mod_auth.models import Role, User

mod_auth = Blueprint('auth', __name__)


@mod_auth.before_app_request
def before_app_request() -> None:
    """Run before the request to app is made."""
    user_id = session.get('user_id', 0)
    g.user = User.query.filter(User.id == user_id).first()
    g.menu_entries['auth'] = {
        'title': 'Log in' if g.user is None else 'Log out',
        'icon': 'sign-in' if g.user is None else 'sign-out',
        'route': 'auth.login' if g.user is None else 'auth.logout'
    }
    if g.user is None:
        g.menu_entries['signup'] = {
            'title': 'Sign up',
            'icon': 'user-plus',
            'route': 'auth.signup'
        }
    else:
        g.menu_entries['account'] = {
            'title': 'Manage account',
            'icon': 'user',
            'route': 'auth.manage'
        }
    g.menu_entries['config'] = get_menu_entries(
        g.user, 'Platform mgmt', 'cog',
        all_entries=[{'title': 'User manager', 'icon': 'users',
                      'route': 'auth.users', 'access': [Role.admin]}]  # type: ignore
    )


def login_required(f: Callable) -> Callable:
    """Decorate the function to redirect to the login page if a user is not logged in."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            g.log.warning(f'login protected endpoint {request.endpoint} accessed before logging in')
            return redirect(url_for('auth.login', next=request.endpoint))

        return f(*args, **kwargs)

    return decorated_function


def check_access_rights(roles: List[Tuple[str, str]] = None, parent_route: None = None) -> Callable:
    """
    Decorate the function to check if a user can access the page.

    :param roles: A list of roles that can access the page.
    :type roles: list[str]
    :param parent_route: If the name of the route isn't a regular page (e.g. for ajax request handling), pass the name
    of the parent route.
    :type parent_route: str
    """
    if roles is None:
        roles = []

    def access_decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            route = parent_route
            if route is None:
                route = request.endpoint
            elif route.startswith("."):
                # Relative to current blueprint, so we'll need to adjust
                route = request.endpoint[:request.endpoint.rindex('.')] + route
            if g.user.role in roles:
                return f(*args, **kwargs)
            # Return page not allowed
            g.log.warning(f'attempt to access protected endpoint {request.endpoint} without required rights')
            abort(403, request.endpoint)

        return decorated_function

    return access_decorator


def send_reset_email(usr) -> None:
    """
    Send account recovery mail to the user.

    :param usr: user from the database
    :type usr: models.User
    """
    from run import app
    expires = int(time.time()) + 86400
    content_to_hash = f"{usr.id}|{expires}|{usr.password}"
    mac = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content_to_hash)
    template = app.jinja_env.get_or_select_template('email/recovery_link.txt')
    message = template.render(
        url=url_for('.complete_reset', uid=usr.id, expires=expires, mac=mac, _external=True),
        name=usr.name
    )
    if not g.mailer.send_simple_message({
        "to": usr.email,
        "subject": "CCExtractor CI platform password recovery instructions",
        "text": message
    }):
        flash('Could not send an email. Please get in touch', 'error-message')


def github_token_validity(token: str):
    """
    Check token validity by calling GitHub V3 APIs.

    :param token: The value of 'github_token' stored in the user model
    :type token: str
    :return True/False: Returns whether token is valid or not
    :rtype: bool
    """
    from run import config
    github_client_id = config.get('GITHUB_CLIENT_ID', '')
    github_client_secret = config.get('GITHUB_CLIENT_SECRET', '')
    url = f'https://api.github.com/applications/{github_client_id}/token'
    session = requests.Session()
    session.auth = (github_client_id, github_client_secret)
    response = session.post(url, json={"access_token": token})

    return response.status_code == 200


@mod_auth.route('/github_redirect', methods=['GET', 'POST'])
def github_redirect():
    """
    Create redirect URL if no GitHub token found.

    Generate Redirect url to the GitHub page to take user permission
    only when there is no GitHub token stored for that user session.
    """
    from run import config
    github_client_id = config.get('GITHUB_CLIENT_ID', '')
    github_token = g.user.github_token
    if github_token is not None:
        validity = github_token_validity(github_token)
        if validity is False:
            g.user.github_token = None
            g.db.commit()
        else:
            g.log.error('Failed to validate GitHub token')
            return None

    return f'https://github.com/login/oauth/authorize?client_id={github_client_id}&scope=public_repo'


def fetch_username_from_token() -> Any:
    """
    Get username from the GitHub token.

    :return: username
    :rtype: str
    """
    import json
    user = User.query.filter(User.id == g.user.id).first()
    if user.github_token is None:
        return None
    url = 'https://api.github.com/user'
    session = requests.Session()
    session.auth = (user.email, user.github_token)
    try:
        response = session.get(url)
        data = response.json()
        return data['login']
    except Exception as e:
        g.log.error('Failed to fetch the user token')
        return None


@mod_auth.route('/github_callback', methods=['GET', 'POST'])
@template_renderer()
def github_callback():
    """Access the token and store it in database to for further functionalities."""
    from run import config
    if 'code' in request.args:
        """
        request access_token to the GitHub in place of payload
        payload contains client id, secret and temporary GitHub code
        """
        url = 'https://github.com/login/oauth/access_token'
        payload = {
            'client_id': config.get('GITHUB_CLIENT_ID', ''),
            'client_secret': config.get('GITHUB_CLIENT_SECRET', ''),
            'code': request.args['code']
        }
        headers = {'Accept': 'application/json'}
        r = requests.post(url, params=payload, headers=headers)
        response = r.json()

        if 'access_token' in response:
            user = User.query.filter(User.id == g.user.id).first()
            user.github_token = response['access_token']
            g.db.commit()
        else:
            g.log.error("GitHub didn't return an access token")

        return redirect(url_for('auth.manage'))

    return abort(400)


@mod_auth.route('/login', methods=['GET', 'POST'])
@template_renderer()
def login() -> Union[Response, Dict[str, Union[str, LoginForm]]]:
    """Route for handling the login page."""
    redirect_location = request.args.get('next', '')

    if session.get('user_id', None) is not None:
        flash('You are already logged in!', 'alert')
        if len(redirect_location) == 0:
            return redirect("/")
        return redirect(url_for(redirect_location))

    form = LoginForm(request.form)
    if form.validate_on_submit():
        user_to_login = User.query.filter_by(email=form.email.data).first()
        if user_to_login and user_to_login.is_password_valid(form.password.data):
            session['user_id'] = user_to_login.id
            if len(redirect_location) == 0:
                return redirect("/")
            return redirect(url_for(redirect_location))

        flash('Wrong username or password', 'error-message')

    return {
        'next': redirect_location,
        'form': form
    }


@mod_auth.route('/reset', methods=['GET', 'POST'])
@template_renderer()
def reset():
    """
    Provide form for resetting account.

    :return: form to reset
    :rtype: forms.ResetForm
    """
    form = ResetForm(request.form)
    if form.validate_on_submit():
        user_to_reset = User.query.filter_by(email=form.email.data).first()
        if user_to_reset is not None:
            send_reset_email(user_to_reset)
        flash('If an account was linked to the provided email address, an email with reset instructions has been sent. '
              'Please check your inbox.', 'success')
        form = ResetForm(None)
    return {
        'form': form
    }


@mod_auth.route('/reset/<int:uid>/<int:expires>/<mac>', methods=['GET', 'POST'])
@template_renderer()
def complete_reset(uid, expires, mac):
    """
    Complete process of account reset.

    :param uid: user id
    :type uid: int
    :param expires: integer representing time after which the link expires
    :type expires: int
    :param mac: message authentication code
    :type mac: str
    """
    from run import app

    if int(time.time()) <= expires:
        user_to_reset = User.query.filter_by(id=uid).first()
        if user_to_reset is not None:
            content_to_hash = f"{uid}|{expires}|{user_to_reset.password}"
            real_hash = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content_to_hash)
            try:
                authentic = hmac.compare_digest(real_hash, mac)
            except AttributeError:
                g.log.warning(f'falling back to direct comparison of hash...')
                # Older python version? Fallback which is less safe
                authentic = real_hash == mac
            if authentic:
                form = CompleteResetForm(request.form)
                if form.validate_on_submit():
                    user_to_reset.password = User.generate_hash(form.password.data)
                    g.db.commit()
                    template = app.jinja_env.get_or_select_template('email/password_reset.txt')
                    message = template.render(name=user_to_reset.name)
                    g.mailer.send_simple_message({
                        "to": user_to_reset.email,
                        "subject": "CCExtractor CI platform password reset",
                        "text": message
                    })
                    session['user_id'] = user_to_reset.id
                    return redirect("/")
                return {
                    'form': form,
                    'uid': uid,
                    'mac': mac,
                    'expires': expires
                }

    flash('The request to reset your password was invalid. Please enter your email again to start over.',
          'error-message')
    return redirect(url_for('.reset'))


@mod_auth.route('/signup', methods=['GET', 'POST'])
@template_renderer()
def signup() -> Dict[str, SignupForm]:
    """Route for handling the signup page."""
    from run import app
    form = SignupForm(request.form)
    if form.validate_on_submit():
        if is_email(form.email.data):
            # Check if user exists
            user_that_exists = User.query.filter_by(email=form.email.data).first()
            if user_that_exists is None:
                expires = int(time.time()) + 86400
                content_to_hash = f"{form.email.data}|{expires}"
                hmac_hash = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content_to_hash)
                # New user
                template = app.jinja_env.get_or_select_template('email/registration_email.txt')
                message = template.render(url=url_for(
                    '.complete_signup', email=form.email.data, expires=expires, mac=hmac_hash, _external=True)
                )
            else:
                # Existing user
                template = app.jinja_env.get_or_select_template('email/registration_existing.txt')
                message = template.render(url=url_for('.reset', _external=True), name=user_that_exists.name)
            if g.mailer.send_simple_message({
                "to": form.email.data,
                "subject": "CCExtractor CI platform registration",
                "text": message
            }):
                flash('Email sent for verification purposes. Please check your mailbox', 'success')
                form = SignupForm(None)
            else:
                flash('Could not send email', 'error-message')
        else:
            g.log.debug(f'sign up attempt using invalid email id: {form.email.data}')
            flash('Invalid email address!', 'error-message')

    return {
        'form': form
    }


@mod_auth.route('/complete_signup/<email>/<int:expires>/<mac>',
                methods=['GET', 'POST'])
@template_renderer()
def complete_signup(email: str, expires: int,
                    mac: str) -> Union[Response, Dict[str, Union[CompleteSignupForm, str, int]]]:
    """
    Complete user signup.

    :param email: email address of the user
    :type email: str
    :param expires: integer representing time after which the link expires
    :type expires: int
    :param mac: message authentication code
    :type mac: str
    """
    from run import app

    if int(time.time()) <= expires:
        content_to_hash = f"{email}|{expires}"
        real_hash = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content_to_hash)
        try:
            authentic = hmac.compare_digest(real_hash, mac)
        except AttributeError:
            g.log.warning(f'falling back to direct comparison of hash...')
            # Older python version? Fallback which is less safe
            authentic = real_hash == mac
        if authentic:
            # Check if email already exists (sign up twice with same email)
            user_that_exists = User.query.filter_by(email=email).first()
            if user_that_exists is not None:
                flash('There is already a user with this email address registered.', 'error-message')
                return redirect(url_for('.signup'))
            form = CompleteSignupForm()
            if form.validate_on_submit():
                user_to_register = User(form.name.data, email=email, password=User.generate_hash(form.password.data))
                g.db.add(user_to_register)
                g.db.commit()
                session['user_id'] = user_to_register.id
                template = app.jinja_env.get_or_select_template('email/registration_ok.txt')
                message = template.render(name=user_to_register.name)
                g.mailer.send_simple_message({
                    "to": user_to_register.email,
                    "subject": "Welcome to the CCExtractor CI platform",
                    "text": message
                })
                return redirect('/')
            return {
                'form': form,
                'email': email,
                'expires': expires,
                'mac': mac
            }
        else:
            g.log.error('Invalid HMAC')

    else:
        g.log.error('HMAC expired')
    flash('The request to complete the registration was invalid. Please enter your email again to start over.',
          'error-message')
    return redirect(url_for('.signup'))


def generate_hmac_hash(key: str, data: str) -> str:
    """
    Accept key and data in any format and encodes it into bytes.

    :param key: HMAC hash key
    :type key: str
    :param data: content to be hashed separated by '|'
    :type data: str
    :return: cryptographic hash of data combined with key
    :rtype: str
    """
    encoded_key = bytes(key, 'latin-1')
    encoded_data = bytes(data, 'latin-1')
    return hmac.new(encoded_key, encoded_data, hashlib.sha256).hexdigest()


@mod_auth.route('/logout')
@template_renderer()
def logout():
    """
    Destroy session variable.

    Return user to the login page.
    """
    session.pop('user_id', None)
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('.login'))


@mod_auth.route('/manage', methods=['GET', 'POST'])
@login_required
@template_renderer()
def manage():
    """Allow editing or accessing account details."""
    from run import app
    form = AccountForm(request.form, g.user)
    if form.validate_on_submit():
        user_to_update = User.query.filter(User.id == g.user.id).first()
        old_email = None
        password = False
        if user_to_update.email != form.email.data:
            old_email = user_to_update.email
            user_to_update.email = form.email.data
        if len(form.new_password.data) >= 10:
            password = True
            user_to_update.password = User.generate_hash(form.new_password.data)
        if user_to_update.name != form.name.data:
            user_to_update.name = form.name.data
        g.user = user_to_update
        g.db.commit()
        if old_email is not None:
            template = app.jinja_env.get_or_select_template('email/email_changed.txt')
            message = template.render(name=user_to_update.name, email=user_to_update.email)
            g.mailer.send_simple_message({
                "to": [old_email, user_to_update.email],
                "subject": "CCExtractor CI platform email changed",
                "text": message
            })
        if password:
            template = app.jinja_env.get_or_select_template('email/password_changed.txt')
            message = template.render(name=user_to_update.name)
            to = user_to_update.email if old_email is None else [old_email, user_to_update.email]
            g.mailer.send_simple_message({
                "to": to,
                "subject": "CCExtractor CI platform password changed",
                "text": message
            })
        flash('Settings saved')
    github_url = github_redirect()
    return {
        'form': form,
        'url': github_url
    }


@mod_auth.route('/users')
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def users():
    """
    Get list of all users.

    :return: list of all users in a dictionary
    :rtype: dict
    """
    return {
        'users': User.query.order_by(User.name.asc()).all()
    }


@mod_auth.route('/user/<int:uid>')
@login_required
@template_renderer()
def user(uid):
    """
    View user and samples provided by the user.

    Only give access if the uid matches the user, or if the user is an admin.

    :param uid: id of the user
    :type uid: int
    :return: user view and samples if valid response, appropriate error otherwise
    :rtype: dynamic
    """
    from mod_upload.models import Upload
    if g.user.id == uid or g.user.role == Role.admin:
        usr = User.query.filter_by(id=uid).first()
        if usr is not None:
            uploads = Upload.query.filter(Upload.user_id == usr.id).all()
            return {
                'view_user': usr,
                'samples': [u.sample for u in uploads]
            }
        g.log.debug(f'user with id: {uid} not found!')
        abort(404)
    else:
        abort(403, request.endpoint)


@mod_auth.route('/reset_user/<int:uid>')
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def reset_user(uid):
    """
    Reset user password by admin.

    Only give access if the uid matches the user, or if the user is an admin.

    :param uid: id of the user
    :type uid: int
    :return: user view if valid response, appropriate error otherwise
    :rtype: dynamic
    """
    if g.user.id == uid or g.user.role == Role.admin:
        usr = User.query.filter_by(id=uid).first()
        if usr is not None:
            send_reset_email(usr)
            return {
                'view_user': usr
            }
        g.log.debug(f'user with id: {uid} not found!')
        abort(404)
    else:
        g.log.warning(f'user with id: {g.user.id} tried to access restricted endpoint for user id: {uid}!')
        abort(403, request.endpoint)


@mod_auth.route('/role/<int:uid>', methods=['GET', 'POST'])
@login_required
@check_access_rights([Role.admin])
@template_renderer()
def role(uid):
    """
    View and change user's role.

    :param uid: id of the user
    :type uid: int
    :return: role form and user view if valid response, appropriate error otherwise
    :rtype: dynamic
    """
    usr = User.query.filter_by(id=uid).first()
    if usr is not None:
        form = RoleChangeForm(request.form)
        form.role.choices = [(r.name, r.description) for r in Role]
        if form.validate_on_submit():
            usr.role = Role.from_string(form.role.data)
            g.db.commit()
            return redirect(url_for('.users'))
        form.role.data = usr.role.name
        return {
            'form': form,
            'view_user': usr
        }
    g.log.debug(f'user with id: {uid} not found!')
    abort(404)


@mod_auth.route('/deactivate/<int:uid>', methods=['GET', 'POST'])
@login_required
@template_renderer()
def deactivate(uid):
    """
    Deactivate user account.

    Only give access if the uid matches the user, or if the user is an admin

    :param uid: id of the user
    :type uid: int
    :return: DeactivationForm and user view if valid response, appropriate error otherwise
    :rtype: dynamic
    """
    if g.user.id == uid or g.user.role == Role.admin:
        usr = User.query.filter_by(id=uid).first()
        if usr is not None:
            form = DeactivationForm(request.form)
            if form.validate_on_submit():
                # Deactivate user
                usr.name = f"Anonymous {usr.id}"
                usr.email = f"unknown{usr.id}@ccextractor.org"
                usr.password = User.create_random_password(16)
                g.db.commit()
                if g.user.role == Role.admin:
                    return redirect(url_for('.users'))
                else:
                    session.pop('user_id', None)
                    g.log.debug(f'account deactivate for user id: {uid}')
                    flash('Account deactivated.', 'success')
                    return redirect(url_for('.login'))
            return {
                'form': form,
                'view_user': usr
            }
        g.log.debug(f'user with id: {uid} not found!')
        abort(404)
    else:
        abort(403, request.endpoint)

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

import database
import mod_auth.forms
import mod_auth.models
from database import EnumSymbol
from decorators import get_menu_entries, template_renderer
from mod_auth.forms import (AccountForm, CompleteResetForm, CompleteSignupForm,
                            DeactivationForm, LoginForm, ResetForm,
                            RoleChangeForm, SignupForm)
from mod_auth.models import Role, User

mod_auth = Blueprint('auth', __name__)  # type: ignore


@mod_auth.before_app_request    # type: ignore
def before_app_request() -> None:
    """Run before the request to app is made."""
    user_id = session.get('user_id', 0)
    g.user = User.query.filter(User.id == user_id).first()
    g.menu_entries['auth'] = {
        'title': 'Log in' if g.user is None else 'Log out',
        'icon': 'sign-in' if g.user is None else 'sign-out',
        'route': 'auth.login' if g.user is None else 'auth.logout'
    }
    if g.user is not None:
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
    content_to_hash = "{id}|{expiry}|{passwd}".format(id=usr.id, expiry=expires, passwd=usr.password)
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
    Check token validity by calling Github V3 APIs.

    :param token: The value of 'github_token' stored in the user model
    :type token: str
    :return True/False: Returns whether token is valid or not
    :rtype: bool
    """
    from run import config
    github_clientid = config.get('GITHUB_CLIENT_ID', '')
    github_clientsecret = config.get('GITHUB_CLIENT_SECRET', '')
    url = 'https://api.github.com/applications/{id}/tokens/{token}'.format(id=github_clientid, token=token)
    session = requests.Session()
    session.auth = (github_clientid, github_clientsecret)
    response = session.get(url)

    return response.status_code == 200


@mod_auth.route('/github_redirect', methods=['GET', 'POST'])    # type: ignore
def github_redirect():
    """
    Create redirect URL if no github token found.

    Generate Redirect url to the Github page to take user permisssion
    only when there is no github token stored for that user session.
    """
    from run import config
    github_clientid = config.get('GITHUB_CLIENT_ID', '')
    github_token = g.user.github_token
    if github_token is not None:
        validity = github_token_validity(github_token)
        if validity is False:
            g.user.github_token = None
            g.db.commit()
        else:
            return None

    return 'https://github.com/login/oauth/authorize?client_id={id}&scope=public_repo'.format(id=github_clientid)


def fetch_username_from_token() -> Any:
    """
    Get username from the Github token.

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


@mod_auth.route('/github_callback', methods=['GET', 'POST'])    # type: ignore
@template_renderer()
def github_callback():
    """Access the token and store it in database to for further functionalities."""
    from run import config
    if 'code' in request.args:
        """
        request access_token to the github in place of payload
        payload contains client id, secret and temporary github code
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

        # get access_token from response and store in session
        if 'access_token' in response:
            user = User.query.filter(User.id == g.user.id).first()
            user.github_token = response['access_token']
            g.db.commit()
        else:
            g.log.error('github didn\'t return an access token')

        # send authenticated user where they're supposed to go
        return redirect(url_for('auth.manage'))

    return '', 404


@mod_auth.route('/login', methods=['GET', 'POST'])      # type: ignore
@template_renderer()
def login() -> Union[Response, Dict[str, Union[str, LoginForm]]]:
    """Route for handling the login page."""
    # fetching redirect_location from the request
    redirect_location = request.args.get('next', '')

    # redirect already logged in user
    if session.get('user_id', None) is not None:
        flash('You are already logged in!', 'alert')
        if len(redirect_location) == 0:
                return redirect("/")
        else:
            return redirect(url_for(redirect_location))

    form = LoginForm(request.form)
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        # saving session and redirecting on valid password
        if user and user.is_password_valid(form.password.data):
            session['user_id'] = user.id
            if len(redirect_location) == 0:
                return redirect("/")
            else:
                return redirect(url_for(redirect_location))

        flash('Wrong username or password', 'error-message')

    return {
        'next': redirect_location,
        'form': form
    }


@mod_auth.route('/reset', methods=['GET', 'POST'])  # type: ignore
@template_renderer()
def reset():
    """
    Provide form for resetting account.

    :return: form to reset
    :rtype: forms.ResetForm
    """
    form = ResetForm(request.form)
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None:
            send_reset_email(user)
        flash('If an account was linked to the provided email address, an email with reset instructions has been sent. '
              'Please check your inbox.', 'success')
        form = ResetForm(None)
    return {
        'form': form
    }


@mod_auth.route('/reset/<int:uid>/<int:expires>/<mac>', methods=['GET', 'POST'])    # type: ignore
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
    # Check if time expired
    now = int(time.time())
    if now <= expires:
        user = User.query.filter_by(id=uid).first()
        if user is not None:
            # Validate HMAC
            content_to_hash = "{id}|{expiry}|{passwd}".format(id=uid, expiry=expires, passwd=user.password)
            real_hash = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content_to_hash)
            try:
                authentic = hmac.compare_digest(real_hash, mac)
            except AttributeError:
                # Older python version? Fallback which is less safe
                authentic = real_hash == mac
            if authentic:
                form = CompleteResetForm(request.form)
                if form.validate_on_submit():
                    user.password = User.generate_hash(form.password.data)
                    g.db.commit()
                    template = app.jinja_env.get_or_select_template('email/password_reset.txt')
                    message = template.render(name=user.name)
                    g.mailer.send_simple_message({
                        "to": user.email,
                        "subject": "CCExtractor CI platform password reset",
                        "text": message
                    })
                    session['user_id'] = user.id
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


@mod_auth.route('/signup', methods=['GET', 'POST'])  # type: ignore
@template_renderer()
def signup() -> Dict[str, SignupForm]:
    """Route for handling the signup page."""
    from run import app
    form = SignupForm(request.form)
    if form.validate_on_submit():
        if is_email(form.email.data):
            # Check if user exists
            user = User.query.filter_by(email=form.email.data).first()
            if user is None:
                expires = int(time.time()) + 86400
                content_to_hash = "{email}|{expiry}".format(email=form.email.data, expiry=expires)
                hmac_hash = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content_to_hash)
                # New user
                template = app.jinja_env.get_or_select_template('email/registration_email.txt')
                message = template.render(url=url_for(
                    '.complete_signup', email=form.email.data, expires=expires, mac=hmac_hash, _external=True)
                )
            else:
                # Existing user
                template = app.jinja_env.get_or_select_template('email/registration_existing.txt')
                message = template.render(url=url_for('.reset', _external=True), name=user.name)
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
            flash('Invalid email address!', 'error-message')

    return {
        'form': form
    }


@mod_auth.route('/complete_signup/<email>/<int:expires>/<mac>',     # type: ignore
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
    # Check if time expired
    now = int(time.time())
    if now <= expires:
        # Validate HMAC
        content_to_hash = "{email}|{expiry}".format(email=email, expiry=expires)
        real_hash = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content_to_hash)
        try:
            authentic = hmac.compare_digest(real_hash, mac)
        except AttributeError:
            # Older python version? Fallback which is less safe
            authentic = real_hash == mac
        if authentic:
            # Check if email already exists (sign up twice with same email)
            user = User.query.filter_by(email=email).first()
            if user is not None:
                flash('There is already a user with this email address registered.', 'error-message')
                return redirect(url_for('.signup'))
            form = CompleteSignupForm()
            if form.validate_on_submit():
                user = User(form.name.data, email=email, password=User.generate_hash(form.password.data))
                g.db.add(user)
                g.db.commit()
                session['user_id'] = user.id
                # Send email
                template = app.jinja_env.get_or_select_template('email/registration_ok.txt')
                message = template.render(name=user.name)
                g.mailer.send_simple_message({
                    "to": user.email,
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


@mod_auth.route('/logout')  # type: ignore
@template_renderer()
def logout():
    """
    Destroy session variable.

    Return user to the login page.
    """
    session.pop('user_id', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('.login'))


@mod_auth.route('/manage', methods=['GET', 'POST'])     # type: ignore
@login_required
@template_renderer()
def manage():
    """Allow editing or accessing account details."""
    from run import app
    form = AccountForm(request.form, g.user)
    if form.validate_on_submit():
        user = User.query.filter(User.id == g.user.id).first()
        old_email = None
        password = False
        if user.email != form.email.data:
            old_email = user.email
            user.email = form.email.data
        if len(form.new_password.data) >= 10:
            password = True
            user.password = User.generate_hash(form.new_password.data)
        if user.name != form.name.data:
            user.name = form.name.data
        g.user = user
        g.db.commit()
        if old_email is not None:
            template = app.jinja_env.get_or_select_template('email/email_changed.txt')
            message = template.render(name=user.name, email=user.email)
            g.mailer.send_simple_message({
                "to": [old_email, user.email],
                "subject": "CCExtractor CI platform email changed",
                "text": message
            })
        if password:
            template = app.jinja_env.get_or_select_template('email/password_changed.txt')
            message = template.render(name=user.name)
            to = user.email if old_email is None else [old_email, user.email]
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


@mod_auth.route('/users')   # type: ignore
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


@mod_auth.route('/user/<int:uid>')  # type: ignore
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
        abort(404)
    else:
        abort(403, request.endpoint)


@mod_auth.route('/reset_user/<int:uid>')    # type: ignore
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
        abort(404)
    else:
        abort(403, request.endpoint)


@mod_auth.route('/role/<int:uid>', methods=['GET', 'POST'])     # type: ignore
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
            # Update role
            usr.role = Role.from_string(form.role.data)
            g.db.commit()
            return redirect(url_for('.users'))
        form.role.data = usr.role.name
        return {
            'form': form,
            'view_user': usr
        }
    abort(404)


@mod_auth.route('/deactivate/<int:uid>', methods=['GET', 'POST'])   # type: ignore
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
                usr.name = "Anonymized {id}".format(id=usr.id)
                usr.email = "unknown{id}@ccextractor.org".format(id=usr.id)
                usr.password = User.create_random_password(16)
                g.db.commit()
                if g.user.role == Role.admin:
                    return redirect(url_for('.users'))
                else:
                    session.pop('user_id', None)
                    flash('Account deactivated.', 'success')
                    return redirect(url_for('.login'))
            return {
                'form': form,
                'view_user': usr
            }
        abort(404)
    else:
        abort(403, request.endpoint)

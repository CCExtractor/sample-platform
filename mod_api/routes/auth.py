"""
Token lifecycle, caller identity, account and admin user management.

POST   /auth/tokens          Authenticate with email/password, get a token
GET    /auth/tokens          List tokens (admin-only; ?all=true for all users)
DELETE /auth/tokens/current   Revoke the token you're currently using
DELETE /auth/tokens/{id}      Revoke a specific token by ID
GET    /auth/me              Identity, role and scopes behind the token
PATCH  /auth/me              Change your own name, email or password
POST   /auth/signup          Send a registration link
POST   /auth/password-reset  Send a password reset link
POST   /auth/password-reset/complete
                             Set a new password from a reset link
GET    /auth/me/ftp-credentials
                             Your own FTP details for the ingest server
GET    /auth/me/github       Whether your account is connected to GitHub
DELETE /auth/me/github       Forget this platform's copy of that connection
GET    /users                List platform users (admin)
GET    /users/{id}           One platform user (admin)
PATCH  /users/{id}           Change a user's role (admin)
POST   /users/{id}/deactivate  Anonymise an account (admin, or your own)
POST   /users/{id}/password-reset
                             Send someone a reset link (admin, or your own)

Signup and reset send the same emails as the classic pages and reuse their
signed links, so accounts are still created and passwords still set by one
implementation rather than two.
"""

import hmac
import time

from flask import g, request, url_for
from passlib.apps import custom_app_context as pwd_context
from sqlalchemy.exc import IntegrityError

from mod_api import mod_api
from mod_api.middleware.auth import require_roles, require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_body,
                                           validate_offset_pagination,
                                           validate_path_id)
from mod_api.models.api_token import DEFAULT_SCOPES, ApiToken, Scope
from mod_api.schemas.auth import (AccountUpdateSchema, ApiTokenItemSchema,
                                  AuthTokenSchema, EmailOnlySchema,
                                  PasswordResetCompleteSchema,
                                  RoleUpdateSchema, TokenCreateRequestSchema)
from mod_api.utils import paginated_response, single_response
from mod_auth.models import Role, User

_DUMMY_HASH = pwd_context.hash('__dummy__')

# Signup and reset links last a day, matching the classic pages.
_LINK_TTL = 86400


def _send(to, subject, text):
    """Send one email, logging rather than failing when the mailer says no."""
    if not g.mailer.send_simple_message(
            {'to': to, 'subject': subject, 'text': text}):
        g.log.error(f'could not send "{subject}" to {to}')


def _send_reset_link(user):
    """
    Email a password reset link to one user.

    The signature and the template are the classic ones, so a link from
    here and a link from the classic page are interchangeable. What cannot
    be reused is mod_auth's own send_reset_email: it builds the URL with a
    relative endpoint, which resolves against whichever blueprint is
    handling the request and so cannot be built from inside this one.

    Where CONSOLE_URL names a web console, the link points there instead,
    so somebody who started in the console is not handed to a second site
    to finish. The console posts the same three values back to
    /auth/password-reset/complete, so the link means the same thing either
    way. Unset, which is every existing install, nothing changes.
    """
    from mod_auth.controllers import generate_hmac_hash
    from run import app

    expires = int(time.time()) + _LINK_TTL
    mac = generate_hmac_hash(
        app.config.get('HMAC_KEY', ''),
        f'{user.id}|{expires}|{user.password}')
    console = app.config.get('CONSOLE_URL', '')
    if console:
        url = (f"{console.rstrip('/')}/reset"
               f'?uid={user.id}&expires={expires}&mac={mac}')
    else:
        url = url_for('auth.complete_reset', uid=user.id, expires=expires,
                      mac=mac, _external=True)
    template = app.jinja_env.get_or_select_template('email/recovery_link.txt')
    _send(user.email,
          'CCExtractor CI platform password recovery instructions',
          template.render(url=url, name=user.name))


def _invalid_reset_link():
    """
    Build the single reply every bad reset link gets.

    Expired, unknown user and bad signature deliberately share one message:
    telling them apart would confirm which accounts exist.
    """
    return make_error_response(
        'invalid_link',
        'This reset link is invalid or has expired. Request a new one.',
        http_status=400)


@mod_api.route('/auth/tokens', methods=['POST'])
@validate_body(TokenCreateRequestSchema)
def create_token(validated_data=None):
    """
    Authenticate with email + password and issue a scoped API token.

    The plaintext token value is returned exactly once in this response.
    It's never stored or logged — only the SHA-256 hash is persisted
    (see ApiToken: the token is a 256-bit random secret, so a fast hash
    with constant-time compare is sufficient).
    """
    email = validated_data['email']
    password = validated_data['password']
    token_name = validated_data['token_name']
    expires_in_days = validated_data.get('expires_in_days', 7)
    scopes = validated_data.get('scopes') or DEFAULT_SCOPES

    user = User.query.filter_by(email=email).first()

    # Hash password even if user is not found to prevent timing attacks
    if user is None:
        try:
            pwd_context.verify(password, _DUMMY_HASH)
        except Exception:
            pass
        return make_error_response(
            'invalid_credentials',
            'Invalid email or password.',
            http_status=401,
        )

    if not user.is_password_valid(password):
        return make_error_response(
            'invalid_credentials',
            'Invalid email or password.',
            http_status=401,
        )

    # Check role limitations
    # Note: Plain 'user' role deliberately cannot request tokens:manage. They
    # can create tokens with runs:write but cannot list them. They must revoke
    # either the current token or by ID.
    allowed_scopes = {
        Scope.RUNS_READ, Scope.RUNS_WRITE, Scope.RESULTS_READ,
        Scope.SYSTEM_READ,
    }
    if user.is_admin:
        allowed_scopes.add(Scope.TOKENS_MANAGE)
        allowed_scopes.add(Scope.BASELINES_WRITE)
        allowed_scopes.add(Scope.SYSTEM_WRITE)

    invalid_scopes = set(scopes) - allowed_scopes
    if invalid_scopes:
        return make_error_response(
            'forbidden',
            f'Your current role ({user.role.value}) does not permit requesting '
            f'the following scopes: {", ".join(invalid_scopes)}.',
            http_status=403,
        )

    plaintext = ApiToken.generate_token()
    token_hash = ApiToken.hash_token(plaintext)
    token_prefix = ApiToken.extract_prefix(plaintext)

    api_token = ApiToken(
        user_id=user.id,
        token_name=token_name,
        token_hash=token_hash,
        token_prefix=token_prefix,
        scopes=scopes,
        expires_in_days=expires_in_days,
    )
    g.db.add(api_token)

    try:
        g.db.commit()
    except IntegrityError as e:
        g.db.rollback()
        error_msg = str(e).lower()
        if 'uq_user_token_name' in error_msg or 'api_token.user_id, api_token.token_name' in error_msg:
            # Names stay reserved even after revocation (the unique
            # constraint spans revoked rows, kept for audit history),
            # so "revoke and retry" would not free the name.
            return make_error_response(
                'validation_error',
                f'Token name "{token_name}" already exists for this user. '
                'Names remain reserved after revocation; choose a new name.',
                details={'fields': {
                    'token_name': 'Already in use (including by revoked '
                                  'tokens). Choose a different name.'}},
                http_status=400,
            )
        raise

    return single_response(
        {
            'token': plaintext,
            'token_type': 'bearer',
            'token_name': token_name,
            'scopes': scopes,
            'expires_at': api_token.expires_at,
        },
        schema=AuthTokenSchema(),
        http_status=201,
    )


@mod_api.route('/auth/tokens/current', methods=['DELETE'])
def revoke_current_token():
    """Revoke whatever token is in the Authorization header right now.

    Note: This endpoint is intentionally scope-free. Any valid token
    is allowed to revoke itself regardless of its scopes.
    """
    token = getattr(g, 'api_token', None)
    if token is None:
        return make_error_response(
            'unauthorized',
            'No token found in the current request.',
            http_status=401,
        )
    token.revoke()
    g.db.add(token)
    g.db.commit()
    return '', 204


@mod_api.route('/auth/tokens', methods=['GET'])
@require_roles([Role.admin])
@require_scope(Scope.TOKENS_MANAGE)
@validate_offset_pagination()
def list_tokens(limit=50, offset=0):
    """
    List API tokens, paginated. Admin-only.

    tokens:manage is an admin-only scope (see create_token), so the
    require_roles guard above already rejects everyone else with 403.
    Lists the caller's own tokens by default; pass ?all=true to list
    every token in the system.
    """
    want_all = request.args.get('all', 'false').lower() == 'true'

    if want_all:
        query = ApiToken.query.order_by(ApiToken.created_at.desc())
    else:
        query = ApiToken.query.filter_by(
            user_id=g.api_user.id,
        ).order_by(ApiToken.created_at.desc())

    total = query.count()
    tokens = query.offset(offset).limit(limit).all()
    schema = ApiTokenItemSchema(many=True)

    return paginated_response(tokens, total, limit, offset, schema=schema)


@mod_api.route('/auth/tokens/<int:token_id>', methods=['DELETE'])
def revoke_specific_token(token_id):
    """
    Revoke a token by its numeric ID.

    Non-admins can only revoke their own tokens. Admins can revoke anyone's.
    Already-revoked tokens are silently accepted (idempotent).

    Deliberately requires no extra scope: scopes gate data access, while
    revocation is self-service credential hygiene. Any valid token may
    revoke tokens belonging to its own user — plain users cannot obtain
    tokens:manage (see create_token), yet must be able to clean up their
    own credentials.
    """
    is_admin = g.api_user.is_admin
    token = ApiToken.query.filter_by(id=token_id).first()

    # Non-admins get a uniform 404 for both "doesn't exist" and "belongs to
    # another user" to prevent token-ID enumeration.
    is_own = token is not None and token.user_id == g.api_user.id
    if not token or (not is_admin and not is_own):
        return make_error_response('not_found', 'Token not found.', http_status=404)

    # Reaching here means the caller is either the owner or an admin (any other
    # caller was already given a 404 above), so the revocation is authorized.
    if not token.is_revoked:
        token.revoke()
        g.db.add(token)
        g.db.commit()

    return '', 204


@mod_api.route('/auth/me', methods=['GET'])
def get_current_user():
    """
    Return the identity, role and scopes behind the calling token.

    Needs no extra scope: it reports on the caller itself and discloses
    nothing another endpoint would withhold.
    """
    return single_response({
        'user_id': g.api_user.id,
        'name': g.api_user.name,
        'email': g.api_user.email,
        'role': g.api_user.role.value,
        'scopes': g.api_token.scopes if g.api_token else [],
    })


def _serialize_user(user):
    """Public shape of a user; omits password hash and GitHub token."""
    return {
        'user_id': user.id,
        'name': user.name,
        'email': user.email,
        'role': user.role.value,
        'github_linked': bool(user.github_login),
        'github_login': user.github_login,
    }


@mod_api.route('/users', methods=['GET'])
@require_roles([Role.admin])
@require_scope(Scope.TOKENS_MANAGE)
@validate_offset_pagination()
def list_users(limit=50, offset=0):
    """List platform users, oldest first."""
    query = User.query.order_by(User.id.asc())
    total = query.count()
    users = query.offset(offset).limit(limit).all()
    return paginated_response(
        [_serialize_user(user) for user in users], total, limit, offset)


@mod_api.route('/users/<user_id>', methods=['PATCH'])
@require_roles([Role.admin])
@require_scope(Scope.TOKENS_MANAGE)
@validate_path_id('user_id')
@validate_body(RoleUpdateSchema)
def update_user_role(user_id, validated_data=None):
    """
    Change a user's role.

    Admins cannot change their own role: demoting the last admin here
    would leave nobody able to undo it.
    """
    user = User.query.filter(User.id == user_id).first()
    if user is None:
        return make_error_response(
            'not_found', f'User {user_id} not found.', http_status=404)

    if user.id == g.api_user.id:
        return make_error_response(
            'forbidden', 'You cannot change your own role.', http_status=403)

    previous_role = user.role.value
    user.role = Role.from_string(validated_data['role'])
    g.db.commit()

    g.log.info(f'user {user.id} role {previous_role} -> {user.role.value} '
               f'by admin {g.api_user.id}')
    return single_response(_serialize_user(user))


@mod_api.route('/auth/signup', methods=['POST'])
@validate_body(EmailOnlySchema)
def signup(validated_data=None):
    """
    Send a registration link to an email address.

    Answers the same way whether or not the address is already registered,
    because a different reply here would tell an anonymous caller who has an
    account. The link lands on the classic completion page, which is where
    the account is actually created: two places able to mint accounts is a
    surface worth not having.
    """
    from mod_auth.controllers import generate_hmac_hash
    from run import app

    email = validated_data['email']
    existing = User.query.filter_by(email=email).first()

    if existing is None:
        expires = int(time.time()) + _LINK_TTL
        mac = generate_hmac_hash(
            app.config.get('HMAC_KEY', ''), f'{email}|{expires}')
        url = url_for('auth.complete_signup', email=email, expires=expires,
                      mac=mac, _external=True)
        template = 'email/registration_email.txt'
        message = app.jinja_env.get_or_select_template(template).render(url=url)
    else:
        url = url_for('auth.reset', _external=True)
        template = 'email/registration_existing.txt'
        message = app.jinja_env.get_or_select_template(template).render(
            url=url, name=existing.name)

    _send(email, 'CCExtractor CI platform registration', message)
    return single_response({'sent': True}, http_status=202)


@mod_api.route('/auth/password-reset', methods=['POST'])
@validate_body(EmailOnlySchema)
def request_password_reset(validated_data=None):
    """
    Send a password reset link.

    Silent about whether the address is registered, for the same reason
    signup is.
    """
    user = User.query.filter_by(email=validated_data['email']).first()
    if user is not None:
        _send_reset_link(user)
    return single_response({'sent': True}, http_status=202)


@mod_api.route('/auth/password-reset/complete', methods=['POST'])
@validate_body(PasswordResetCompleteSchema)
def complete_password_reset(validated_data=None):
    """
    Set a new password using a link from the reset email.

    The signature covers the current password hash, so a link stops working
    the moment it is used or the password changes by any other route. The
    caller is not signed in here: they still have to authenticate, which
    proves the new password arrived intact.
    """
    from mod_auth.controllers import generate_hmac_hash
    from run import app

    data = validated_data
    if int(time.time()) > data['expires']:
        return _invalid_reset_link()

    user = User.query.filter_by(id=data['user_id']).first()
    if user is None:
        return _invalid_reset_link()

    expected = generate_hmac_hash(
        app.config.get('HMAC_KEY', ''),
        f"{data['user_id']}|{data['expires']}|{user.password}")
    if not hmac.compare_digest(expected, data['mac']):
        return _invalid_reset_link()

    user.password = User.generate_hash(data['password'])
    g.db.commit()

    template = app.jinja_env.get_or_select_template('email/password_reset.txt')
    _send(user.email, 'CCExtractor CI platform password reset',
          template.render(name=user.name))

    g.log.info(f'password reset completed via API for user {user.id}')
    return single_response({'user_id': user.id, 'password_changed': True})


@mod_api.route('/auth/me', methods=['PATCH'])
@validate_body(AccountUpdateSchema)
def update_account(validated_data=None):
    """
    Change your own name, email or password.

    Touching the email or the password needs the current one as well: the
    bearer token proves the request came from a signed-in session, not that
    the person sending it knows the account's own credentials.
    """
    data = validated_data
    if not data or set(data) == {'current_password'}:
        return make_error_response(
            'validation_error', 'No fields to update.', http_status=400)

    user = g.api_user
    sensitive = {'email', 'new_password'} & set(data)
    if sensitive:
        current = data.get('current_password')
        if not current or not user.is_password_valid(current):
            return make_error_response(
                'forbidden',
                'current_password is required and must match to change '
                'your email or password.',
                http_status=403)

    if 'email' in data and data['email'] != user.email:
        if User.query.filter_by(email=data['email']).first() is not None:
            return make_error_response(
                'conflict', 'That email is already in use.', http_status=409)
        user.email = data['email']

    if 'name' in data:
        user.name = data['name']
    if 'new_password' in data:
        user.password = User.generate_hash(data['new_password'])

    try:
        g.db.commit()
    except IntegrityError:
        # name and email are both unique, so a race lands here.
        g.db.rollback()
        return make_error_response(
            'conflict', 'That name or email is already in use.',
            http_status=409)

    g.log.info(f'user {user.id} updated their own account: '
               f'{sorted(k for k in data if k != "current_password")}')
    return single_response(_serialize_user(user))


@mod_api.route('/users/<user_id>/deactivate', methods=['POST'])
@validate_path_id('user_id')
def deactivate_user(user_id):
    """
    Anonymise an account and lock it out.

    The row stays so the uploads and runs it owns keep an author, which is
    why this scrubs the identity instead of deleting. Open to admins and to
    the account's owner, matching the classic page.

    Scope-free for the same reason revoking your own token is: closing your
    own account cannot depend on tokens:manage, which no role below admin is
    ever allowed to hold. Ownership is checked below instead.

    The account's own tokens are revoked as part of this. Scrambling the
    password only stops new ones being minted, and an admin reaching for
    this because somebody is abusing the platform means to end the access
    they already have, not to leave it running for up to thirty days.

    Tokens belonging to the caller are untouched unless they are the same
    account, so an admin doing this to somebody else keeps working.
    """
    caller = g.api_user
    if caller.role != Role.admin and caller.id != int(user_id):
        return make_error_response(
            'forbidden', 'You can only deactivate your own account.',
            http_status=403)

    user = User.query.filter(User.id == user_id).first()
    if user is None:
        return make_error_response(
            'not_found', f'User {user_id} not found.', http_status=404)

    user.name = f'Anonymous {user.id}'
    user.email = f'unknown{user.id}@ccextractor.org'
    user.password = User.generate_hash(User.create_random_password(16))

    revoked = 0
    for token in ApiToken.query.filter(ApiToken.user_id == user.id).all():
        if not token.is_revoked:
            token.revoke()
            revoked += 1
    g.db.commit()

    g.log.warning(f'user {user.id} deactivated via API by {caller.id}, '
                  f'{revoked} token(s) revoked')
    return single_response({
        'user_id': user.id,
        'deactivated': True,
        'tokens_revoked': revoked,
    })


@mod_api.route('/users/<user_id>', methods=['GET'])
@require_roles([Role.admin])
@require_scope(Scope.TOKENS_MANAGE)
@validate_path_id('user_id')
def get_user(user_id):
    """Return one platform user."""
    user = User.query.filter(User.id == user_id).first()
    if user is None:
        return make_error_response(
            'not_found', f'User {user_id} not found.', http_status=404)
    return single_response(_serialize_user(user))


@mod_api.route('/users/<user_id>/password-reset', methods=['POST'])
@validate_path_id('user_id')
def send_user_password_reset(user_id):
    """
    Send a reset link to another account, or to your own.

    Unlike the public /auth/password-reset this names an account rather than
    an address, so it says plainly when the id is unknown: the caller is
    already signed in and can list users anyway.

    Scope-free for the same reason deactivation is: asking for a reset on
    your own account cannot depend on tokens:manage.
    """
    caller = g.api_user
    if caller.role != Role.admin and caller.id != int(user_id):
        return make_error_response(
            'forbidden', 'You can only request a reset for your own account.',
            http_status=403)

    user = User.query.filter(User.id == user_id).first()
    if user is None:
        return make_error_response(
            'not_found', f'User {user_id} not found.', http_status=404)

    _send_reset_link(user)

    g.log.info(f'password reset link sent to user {user.id} by {caller.id}')
    return single_response({'user_id': user.id, 'sent': True},
                           http_status=202)


@mod_api.route('/auth/me/ftp-credentials', methods=['GET'])
@require_scope(Scope.RUNS_WRITE)
def get_ftp_credentials():
    """
    Return the caller's FTP details, creating them on first ask.

    Only ever the caller's own: these are working credentials, so there is
    no version of this that reads someone else's. The password is stored in
    the clear by design (it is random and cannot be chosen), so this is the
    only place it can come from.

    Behind runs:write rather than open to any token, unlike the rest of
    /auth/me: FTP is another way to upload a sample, so a token narrowed to
    reading has no business fetching a working credential for it. Every
    role holds runs:write, so this narrows tokens without narrowing people.
    """
    from mod_upload.controllers import retrieve_ftp_credentials
    from run import config

    credentials = retrieve_ftp_credentials(g.api_user.id)
    return single_response({
        'host': config.get('SERVER_NAME', ''),
        'port': config.get('FTP_PORT', ''),
        'username': credentials.user_name,
        'password': credentials.password,
    })


@mod_api.route('/auth/me/github', methods=['GET'])
def get_github_link():
    """
    Say whether the caller's account is connected to GitHub.

    Connecting is a browser redirect, so this hands back the URL to send
    somebody to rather than performing it. Trading the code GitHub returns
    for a token stays on the classic callback: that needs the client
    secret and the redirect registered with GitHub, and one place holding
    those is better than two.

    The stored token is never part of this response. The URL carries only
    the client id and the scope asked for, both of which are public.
    """
    from run import config

    user = g.api_user
    client_id = config.get('GITHUB_CLIENT_ID', '')
    return single_response({
        'linked': user.github_token is not None,
        'github_login': user.github_login,
        'authorize_url': (
            'https://github.com/login/oauth/authorize'
            f'?client_id={client_id}&scope=public_repo'),
    })


@mod_api.route('/auth/me/github', methods=['DELETE'])
def unlink_github():
    """
    Forget this platform's copy of the caller's GitHub connection.

    Only ever the caller's own, like the FTP details above. This drops the
    token the platform holds; the authorisation itself is withdrawn from
    GitHub's own applications page, which is the only place that can
    really end it.
    """
    user = g.api_user
    user.github_token = None
    user.github_login = None
    g.db.commit()

    g.log.info(f'user {user.id} disconnected GitHub via API')
    return single_response({'linked': False, 'github_login': None})

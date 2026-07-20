"""
Token lifecycle: create, list, and revoke API tokens.

POST   /auth/tokens          Authenticate with email/password, get a token
GET    /auth/tokens          List tokens (admin-only; ?all=true for all users)
DELETE /auth/tokens/current   Revoke the token you're currently using
DELETE /auth/tokens/{id}      Revoke a specific token by ID
"""

from flask import g, request
from passlib.apps import custom_app_context as pwd_context
from sqlalchemy.exc import IntegrityError

from mod_api import mod_api
from mod_api.middleware.auth import require_roles, require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_body,
                                           validate_offset_pagination)
from mod_api.models.api_token import DEFAULT_SCOPES, ApiToken, Scope
from mod_api.schemas.auth import (ApiTokenItemSchema, AuthTokenSchema,
                                  TokenCreateRequestSchema)
from mod_api.utils import paginated_response, single_response
from mod_auth.models import Role, User

_DUMMY_HASH = pwd_context.hash('__dummy__')


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

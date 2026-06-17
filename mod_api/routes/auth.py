"""
Token lifecycle: create, list, and revoke API tokens.

POST   /auth/tokens          Authenticate with email/password, get a token
GET    /auth/tokens          List tokens (own tokens; admin can see all)
DELETE /auth/tokens/current   Revoke the token you're currently using
DELETE /auth/tokens/{id}      Revoke a specific token by ID
"""

from flask import g, request
from passlib.apps import custom_app_context as pwd_context

from mod_api import mod_api
from mod_api.middleware.auth import require_roles, require_scope
from mod_api.middleware.error_handler import make_error_response
from mod_api.middleware.validation import (validate_body,
                                           validate_offset_pagination)
from mod_api.models.api_token import DEFAULT_SCOPES, ApiToken
from mod_api.schemas.auth import (ApiTokenItemSchema, AuthTokenSchema,
                                  TokenCreateRequestSchema)
from mod_api.utils import paginated_response, single_response
from mod_auth.models import User

_DUMMY_HASH = pwd_context.hash('__dummy__')


@mod_api.route('/auth/tokens', methods=['POST'])
@validate_body(TokenCreateRequestSchema)
def create_token(validated_data=None):
    """
    Authenticate with email + password and issue a scoped API token.

    The plaintext token value is returned exactly once in this response.
    It's never stored or logged — only the argon2 hash is persisted.
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
    allowed_scopes = {
        'runs:read', 'runs:write', 'results:read',
        'system:read', 'tokens:manage'
    }
    if user.role.value == 'admin':
        allowed_scopes.add('baselines:write')

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

    from sqlalchemy.exc import IntegrityError
    try:
        g.db.commit()
    except IntegrityError as e:
        g.db.rollback()
        error_msg = str(e).lower()
        if 'uq_user_token_name' in error_msg or 'duplicate' in error_msg:
            return make_error_response(
                'validation_error',
                f'Token name "{token_name}" already exists for this user.',
                details={'fields': {
                    'token_name': 'Already in use. Revoke the existing token first.'}},
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
    """Revoke whatever token is in the Authorization header right now."""
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
@require_roles(['admin', 'contributor', 'tester'])
@require_scope('tokens:manage')
@validate_offset_pagination()
def list_tokens(limit=50, offset=0):
    """
    List tokens for the current user, paginated.

    Admins can pass ?all=true to see every token in the system.
    Non-admins who try ?all=true get a 403.
    """
    want_all = request.args.get('all', 'false').lower() == 'true'
    is_admin = g.api_user.role.value == 'admin'

    if want_all and not is_admin:
        return make_error_response(
            'forbidden',
            'Only admins may list all tokens.',
            details={'required_roles': ['admin']},
            http_status=403,
        )

    if want_all and is_admin:
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
    """
    is_admin = g.api_user.role.value == 'admin'
    token = ApiToken.query.filter_by(id=token_id).first()

    # Non-admins get a uniform 404 for both "doesn't exist" and "belongs to
    # another user" to prevent token-ID enumeration.
    is_own = token is not None and token.user_id == g.api_user.id
    if not token or (not is_admin and not is_own):
        return make_error_response('not_found', 'Token not found.', http_status=404)

    if not is_own and not g.api_token.has_scope('tokens:manage'):
        return make_error_response('forbidden', 'Cross-user revocation requires tokens:manage scope.', http_status=403)

    if not token.is_revoked:
        token.revoke()
        g.db.add(token)
        g.db.commit()

    return '', 204

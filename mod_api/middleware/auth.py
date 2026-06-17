"""
Bearer token authentication and scope/role enforcement for API routes.

Runs as a before_request hook on the api blueprint. Public endpoints
(token creation, health check) are exempted. On success, the authenticated
user and token are stored in flask.g for downstream handlers.

HTTP semantics:
    401 = token missing, expired, revoked, or invalid
    403 = valid token but insufficient scope or role
"""

import functools
from typing import List

from flask import g, request

from mod_api import mod_api
from mod_api.middleware.error_handler import make_error_response
from mod_api.models.api_token import ApiToken

_AUTH_FAILED_MSG = 'Bearer token is missing, expired, or invalid.'

# These endpoints bypass auth entirely.
_PUBLIC_ENDPOINTS = frozenset([
    'api.create_token',       # POST /auth/tokens (uses email/password body)
    'api.system_health',      # GET /system/health (uptime monitoring)
])


def _unauthorized():
    """Shorthand for a 401 response with the standard auth failure message."""
    from mod_api.middleware.rate_limit import check_rate_limit
    rate_limit_resp = check_rate_limit()
    if rate_limit_resp:
        return rate_limit_resp

    return make_error_response(
        'unauthorized', _AUTH_FAILED_MSG, http_status=401)


@mod_api.before_request
def authenticate_request():
    """Validate Bearer token and attach user context to the request."""
    if request.endpoint in _PUBLIC_ENDPOINTS:
        g.api_user = None
        g.api_token = None
        return

    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return _unauthorized()

    parts = auth_header.split(' ', 1)
    if len(parts) != 2 or parts[0] != 'Bearer':
        return _unauthorized()

    token_value = parts[1].strip()
    if not token_value or not token_value.startswith('spci_'):
        return _unauthorized()

    # Look up by prefix, then verify the full hash against each candidate.
    prefix = ApiToken.extract_prefix(token_value)
    candidates = ApiToken.query.filter_by(token_prefix=prefix).all()

    if not candidates:
        return _unauthorized()

    matched_token = None
    for candidate in candidates:
        if ApiToken.verify_token(token_value, candidate.token_hash):
            matched_token = candidate
            break

    if matched_token is None:
        return _unauthorized()

    if not matched_token.is_valid:
        return _unauthorized()

    g.api_token = matched_token
    g.api_user = matched_token.user


def require_scope(*scopes: str):
    """Reject the request if the token lacks any of the ``scopes``."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            token = getattr(g, 'api_token', None)
            if token is None:
                return _unauthorized()

            missing_scopes = [s for s in scopes if not token.has_scope(s)]
            if missing_scopes:
                return make_error_response(
                    'forbidden',
                    'Token lacks the required scopes for this operation.',
                    details={
                        'required_scopes': list(scopes),
                        'missing_scopes': missing_scopes,
                        'token_scopes': token.scopes,
                    },
                    http_status=403,
                )
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_roles(roles: List[str]):
    """Reject the request if the user's role is not in ``roles``."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            user = getattr(g, 'api_user', None)
            if user is None:
                return _unauthorized()
            if user.role.value not in roles:
                return make_error_response(
                    'forbidden',
                    'Your role does not have permission for this operation.',
                    details={
                        'required_roles': roles,
                        'user_role': user.role.value,
                    },
                    http_status=403,
                )
            return f(*args, **kwargs)
        return decorated_function
    return decorator

"""Structured JSON error responses for API routes."""

from flask import current_app, jsonify, request
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy.exc import SQLAlchemyError

from mod_api import mod_api

_API_PREFIX = '/api/v1'


def make_error_response(code, message, details=None, http_status=400):
    """Build a JSON error response conforming to the ErrorResponse schema."""
    body = {
        'code': code,
        'message': str(message)[:500],
        'details': details if details is not None else {},
    }
    response = jsonify(body)
    response.status_code = http_status
    return response


@mod_api.errorhandler(400)
def handle_400(error):
    """Bad request."""
    return make_error_response(
        'validation_error',
        getattr(error, 'description', 'Bad request.'),
        http_status=400,
    )


@mod_api.errorhandler(401)
def handle_401(error):
    """Unauthorized."""
    return make_error_response(
        'unauthorized',
        'Bearer token is missing, expired, or invalid.',
        http_status=401,
    )


@mod_api.errorhandler(403)
def handle_403(error):
    """Forbidden."""
    return make_error_response(
        'forbidden',
        'Token does not have the required scope for this operation.',
        http_status=403,
    )


@mod_api.errorhandler(404)
def handle_404(error):
    """Not found."""
    return make_error_response(
        'not_found',
        getattr(error, 'description', 'Resource not found.'),
        http_status=404,
    )


@mod_api.errorhandler(405)
def handle_405(error):
    """Handle method-not-allowed errors for API routes."""
    resp = make_error_response(
        'method_not_allowed',
        'Method not allowed.',
        http_status=405,
    )
    if hasattr(error, 'valid_methods') and error.valid_methods:
        resp.headers['Allow'] = ', '.join(error.valid_methods)
    return resp


@mod_api.errorhandler(422)
def handle_422(error):
    """Unprocessable entity."""
    return make_error_response(
        'unprocessable',
        getattr(
            error,
            'description',
            'Request is valid JSON but semantically invalid.'),
        http_status=422,
    )


@mod_api.errorhandler(429)
def handle_429(error):
    """Rate limited.

    This is only a fallback for 429s raised outside the rate-limit
    middleware. The live limiter (mod_api.middleware.rate_limit) returns
    accurate per-bucket limit/retry_after/window values and the
    Retry-After header; we deliberately don't hardcode numbers here that
    would be wrong for the auth (5/15m) and write (20/min) buckets.
    """
    return make_error_response(
        'rate_limited',
        'Rate limit exceeded.',
        http_status=429,
    )


@mod_api.errorhandler(500)
def handle_500(error):
    """Handle unexpected server errors for API routes."""
    current_app.logger.exception(error)
    return make_error_response(
        'internal_error',
        'An unexpected error occurred.',
        http_status=500,
    )


@mod_api.errorhandler(MarshmallowValidationError)
def handle_marshmallow_validation_error(error):
    """Catch schema validation failures and return them as 400."""
    return make_error_response(
        'validation_error',
        'Request failed schema validation.',
        details={'fields': error.messages},
        http_status=400,
    )


@mod_api.errorhandler(SQLAlchemyError)
def handle_sqlalchemy_error(error):
    """Log database errors."""
    current_app.logger.exception(error)
    return make_error_response(
        'internal_error',
        'An unexpected database error occurred.',
        http_status=500,
    )


def convert_api_errors_to_json(response):
    """Catch routing errors that were handled by global app handlers and convert them to JSON."""
    if request.path.startswith(_API_PREFIX):
        if response.status_code >= 500 and not response.is_json:
            new_resp = make_error_response(
                'internal_error', 'An unexpected error occurred.', http_status=response.status_code
            )
            response.data = new_resp.data
            response.mimetype = new_resp.mimetype
            return response
        if response.status_code == 404 and not response.is_json:
            new_resp = make_error_response('not_found', 'Resource not found.', http_status=404)
            response.data = new_resp.data
            response.mimetype = new_resp.mimetype
            return response
        if response.status_code == 405 and not response.is_json:
            new_resp = make_error_response('method_not_allowed', 'Method not allowed.', http_status=405)
            response.data = new_resp.data
            response.mimetype = new_resp.mimetype
            return response
    return response

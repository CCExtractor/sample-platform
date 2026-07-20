"""
Request validation decorators for bodies, query params, and path IDs.

All of these return 400 with field-level details on failure, so route
handlers can assume clean input.
"""

from datetime import datetime, timezone
from functools import wraps

from flask import request
from marshmallow import ValidationError as MarshmallowValidationError

from mod_api.middleware.error_handler import make_error_response

# Whitelist of allowed sort params.
ALLOWED_RUN_SORTS = frozenset([
    'created_at', '-created_at',
    'run_id', '-run_id',
])


def validate_body(schema_class):
    """Validate the JSON body with a schema, pass result as ``validated_data``."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            content_type = request.content_type or ''
            if content_type.split(';')[0].strip() != 'application/json':
                return make_error_response(
                    'validation_error',
                    'Content-Type must be application/json.',
                    http_status=415,
                )
            json_data = request.get_json(silent=True)
            if json_data is None:
                return make_error_response(
                    'validation_error',
                    'Request body must be valid JSON.',
                    http_status=400,
                )
            schema = schema_class()
            try:
                validated = schema.load(json_data)
            except MarshmallowValidationError as e:
                return make_error_response(
                    'validation_error',
                    'Request failed schema validation.',
                    details={'fields': e.messages},
                    http_status=400,
                )
            kwargs['validated_data'] = validated
            return f(*args, **kwargs)
        return decorated
    return decorator


def validate_offset_pagination(default_limit=50):
    """Extract and validate ``limit`` and ``offset`` query params."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'cursor' in request.args:
                return make_error_response(
                    'validation_error',
                    'Cannot mix cursor and offset pagination.',
                    details={'fields': {
                        'cursor': 'Cannot specify cursor when using offset pagination.'}},
                    http_status=400,
                )

            try:
                limit = int(request.args.get('limit', default_limit))
            except (ValueError, TypeError):
                return make_error_response(
                    'validation_error',
                    'limit must be an integer.',
                    details={'fields': {
                        'limit': 'Must be an integer between 1 and 100.'}},
                    http_status=400,
                )

            try:
                offset = int(request.args.get('offset', 0))
            except (ValueError, TypeError):
                return make_error_response(
                    'validation_error',
                    'offset must be a non-negative integer.',
                    details={'fields': {
                        'offset': 'Must be a non-negative integer.'}},
                    http_status=400,
                )

            if limit < 1 or limit > 100:
                return make_error_response(
                    'validation_error',
                    'limit must be between 1 and 100.',
                    details={'fields': {'limit': 'Must be between 1 and 100.'}},
                    http_status=400,
                )

            if offset < 0:
                return make_error_response(
                    'validation_error',
                    'offset must be non-negative.',
                    details={'fields': {'offset': 'Must be >= 0.'}},
                    http_status=400,
                )

            if offset > 2147483647:
                return make_error_response(
                    'validation_error',
                    'offset is too large.',
                    details={'fields': {'offset': 'Must be <= 2147483647.'}},
                    http_status=400,
                )

            kwargs['limit'] = limit
            kwargs['offset'] = offset
            return f(*args, **kwargs)
        return decorated
    return decorator


def _parse_limit(default_limit):
    try:
        limit = int(request.args.get('limit', default_limit))
    except (ValueError, TypeError):
        return None, make_error_response(
            'validation_error',
            'limit must be an integer.',
            details={'fields': {'limit': 'Must be an integer between 1 and 100.'}},
            http_status=400,
        )

    if limit < 1 or limit > 100:
        return None, make_error_response(
            'validation_error',
            'limit must be between 1 and 100.',
            details={'fields': {'limit': 'Must be between 1 and 100.'}},
            http_status=400,
        )
    return limit, None


def _parse_cursor():
    cursor = request.args.get('cursor')
    if cursor is None:
        return None, None
    try:
        cursor = int(cursor)
    except (ValueError, TypeError):
        return None, make_error_response(
            'validation_error',
            'cursor must be an integer.',
            details={'fields': {'cursor': 'Must be an integer.'}},
            http_status=400,
        )
    if cursor < 0:
        return None, make_error_response(
            'validation_error',
            'cursor must be non-negative.',
            details={'fields': {'cursor': 'Must be >= 0.'}},
            http_status=400,
        )
    if cursor > 10_000_000:
        return None, make_error_response(
            'validation_error',
            'cursor out of range.',
            details={'fields': {'cursor': 'Must be <= 10000000.'}},
            http_status=400,
        )
    return cursor, None


def validate_cursor_pagination(default_limit=50):
    """Extract and validate ``limit`` and ``cursor`` query params."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'offset' in request.args:
                return make_error_response(
                    'validation_error',
                    'Cannot mix cursor and offset pagination.',
                    details={'fields': {
                        'offset': 'Cannot specify offset when using cursor pagination.'}},
                    http_status=400,
                )

            limit, err = _parse_limit(default_limit)
            if err:
                return err

            cursor, err = _parse_cursor()
            if err:
                return err

            kwargs['limit'] = limit
            kwargs['cursor'] = cursor
            return f(*args, **kwargs)
        return decorated
    return decorator


def validate_path_id(param_name):
    """Ensure a URL path parameter is a positive integer."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            value = kwargs.get(param_name)
            try:
                int_value = int(value)
            except (ValueError, TypeError):
                return make_error_response(
                    'validation_error',
                    f'{param_name} must be a positive integer.',
                    details={
                        'fields': {
                            param_name: 'Must be a positive integer.'}},
                    http_status=400,
                )
            if int_value < 1 or int_value > 2147483647:
                return make_error_response(
                    'validation_error',
                    f'{param_name} must be between 1 and 2147483647.',
                    details={
                        'fields': {
                            param_name: 'Must be between 1 and 2147483647. Out of bounds IDs are rejected.'
                        }
                    },
                    http_status=400,
                )
            kwargs[param_name] = int_value
            return f(*args, **kwargs)
        return decorated
    return decorator


def _parse_iso8601_date(param_name, param_str):
    if not param_str:
        return None, None
    try:
        dt = datetime.fromisoformat(param_str.replace('Z', '+00:00'))
    except ValueError:
        return None, make_error_response(
            'validation_error',
            f'{param_name} must be a valid ISO 8601 datetime.',
            details={'fields': {param_name: 'Invalid ISO 8601 format.'}},
            http_status=400,
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt, None


def validate_date_range(f):
    """Parse date query params and reject inverted ranges."""
    @wraps(f)
    def decorated(*args, **kwargs):
        created_after_str = request.args.get('created_after')
        created_before_str = request.args.get('created_before')

        created_after, err = _parse_iso8601_date('created_after', created_after_str)
        if err:
            return err

        created_before, err = _parse_iso8601_date('created_before', created_before_str)
        if err:
            return err

        if created_after and created_before and created_after > created_before:
            return make_error_response(
                'validation_error',
                'created_after cannot be later than created_before.',
                details={'fields': {
                    'created_after': 'Cannot be after created_before.'}},
                http_status=400,
            )

        kwargs['created_after'] = created_after
        kwargs['created_before'] = created_before
        return f(*args, **kwargs)
    return decorated


def validate_sort(allowed=None):
    """Validate the ``sort`` query param against a whitelist."""
    if allowed is None:
        allowed = ALLOWED_RUN_SORTS

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            sort = request.args.get('sort', '-created_at')
            if sort not in allowed:
                return make_error_response(
                    'validation_error',
                    f'sort must be one of: {", ".join(sorted(allowed))}',
                    details={
                        'fields': {
                            'sort': f'Must be one of: {sorted(allowed)}'
                        }
                    },
                    http_status=400,
                )
            kwargs['sort'] = sort
            return f(*args, **kwargs)
        return decorated
    return decorator

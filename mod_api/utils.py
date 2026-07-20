"""Pagination, serialization, and response formatting helpers."""

from flask import jsonify


def paginated_response(data, total, limit, offset, schema=None, truncated=False, extra_meta=None):
    """Build an offset-paginated JSON response."""
    if schema:
        serialized = schema.dump(data, many=True)
    else:
        serialized = data

    next_offset = offset + limit if (offset + limit) < total else None

    pagination = {
        'limit': limit,
        'offset': offset,
        'total': total,
        'next_offset': next_offset,
    }

    if truncated:
        pagination['truncated'] = True

    response = {
        'data': serialized,
        'pagination': pagination,
        'meta': {}
    }
    if extra_meta:
        response['meta'].update(extra_meta)

    return jsonify(response)


def cursor_paginated_response(data, next_cursor, limit, schema=None):
    """Build a cursor-paginated JSON response."""
    if schema:
        serialized = schema.dump(data, many=True)
    else:
        serialized = data

    return jsonify({
        'data': serialized,
        'pagination': {
            'limit': limit,
            'next_cursor': next_cursor,
        },
    })


def single_response(data, schema=None, http_status=200):
    """Build a single-item JSON response."""
    if schema:
        serialized = schema.dump(data)
    else:
        serialized = data

    response = jsonify(serialized)
    response.status_code = http_status
    return response


def get_sort_column(sort_param, column_map):
    """Translate a sort string into an SQLAlchemy order_by clause.

    Handles descending sorts prefixed with '-' (e.g. '-created_at').
    """
    descending = sort_param.startswith('-')
    # [1:] not lstrip('-'): lstrip would also swallow a second leading dash,
    # silently normalizing bad input like '--created_at'.
    field_name = sort_param[1:] if descending else sort_param

    column = column_map.get(field_name)
    if column is None:
        return None

    if descending:
        return column.desc()
    return column.asc()


def safe_resolve(base_path, filename):
    """
    Resolve filename under base_path, rejecting path traversal.

    Returns the absolute path if it's safely within base_path,
    or None if traversal was detected.
    """
    import os
    resolved = os.path.realpath(os.path.join(base_path, filename))
    base_real = os.path.realpath(base_path)
    if not resolved.startswith(base_real + os.sep) and resolved != base_real:
        return None
    return resolved

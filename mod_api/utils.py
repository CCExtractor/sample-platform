"""Pagination, serialization, and response formatting helpers."""

from flask import jsonify


def paginated_response(data, total, limit, offset, schema=None, truncated=False):
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

    return jsonify({
        'data': serialized,
        'pagination': pagination,
    })


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
    field_name = sort_param.lstrip('-')

    column = column_map.get(field_name)
    if column is None:
        return None

    if descending:
        return column.desc()
    return column.asc()

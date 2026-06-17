"""Shared schemas: ErrorResponse and pagination wrappers."""

from marshmallow import Schema, fields


class ErrorResponseSchema(Schema):
    """Standard JSON error body returned by all error responses."""

    code = fields.String(required=True)
    message = fields.String(required=True)
    details = fields.Dict(keys=fields.String(), required=True, load_default={})


class PaginationSchema(Schema):
    """Offset-based pagination metadata."""

    limit = fields.Integer(required=True)
    offset = fields.Integer(required=True)
    total = fields.Integer(required=True)
    next_offset = fields.Integer(allow_none=True, load_default=None)


class CursorPaginationSchema(Schema):
    """Cursor-based pagination metadata."""

    limit = fields.Integer(required=True)
    next_cursor = fields.Integer(allow_none=True, load_default=None)

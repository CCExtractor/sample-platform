"""Schemas for error items, error summary buckets, and log lines."""

from marshmallow import Schema, fields, validate

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class ErrorItemSchema(Schema):
    """A single error derived from run results or infra progress."""

    error_id = fields.String(required=True)
    run_id = fields.Integer(required=True)
    sample_id = fields.Integer(allow_none=True)
    regression_id = fields.Integer(allow_none=True)
    type = fields.String(required=True)
    severity = fields.String(
        required=True,
        validate=validate.OneOf(['info', 'warning', 'error', 'critical']),
    )
    message = fields.String(required=True)
    location = fields.Dict(allow_none=True, load_default=None)
    stack = fields.List(fields.String(), load_default=None)
    occurred_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)


class ErrorSummaryBucketSchema(Schema):
    """One bucket in a grouped error summary."""

    key = fields.String(required=True)
    count = fields.Integer(required=True)
    severity = fields.String(required=True)
    group_by = fields.String(allow_none=True)
    sample_ids = fields.List(fields.Integer(), load_default=[])
    first_seen_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    last_seen_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)


class LogLineSchema(Schema):
    """A single parsed line from a build log."""

    timestamp = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    level = fields.String(
        required=True,
        validate=validate.OneOf(
            ['debug', 'info', 'warning', 'error', 'critical']),
    )
    source = fields.String(
        required=True,
        validate=validate.OneOf(
            ['orchestrator', 'worker', 'build', 'test_runner', 'web']),
    )
    message = fields.String(required=True)
    run_id = fields.Integer(required=True)
    sample_id = fields.Integer(allow_none=True)

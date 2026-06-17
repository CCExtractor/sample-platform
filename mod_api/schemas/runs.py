"""Schemas for runs, summaries, progress events, and run actions."""

from marshmallow import RAISE, Schema, fields, validate

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class ProgressEventSchema(Schema):
    """A single progress event in a run's timeline."""

    timestamp = fields.DateTime(required=True, format=DATETIME_FORMAT)
    status = fields.String(required=True)
    message = fields.String(required=True)
    step = fields.Integer(allow_none=True)


class RunSchema(Schema):
    """Full run details."""

    run_id = fields.Integer(required=True)
    status = fields.String(required=True, validate=validate.OneOf([
        'queued', 'running', 'pass', 'fail', 'canceled', 'incomplete',
    ]))
    platform = fields.String(
        required=True, validate=validate.OneOf(['linux', 'windows']))
    test_type = fields.String(validate=validate.OneOf(['commit', 'pr']))
    repository = fields.String(required=True)
    branch = fields.String(allow_none=True)
    commit_sha = fields.String(required=True)
    pr_number = fields.Integer(allow_none=True, load_default=None)
    created_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    queued_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    started_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    completed_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    github_link = fields.String(allow_none=True)


class RunSummarySchema(Schema):
    """Pass/fail/skip aggregate counts for a run."""

    run_id = fields.Integer(required=True)
    status = fields.String(required=True)
    total_samples = fields.Integer(required=True)
    pass_count = fields.Integer(required=True)
    fail_count = fields.Integer(required=True)
    skipped_count = fields.Integer(required=True)
    missing_output_count = fields.Integer(required=True)
    error_count = fields.Integer(load_default=0)
    duration_ms = fields.Integer(allow_none=True)
    triggered_by = fields.String(allow_none=True)


class RunConfigSchema(Schema):
    """The test matrix and configuration for a run."""

    run_id = fields.Integer(required=True)
    platform = fields.String(required=True)
    branch = fields.String(required=True)
    commit_sha = fields.String(required=True)
    regression_test_ids = fields.List(fields.Integer(), required=True)


class RunCreateRequestSchema(Schema):
    """POST /runs request body."""

    commit_sha = fields.String(
        required=True,
        validate=validate.Regexp(
            r'^[a-fA-F0-9]{40}$',
            error='commit_sha must be a 40-character hex string.',
        ),
    )
    platform = fields.String(
        required=True,
        validate=validate.OneOf(['linux', 'windows']),
    )
    branch = fields.String(
        load_default='master',
        validate=[
            validate.Length(max=100),
            validate.Regexp(
                r'^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$',
                error='branch must match ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$',
            ),
        ],
    )
    repository = fields.String(
        required=True,
        validate=[
            validate.Length(max=100),
            validate.Regexp(
                r'^[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+$',
                error='repository must match owner/repo format.',
            ),
        ],
    )
    pull_request = fields.Integer(
        load_default=None,
        allow_none=True,
        validate=validate.Range(min=1, max=2147483647),
    )
    regression_test_ids = fields.List(
        fields.Integer(validate=validate.Range(min=1, max=2147483647)),
        load_default=None,
        validate=validate.Length(max=500),
    )

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class RunActionResultSchema(Schema):
    """Response for cancel and similar run actions."""

    run_id = fields.Integer(required=True)
    action = fields.String(required=True)
    status = fields.String(required=True)
    message = fields.String(required=True)

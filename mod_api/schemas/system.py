"""Schemas for health checks, queue jobs, and run artifacts."""

from marshmallow import Schema, fields, validate

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class DependencyHealthSchema(Schema):
    """Status of a single system dependency (DB, GCS, local storage)."""

    name = fields.String(required=True)
    status = fields.String(
        required=True, validate=validate.OneOf(['ok', 'degraded', 'down']))
    message = fields.String(allow_none=True)


class SystemHealthSchema(Schema):
    """Overall system health response."""

    status = fields.String(
        required=True,
        validate=validate.OneOf(['ok', 'degraded', 'down']),
    )
    checked_at = fields.DateTime(required=True, format=DATETIME_FORMAT)
    dependencies = fields.List(
        fields.Nested(DependencyHealthSchema),
        required=True)


class QueueJobSchema(Schema):
    """A single queued or running job."""

    run_id = fields.Integer(required=True)
    status = fields.String(
        required=True, validate=validate.OneOf(['queued', 'running']))
    platform = fields.String(
        required=True, validate=validate.OneOf(['linux', 'windows']))
    queued_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    started_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    position = fields.Integer(allow_none=True)


class ArtifactSchema(Schema):
    """A downloadable artifact tied to a run."""

    artifact_id = fields.String(required=True)
    run_id = fields.Integer(required=True)
    sample_id = fields.Integer(allow_none=True)
    type = fields.String(
        required=True,
        validate=validate.OneOf([
            'build_log', 'sample_output', 'expected_output', 'actual_output',
            'diff', 'media_info', 'binary', 'coredump', 'combined_stdout',
        ]),
    )
    filename = fields.String(required=True)
    content_type = fields.String(required=True)
    size_bytes = fields.Integer(allow_none=True)
    storage_status = fields.String(
        required=True,
        validate=validate.OneOf(['ok', 'degraded', 'missing']),
    )
    download_url = fields.String(allow_none=True)

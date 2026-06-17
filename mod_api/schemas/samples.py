"""Request and response schemas for Sample endpoints and results."""

from marshmallow import Schema, fields, validate


class OutputFileSchema(Schema):
    """Output file schema."""

    output_id = fields.Integer(required=True)
    filename = fields.String(required=True)
    status = fields.String(required=True, validate=validate.OneOf([
        'pass', 'fail', 'missing_output',
    ]))


class RunSampleSchema(Schema):
    """A regression test's result within a specific run."""

    regression_test_id = fields.Integer(required=True)
    sample_id = fields.Integer(allow_none=True)
    sample_name = fields.String(allow_none=True)
    status = fields.String(required=True, validate=validate.OneOf([
        'pass', 'fail', 'skipped', 'missing_output', 'running', 'not_started',
    ]))
    exit_code = fields.Integer(allow_none=True)
    expected_rc = fields.Integer(allow_none=True)
    runtime_ms = fields.Integer(allow_none=True)
    command = fields.String(allow_none=True)
    categories = fields.List(fields.String(), load_default=[])
    outputs = fields.List(fields.Nested(OutputFileSchema), load_default=[])


class SampleSchema(Schema):
    """A media sample from the catalog."""

    sample_id = fields.Integer(required=True)
    sha = fields.String(required=True)
    extension = fields.String(required=True)
    original_name = fields.String(required=True)
    filename = fields.String(required=True)
    tags = fields.List(fields.String(), load_default=[])
    regression_test_count = fields.Integer(load_default=0)
    active = fields.Boolean(load_default=True)


class SampleHistoryEntrySchema(Schema):
    """One row in a sample's cross-run history."""

    run_id = fields.Integer(required=True)
    regression_test_id = fields.Integer(required=True)
    status = fields.String(required=True)
    platform = fields.String(required=True)
    branch = fields.String(required=True)
    commit_sha = fields.String(required=True)
    tested_at = fields.DateTime(allow_none=True, format='%Y-%m-%dT%H:%M:%SZ')
    failure_signature = fields.String(allow_none=True)


class RegressionTestSchema(Schema):
    """A regression test definition."""

    regression_test_id = fields.Integer(required=True)
    sample_id = fields.Integer(allow_none=True)
    sample_name = fields.String(allow_none=True)
    command = fields.String(required=True)
    input_type = fields.String(required=True)
    output_type = fields.String(required=True)
    expected_rc = fields.Integer(required=True)
    active = fields.Boolean(required=True)
    categories = fields.List(fields.String(), load_default=[])
    description = fields.String(allow_none=True)

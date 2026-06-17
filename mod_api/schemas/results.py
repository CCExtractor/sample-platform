"""Schemas for expected/actual output, diffs, and baseline approvals."""

from marshmallow import RAISE, Schema, fields, validate


class OutputFileContentSchema(Schema):
    """File content blob returned for expected or actual output."""

    run_id = fields.Integer(allow_none=True)
    sample_id = fields.Integer(required=True)
    regression_id = fields.Integer(required=True)
    output_id = fields.Integer(required=True)
    filename = fields.String(required=True)
    content_type = fields.String(required=True)
    encoding = fields.String(
        required=True, validate=validate.OneOf(['utf-8', 'base64']))
    content = fields.String(required=True)
    sha256 = fields.String(allow_none=True)
    storage_status = fields.String(
        required=True,
        validate=validate.OneOf(['ok', 'degraded', 'missing']),
    )


class DiffHunkLineSchema(Schema):
    """One line inside a diff hunk."""

    kind = fields.String(required=True, validate=validate.OneOf(
        ['context', 'added', 'removed']))
    expected_line = fields.Integer(allow_none=True)
    actual_line = fields.Integer(allow_none=True)
    text = fields.String(required=True)


class DiffHunkSchema(Schema):
    """A contiguous block of changes."""

    expected_start = fields.Integer(required=True)
    actual_start = fields.Integer(required=True)
    lines = fields.List(fields.Nested(DiffHunkLineSchema), required=True)


class DiffSchema(Schema):
    """Structured diff between expected and actual output."""

    run_id = fields.Integer(required=True)
    sample_id = fields.Integer(required=True)
    regression_id = fields.Integer(required=True)
    output_id = fields.Integer(required=True)
    status = fields.String(required=True, validate=validate.OneOf([
        'identical', 'different', 'missing_actual', 'missing_expected',
    ]))
    summary = fields.Dict(required=True)
    hunks = fields.List(fields.Nested(DiffHunkSchema), required=True)


class BaselineApprovalRequestSchema(Schema):
    """POST /runs/{id}/samples/{sid}/baseline-approval body."""

    regression_id = fields.Integer(
        required=True,
        validate=validate.Range(min=1),
    )
    output_id = fields.Integer(
        required=True,
        validate=validate.Range(min=1),
    )

    remove_variants = fields.Boolean(
        load_default=False,
    )

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class BaselineApprovalSchema(Schema):
    """Response after a baseline approval is applied."""

    status = fields.String(
        required=True,
        validate=validate.OneOf(
            ['approved']))
    run_id = fields.Integer(required=True)
    sample_id = fields.Integer(required=True)
    regression_id = fields.Integer(required=True)
    output_id = fields.Integer(required=True)
    requested_by = fields.String(required=True)
    created_at = fields.DateTime(required=True, format='%Y-%m-%dT%H:%M:%SZ')

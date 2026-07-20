"""Schemas for output file content and baseline approvals."""

from marshmallow import RAISE, Schema, fields, validate

from mod_api.schemas.common import DATETIME_FORMAT


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
    # sha256 always covers the complete file, even when content is truncated.
    sha256 = fields.String(allow_none=True)
    truncated = fields.Boolean(load_default=False)
    download_url = fields.String(allow_none=True)
    storage_status = fields.String(
        required=True,
        validate=validate.OneOf(['ok', 'degraded', 'missing']),
    )


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
    created_at = fields.DateTime(required=True, format=DATETIME_FORMAT)

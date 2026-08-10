"""Request schemas for the upload queue endpoints."""

from marshmallow import RAISE, Schema, fields, validate

from mod_upload.models import Platform

# Read off the model so a platform the database accepts is never rejected
# here, the way the sample and regression test schemas do it.
_PLATFORMS = sorted(Platform.values())


class UploadFinalizeSchema(Schema):
    """Validates POST /queued-samples/{id}/finalize bodies."""

    # The version string rather than its id: a client works from what
    # /system/about and the sample payloads already show it.
    version = fields.String(
        required=True, validate=validate.Length(min=1, max=10))
    platform = fields.String(
        required=True, validate=validate.OneOf(_PLATFORMS))
    parameters = fields.String(
        load_default='', validate=validate.Length(max=1024))
    notes = fields.String(
        load_default='', validate=validate.Length(max=1024))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class QueueLinkSchema(Schema):
    """Validates POST /queued-samples/{id}/link bodies."""

    sample_id = fields.Integer(required=True, validate=validate.Range(min=1))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE

"""Schemas for sample endpoints."""

from marshmallow import RAISE, Schema, fields, validate

from mod_api.schemas.common import DATETIME_FORMAT
from mod_upload.models import Platform

# Read off the model so a platform the database accepts can never be
# rejected here, the way the regression test schemas take their type lists.
_PLATFORMS = sorted(Platform.values())

_TAG_NAME_MAX = 64
_TAG_DESCRIPTION_MAX = 1024


class SampleHistoryEntrySchema(Schema):
    """One row in a sample's cross-run history."""

    run_id = fields.Integer(required=True)
    regression_test_id = fields.Integer(required=True)
    status = fields.String(required=True)
    platform = fields.String(required=True)
    branch = fields.String(required=True)
    commit_sha = fields.String(required=True)
    tested_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)
    failure_signature = fields.String(allow_none=True)


class TagCreateSchema(Schema):
    """Validates POST /tags bodies."""

    name = fields.String(
        required=True, validate=validate.Length(min=1, max=_TAG_NAME_MAX))
    description = fields.String(
        load_default='', validate=validate.Length(max=_TAG_DESCRIPTION_MAX))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class SampleUpdateSchema(Schema):
    """
    Validates PATCH /samples/{id} bodies; every field optional.

    Tags are given by name rather than id so a caller can work from the
    names the sample payload already shows, instead of first fetching the
    tag list to translate them.
    """

    tags = fields.List(
        fields.String(validate=validate.Length(min=1, max=_TAG_NAME_MAX)),
        validate=validate.Length(max=50))
    notes = fields.String(validate=validate.Length(max=1024))
    parameters = fields.String(validate=validate.Length(max=1024))
    platform = fields.String(validate=validate.OneOf(_PLATFORMS))
    version = fields.String(validate=validate.Length(min=1, max=10))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE

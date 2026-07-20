"""Schemas for sample endpoints."""

from marshmallow import Schema, fields

from mod_api.schemas.common import DATETIME_FORMAT


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

"""Request/response schemas for the token endpoints."""

from marshmallow import RAISE, Schema, fields, validate

from mod_api.models.api_token import VALID_SCOPES

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class TokenCreateRequestSchema(Schema):
    """Validates POST /auth/tokens bodies."""

    email = fields.Email(required=True)
    password = fields.String(
        required=True,
        validate=validate.Length(min=8, max=128),
    )
    token_name = fields.String(
        required=True,
        validate=[
            validate.Length(min=1, max=50),
            validate.Regexp(
                r'^[a-zA-Z0-9_\-]+$',
                error='token_name must match ^[a-zA-Z0-9_-]+$',
            ),
        ],
    )
    expires_in_days = fields.Integer(
        load_default=7,
        validate=validate.Range(min=1, max=30),
    )
    scopes = fields.List(
        fields.String(validate=validate.OneOf(VALID_SCOPES)),
        load_default=None,
        validate=validate.Length(max=6),
    )

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class AuthTokenSchema(Schema):
    """The one-time response returned when a token is created."""

    token = fields.String(required=True)
    token_type = fields.String(dump_default='bearer')
    token_name = fields.String(required=True)
    scopes = fields.List(fields.String(), required=True)
    expires_at = fields.DateTime(required=True, format=DATETIME_FORMAT)


class ApiTokenItemSchema(Schema):
    """Token metadata for list responses — never includes the plaintext."""

    id = fields.Integer(required=True)
    user_id = fields.Integer(required=True)
    token_name = fields.String(required=True)
    token_prefix = fields.String(required=True)
    scopes = fields.Method('get_scopes')
    created_at = fields.DateTime(required=True, format=DATETIME_FORMAT)
    expires_at = fields.DateTime(required=True, format=DATETIME_FORMAT)
    is_revoked = fields.Boolean(required=True)
    revoked_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)

    def get_scopes(self, obj):
        """Deserialize scopes from the model's JSON column."""
        return obj.scopes

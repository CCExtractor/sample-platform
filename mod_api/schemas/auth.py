"""Request/response schemas for the token and user endpoints."""

from marshmallow import RAISE, Schema, ValidationError, fields, validate

from mod_api.models.api_token import VALID_SCOPES
from mod_api.schemas.common import DATETIME_FORMAT
from mod_auth.models import Role


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
        # Bounded by the scope list itself, so adding a scope cannot silently
        # make "ask for everything I'm allowed" fail validation.
        validate=validate.Length(max=len(VALID_SCOPES)),
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
    scopes = fields.Method('get_scopes')
    created_at = fields.DateTime(required=True, format=DATETIME_FORMAT)
    expires_at = fields.DateTime(required=True, format=DATETIME_FORMAT)
    is_revoked = fields.Boolean(required=True)
    revoked_at = fields.DateTime(allow_none=True, format=DATETIME_FORMAT)

    def get_scopes(self, obj):
        """Deserialize scopes from the model's JSON column."""
        return obj.scopes


class RoleUpdateSchema(Schema):
    """Validates PATCH /users/{id} bodies."""

    # Taken from the model so the accepted values follow the Role enum.
    role = fields.String(
        required=True, validate=validate.OneOf(sorted(Role.values())))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class EmailOnlySchema(Schema):
    """Validates the signup and password reset request bodies."""

    email = fields.Email(required=True)

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


def valid_password(value):
    """
    Check a password against the configured length bounds.

    Written as a validator rather than a pre-built Length, because the
    bounds come from config and reading those while the schema class is
    being defined would import the app mid-blueprint-setup. The classic
    forms read the same two keys, so the rules cannot drift apart.
    """
    from run import config

    low = int(config.get('MIN_PWD_LEN', 10))
    high = int(config.get('MAX_PWD_LEN', 500))
    if not low <= len(value) <= high:
        raise ValidationError(
            f'Password must be between {low} and {high} characters.')


class PasswordResetCompleteSchema(Schema):
    """Validates POST /auth/password-reset/complete bodies."""

    user_id = fields.Integer(required=True, validate=validate.Range(min=1))
    expires = fields.Integer(required=True)
    mac = fields.String(
        required=True, validate=validate.Length(min=1, max=128))
    password = fields.String(required=True, validate=valid_password)

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class AccountUpdateSchema(Schema):
    """
    Validates PATCH /auth/me bodies; every field optional.

    current_password is demanded alongside any change to the credentials
    themselves, so a leaked token cannot quietly become a stolen account.
    """

    name = fields.String(validate=validate.Length(min=1, max=50))
    email = fields.Email()
    new_password = fields.String(validate=valid_password)
    current_password = fields.String(
        validate=validate.Length(min=1, max=500))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE

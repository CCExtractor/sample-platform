"""Request schemas for the platform configuration endpoints."""

from marshmallow import RAISE, Schema, fields, validate


class MaintenanceUpdateSchema(Schema):
    """Validates PATCH /system/maintenance/{platform} bodies."""

    disabled = fields.Boolean(required=True)

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class BlockedUserCreateSchema(Schema):
    """Validates POST /system/blocked-users bodies."""

    # The numeric GitHub account id, not the login: logins can be changed and
    # reused, which would silently unblock somebody.
    user_id = fields.Integer(required=True, validate=validate.Range(min=1))
    comment = fields.String(load_default='', validate=validate.Length(max=1024))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class ForbiddenExtensionCreateSchema(Schema):
    """Validates POST /system/forbidden-extensions bodies."""

    # Stored without the leading dot, matching how upload validation looks it
    # up. Letters and digits only, so a pattern can never be smuggled in.
    extension = fields.String(
        required=True,
        validate=[
            validate.Length(min=1, max=32),
            validate.Regexp(
                r'^[A-Za-z0-9]+$',
                error='extension must be alphanumeric, without a leading dot',
            ),
        ],
    )

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE

"""Request schemas for the regression test and category write endpoints."""

from marshmallow import RAISE, Schema, fields, validate

from mod_regression.models import InputType, OutputType

# Taken from the models rather than restated, so a type the database accepts
# can never be rejected here (or the reverse) after someone edits the enum.
_INPUT_TYPES = sorted(InputType.values())
_OUTPUT_TYPES = sorted(OutputType.values())

# Matches the maxLength the OpenAPI contract already publishes for a
# regression test's command, so a body accepted here cannot produce a
# response that violates the documented schema.
_COMMAND_MAX = 500

# Category column widths, shared with the category name list below.
_NAME_MAX = 64
_DESCRIPTION_MAX = 1024

# Matches the maxLength the contract publishes for a variant hash.
_HASH_MAX = 128


class RegressionTestCreateSchema(Schema):
    """Validates POST /regression-tests bodies."""

    sample_id = fields.Integer(required=True, validate=validate.Range(min=1))
    command = fields.String(
        required=True, validate=validate.Length(min=1, max=_COMMAND_MAX))
    input_type = fields.String(
        load_default='file', validate=validate.OneOf(_INPUT_TYPES))
    output_type = fields.String(
        load_default='file', validate=validate.OneOf(_OUTPUT_TYPES))
    expected_rc = fields.Integer(
        load_default=0, validate=validate.Range(min=0, max=255))
    description = fields.String(
        load_default='', validate=validate.Length(max=_DESCRIPTION_MAX))
    categories = fields.List(
        fields.String(validate=validate.Length(min=1, max=_NAME_MAX)),
        required=True,
        validate=validate.Length(min=1),
    )
    # A new test starts inactive: it should only join the CI suite once a
    # maintainer has seen what it actually produces on a verification run.
    active = fields.Boolean(load_default=False)

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class RegressionTestUpdateSchema(Schema):
    """Validates PATCH /regression-tests/{id} bodies; every field optional."""

    command = fields.String(validate=validate.Length(min=1, max=_COMMAND_MAX))
    input_type = fields.String(validate=validate.OneOf(_INPUT_TYPES))
    output_type = fields.String(validate=validate.OneOf(_OUTPUT_TYPES))
    expected_rc = fields.Integer(validate=validate.Range(min=0, max=255))
    description = fields.String(validate=validate.Length(max=_DESCRIPTION_MAX))
    categories = fields.List(
        fields.String(validate=validate.Length(min=1, max=_NAME_MAX)),
        validate=validate.Length(min=1),
    )
    active = fields.Boolean()

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class CategoryCreateSchema(Schema):
    """Validates POST /categories bodies."""

    name = fields.String(
        required=True, validate=validate.Length(min=1, max=_NAME_MAX))
    description = fields.String(
        load_default='', validate=validate.Length(max=_DESCRIPTION_MAX))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class CategoryUpdateSchema(Schema):
    """Validates PATCH /categories/{id} bodies; every field optional."""

    name = fields.String(validate=validate.Length(min=1, max=_NAME_MAX))
    description = fields.String(validate=validate.Length(max=_DESCRIPTION_MAX))

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE


class VariantCreateSchema(Schema):
    """Validates POST /regression-tests/{id}/outputs/{oid}/variants bodies."""

    # The hash is joined to the baseline's extension to form a filename under
    # TestResults, so it is restricted to characters that cannot climb out of
    # that directory. Content hashes are hex, so this costs nothing real.
    hash = fields.String(
        required=True,
        validate=[
            validate.Length(min=1, max=_HASH_MAX),
            validate.Regexp(
                r'^[A-Za-z0-9]+$',
                error='hash must be alphanumeric',
            ),
        ],
    )

    class Meta:
        """Reject unknown fields."""

        unknown = RAISE

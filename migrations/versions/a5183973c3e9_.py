"""Change SQLAlchemy Boolean bit(1) to bool

Revision ID: a5183973c3e9
Revises: 2e0d2e02a721
Create Date: 2023-08-10 15:51:13.537000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5183973c3e9'
down_revision = '2e0d2e02a721'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('regression_test', 'active', existing_type=sa.Boolean(), type_=sa.Boolean(), nullable=False)


def downgrade():
    op.alter_column('regression_test', 'active', existing_type=sa.Boolean(), type_=sa.dialects.mysql.BIT(1), nullable=False)

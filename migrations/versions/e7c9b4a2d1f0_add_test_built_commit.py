"""Record the SHA that CI actually built alongside the PR head.

Revision ID: e7c9b4a2d1f0
Revises: d4f8e2a1b3c7
Create Date: 2026-09-08 16:50:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e7c9b4a2d1f0'
down_revision = 'd4f8e2a1b3c7'
branch_labels = None
depends_on = None


def upgrade():
    """Apply the migration."""
    op.add_column('test', sa.Column('built_commit', sa.String(length=64), nullable=True))


def downgrade():
    """Revert the migration."""
    op.drop_column('test', 'built_commit')

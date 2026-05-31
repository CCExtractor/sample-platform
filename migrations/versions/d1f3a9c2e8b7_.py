"""Add baseline_status to regression_test for never-worked tracking

Revision ID: d1f3a9c2e8b7
Revises: c8f3a2b1d4e5
Create Date: 2026-03-07 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd1f3a9c2e8b7'
down_revision = 'c8f3a2b1d4e5'
branch_labels = None
depends_on = None

# Enum values mirror BaselineStatus in mod_regression/models.py
baseline_status_enum = sa.Enum('unknown', 'never_worked', 'established', name='baselinestatus')


def upgrade():
    """Add baseline_status column to regression_test table."""
    # Add column with default so existing rows get 'unknown' immediately
    op.add_column(
        'regression_test',
        sa.Column(
            'baseline_status',
            baseline_status_enum,
            nullable=False,
            server_default='unknown'
        )
    )

    # Historical backfill:
    # - if the regression test has ever passed on either tracked platform, it is established
    # - otherwise keep the trusted state as unknown until a main-repo commit run refreshes it
    op.execute(
        """
        UPDATE regression_test
        SET baseline_status = 'established'
        WHERE last_passed_on_linux IS NOT NULL OR last_passed_on_windows IS NOT NULL
        """
    )


def downgrade():
    """Remove baseline_status column from regression_test table."""
    op.drop_column('regression_test', 'baseline_status')

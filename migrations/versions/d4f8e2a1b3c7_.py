"""Add api_token table for scoped API token auth.

Revision ID: d4f8e2a1b3c7
Revises: c8f3a2b1d4e5
Create Date: 2026-06-11 03:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd4f8e2a1b3c7'
down_revision = 'c8f3a2b1d4e5'
branch_labels = None
depends_on = None


def upgrade():
    """Apply the migration."""
    op.add_column('user', sa.Column('github_login', sa.String(length=255), nullable=True))
    op.create_table(
        'api_token',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_name', sa.String(length=50), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('token_prefix', sa.String(length=16), nullable=False),
        sa.Column('scopes_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], onupdate='CASCADE', ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'token_name', name='uq_user_token_name'),
        mysql_engine='InnoDB'
    )
    op.create_index('ix_api_token_token_prefix', 'api_token', ['token_prefix'])


def downgrade():
    """Revert the migration."""
    op.drop_index('ix_api_token_token_prefix', table_name='api_token')
    op.drop_table('api_token')
    op.drop_column('user', 'github_login')

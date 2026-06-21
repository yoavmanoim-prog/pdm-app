"""add token_version to users

Supports "log out on permission change": every JWT carries the token_version it
was minted at, and a token whose version no longer matches the user's current
token_version is rejected. Admin role edits / deactivations bump this column.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_column('users', 'token_version')

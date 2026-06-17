"""add settings JSON to repositories

Per-repo configurable settings (first one: part_number_mask). NULL = code
defaults (legacy behaviour preserved).

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('repositories', sa.Column('settings', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('repositories', 'settings')

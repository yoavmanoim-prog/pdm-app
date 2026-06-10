"""add watch_path to repositories

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('repositories', sa.Column('watch_path', sa.String(1000), nullable=True))


def downgrade():
    op.drop_column('repositories', 'watch_path')

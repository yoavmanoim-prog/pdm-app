"""add drawing-approval fields to commit_files

Records who signed off a drawing version before it was pushed (approve_drawing).
NULL until approved; a new commit on a document yields a fresh, unapproved row.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('commit_files', sa.Column('approved_by', sa.String(length=255), nullable=True))
    op.add_column('commit_files', sa.Column('approved_by_id', sa.Uuid(), nullable=True))
    op.add_column('commit_files', sa.Column('approved_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('commit_files', 'approved_at')
    op.drop_column('commit_files', 'approved_by_id')
    op.drop_column('commit_files', 'approved_by')

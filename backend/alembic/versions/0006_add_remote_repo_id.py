"""add remote_repo_id to repositories

Lets a local repo link to a remote repo with a different id (connect to an
existing remote repo, or push a populated local into an empty remote one).
NULL = same id as the local repo (legacy behaviour).

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('repositories', sa.Column('remote_repo_id', sa.UUID(), nullable=True))


def downgrade():
    op.drop_column('repositories', 'remote_repo_id')

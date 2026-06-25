"""add users table

App-native authentication: a users table holding email, a bcrypt password hash,
a role (admin/member) and an is_active flag. No data is migrated — the table
starts empty and an admin is seeded at startup via BOOTSTRAP_ADMIN_* env vars.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='member'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        # one account per email address
        sa.UniqueConstraint('email', name='uq_users_email'),
    )


def downgrade():
    op.drop_table('users')

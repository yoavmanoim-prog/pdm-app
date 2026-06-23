"""add roles table (admin-managed roles + privileges)

Roles bundle privileges; users link to a role by name (users.role == roles.name,
already populated with 'admin'/'member'). Seeds the two built-in roles so the
existing role strings resolve to a privilege set. No users-table change.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-23
"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

# keep in sync with app/authz.PRIVILEGES
ALL_PRIVILEGES = ["manage_users", "manage_roles", "approve_drawing", "approve_release"]


def upgrade():
    roles = op.create_table(
        'roles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('privileges', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_roles_name'),
    )
    # seed the two undeletable built-ins. admin gets the full catalog so existing
    # admins keep every capability; member gets none (normal app access only).
    now = datetime.utcnow()
    op.bulk_insert(roles, [
        {'id': uuid.uuid4(), 'name': 'admin', 'privileges': ALL_PRIVILEGES,
         'is_builtin': True, 'created_at': now},
        {'id': uuid.uuid4(), 'name': 'member', 'privileges': [],
         'is_builtin': True, 'created_at': now},
    ])


def downgrade():
    op.drop_table('roles')

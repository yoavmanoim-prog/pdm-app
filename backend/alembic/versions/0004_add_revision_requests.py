"""add revision_requests table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'revision_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('repository_id', sa.UUID(), sa.ForeignKey('repositories.id'), nullable=False),
        sa.Column('document_id', sa.UUID(), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('proposed_revision_code', sa.String(10), nullable=False),
        sa.Column('requested_by', sa.String(255), nullable=False),
        sa.Column('change_note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_by', sa.String(255), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    # prevent two pending requests for the same document at the DB level
    op.create_index(
        'uq_revision_requests_one_pending_per_doc',
        'revision_requests',
        ['document_id'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade():
    op.drop_index('uq_revision_requests_one_pending_per_doc', table_name='revision_requests')
    op.drop_table('revision_requests')

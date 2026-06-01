"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "schematics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("part_number", sa.Text, nullable=False),
        sa.Column("vehicle_make", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("s3_key", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("schematics.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted", sa.Boolean, server_default="false"),
    )
    op.create_index("idx_schematics_part", "schematics", ["part_number"])


def downgrade():
    op.drop_index("idx_schematics_part")
    op.drop_table("schematics")

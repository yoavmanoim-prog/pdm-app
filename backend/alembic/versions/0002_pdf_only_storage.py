"""PDF-only storage — remove SVG columns from commit_files

Revision ID: 002
Revises: 001
Create Date: 2026-06-04

The system now stores PDFs directly instead of converting to SVG.
- s3_key_svg is removed: no SVG files are stored any more
- pdf_diff is removed: SVG element-level diff is no longer computed
- s3_key_pdf and content_hash remain: PDF path and dedup hash are still needed

Uses IF EXISTS / IF NOT EXISTS throughout so this migration is safe to run
against databases that may have partial or different schemas from previous
deployment histories.
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Ensure commit_files exists with the correct PDF-only schema.
    # IF NOT EXISTS makes this safe even if the table was never created.
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS commit_files (
            id          UUID         NOT NULL,
            commit_id   UUID         NOT NULL,
            document_id UUID         NOT NULL,
            change_type VARCHAR(20)  NOT NULL,
            s3_key_pdf  VARCHAR(500),
            content_hash VARCHAR(64),
            PRIMARY KEY (id),
            FOREIGN KEY (commit_id)   REFERENCES commits(id),
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """))

    # Drop SVG columns if they exist — safe no-op if they were never there
    conn.execute(sa.text(
        "ALTER TABLE commit_files DROP COLUMN IF EXISTS s3_key_svg"
    ))
    conn.execute(sa.text(
        "ALTER TABLE commit_files DROP COLUMN IF EXISTS pdf_diff"
    ))


def downgrade():
    op.add_column('commit_files', sa.Column('pdf_diff', sa.JSON(), nullable=True))
    op.add_column('commit_files', sa.Column('s3_key_svg', sa.String(500), nullable=True))

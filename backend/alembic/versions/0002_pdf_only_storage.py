"""PDF-only storage — remove SVG columns from commit_files

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-04

The system now stores PDFs directly instead of converting to SVG.
- s3_key_svg is removed: no SVG files are stored any more
- pdf_diff is removed: SVG element-level diff is no longer computed
- s3_key_pdf and content_hash remain: PDF path and dedup hash are still needed
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the SVG storage key — PDFs are now stored directly, no SVG conversion
    op.drop_column('commit_files', 's3_key_svg')

    # Drop the SVG element diff — comparisons are now visual (old PDF vs new PDF)
    op.drop_column('commit_files', 'pdf_diff')


def downgrade():
    # Restore columns if rolling back — they will be empty (data is gone)
    op.add_column('commit_files', sa.Column('pdf_diff', sa.JSON(), nullable=True))
    op.add_column('commit_files', sa.Column('s3_key_svg', sa.String(500), nullable=True))

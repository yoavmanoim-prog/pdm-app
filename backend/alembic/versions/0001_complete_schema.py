"""Complete schema — creates all tables from scratch

Revision ID: 0001
Revises:
Create Date: 2026-06-04

Why this migration exists:
  Previous migrations used ALTER TABLE which assumed tables already existed.
  This single migration builds everything from an empty database so both
  local-vault and remote-vault databases can be initialised cleanly.

Table creation order (foreign key dependencies drive the order):
  1. repositories   — no dependencies
  2. documents      — needs repositories
  3. commits        — needs repositories (branch FK added later, see note)
  4. branches       — needs repositories + commits
  5. FK patch       — add commits.branch_id → branches (circular resolved)
  6. commit_files   — needs commits + documents
  7. bom_entries    — needs documents
  8. revisions      — needs documents + commits
  9. audit_events   — needs repositories
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. repositories ─────────────────────────────────────────────────────
    # Top-level container — like a GitHub repo but for engineering drawings.
    # Every other table (except audit_events) hangs off a repository.
    op.create_table(
        'repositories',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('remote_url', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # ── 2. documents ─────────────────────────────────────────────────────────
    # A single engineering drawing: one part or one assembly.
    # Stores metadata only — actual SVG/PDF files live in S3.
    op.create_table(
        'documents',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('repository_id', sa.Uuid(), nullable=False),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('doc_type', sa.String(20), nullable=False),  # "detail" or "assembly"
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── 3. commits (without branch FK — circular dependency, resolved below) ─
    # A snapshot of a change, like a git commit.
    # branch_id column is created here but its FK constraint is added in step 5.
    op.create_table(
        'commits',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('repository_id', sa.Uuid(), nullable=False),
        sa.Column('branch_id', sa.Uuid(), nullable=True),    # FK to branches added later
        sa.Column('parent_id', sa.Uuid(), nullable=True),    # previous commit in chain
        sa.Column('author', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('short_hash', sa.String(16), nullable=False),  # 8-char identifier
        sa.Column('is_local', sa.Boolean(), nullable=False),     # False once pushed
        sa.Column('diff_report', sa.JSON(), nullable=True),
        sa.Column('protocol_violations', sa.JSON(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['commits.id']),  # self-reference is fine
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('short_hash'),
    )

    # ── 4. branches ──────────────────────────────────────────────────────────
    # An isolated line of work — like a git branch.
    # base_commit_id records where the branch diverged from main.
    op.create_table(
        'branches',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('repository_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('base_commit_id', sa.Uuid(), nullable=True),  # null = brand new repo
        sa.Column('status', sa.String(20), nullable=False),     # open / merged / closed
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
        sa.ForeignKeyConstraint(['base_commit_id'], ['commits.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── 5. resolve the circular FK: commits.branch_id → branches ────────────
    # Now that branches exists we can add the FK we skipped in step 3.
    # This is the standard Alembic pattern for circular foreign keys.
    op.create_foreign_key(
        'commits_branch_id_fkey',
        'commits', 'branches',
        ['branch_id'], ['id'],
    )

    # ── 6. commit_files ───────────────────────────────────────────────────────
    # One row per file changed in a commit.
    # Stores S3 keys for both SVG (working format) and PDF (published format).
    op.create_table(
        'commit_files',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('commit_id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('change_type', sa.String(20), nullable=False),  # added/modified/deleted
        sa.Column('s3_key_svg', sa.String(500), nullable=True),
        sa.Column('s3_key_pdf', sa.String(500), nullable=True),
        sa.Column('content_hash', sa.String(64), nullable=True),  # SHA-256 for dedup
        sa.Column('pdf_diff', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['commit_id'], ['commits.id']),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── 7. bom_entries ────────────────────────────────────────────────────────
    # Bill of Materials: links an assembly drawing to its component parts.
    # An assembly can have many BOM entries; a part can appear in many assemblies.
    op.create_table(
        'bom_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('assembly_id', sa.Uuid(), nullable=False),    # the parent assembly
        sa.Column('component_id', sa.Uuid(), nullable=False),   # the child part
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('position', sa.String(50), nullable=True),    # balloon number on drawing
        sa.Column('part_revision', sa.String(10), nullable=True),
        sa.Column('material', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('product_line', sa.String(255), nullable=True),
        sa.Column('item_type', sa.String(20), nullable=False),  # "part" or "assembly"
        sa.Column('find_number', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['assembly_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['component_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── 8. revisions ─────────────────────────────────────────────────────────
    # A formal published release: Rev A, Rev B, Rev C...
    # Points to the exact commit that was released.
    op.create_table(
        'revisions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('commit_id', sa.Uuid(), nullable=False),
        sa.Column('revision_code', sa.String(10), nullable=False),  # "A", "B", "C"...
        sa.Column('status', sa.String(20), nullable=False),   # draft/released/obsolete
        sa.Column('published_by', sa.String(255), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('change_note', sa.Text(), nullable=True),   # required from Rev B onwards
        sa.Column('passed_protocol', sa.Boolean(), nullable=False),
        sa.Column('violations', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['commit_id'], ['commits.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── 9. audit_events ───────────────────────────────────────────────────────
    # Immutable log of every action ever taken. Never deleted, never modified.
    # is_breach = True means a protocol rule was broken during this action.
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('repository_id', sa.Uuid(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('actor', sa.String(255), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(100), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('is_breach', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    # Drop in reverse order — children before parents
    op.drop_table('audit_events')
    op.drop_table('revisions')
    op.drop_table('bom_entries')
    op.drop_table('commit_files')
    op.drop_constraint('commits_branch_id_fkey', 'commits', type_='foreignkey')
    op.drop_table('branches')
    op.drop_table('commits')
    op.drop_table('documents')
    op.drop_table('repositories')

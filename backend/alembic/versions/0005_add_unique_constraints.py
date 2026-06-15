"""add unique constraints for documents, bom_entries, and branches

Closes the data-integrity gap where uniqueness was only enforced in app code,
allowing concurrent requests to race in duplicate rows.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    # Defensive de-dup: the app already prevents these duplicates, but any rows
    # that slipped in through a race would make the constraint creation fail.
    # Keep the lowest id() per group and drop the rest.

    # documents: unique (repository_id, part_number)
    op.execute(
        """
        DELETE FROM documents d
        USING documents older
        WHERE d.repository_id = older.repository_id
          AND d.part_number = older.part_number
          AND d.id > older.id
        """
    )
    op.create_unique_constraint(
        'uq_documents_repo_part_number',
        'documents',
        ['repository_id', 'part_number'],
    )

    # bom_entries: unique (assembly_id, component_id)
    op.execute(
        """
        DELETE FROM bom_entries b
        USING bom_entries older
        WHERE b.assembly_id = older.assembly_id
          AND b.component_id = older.component_id
          AND b.id > older.id
        """
    )
    op.create_unique_constraint(
        'uq_bom_assembly_component',
        'bom_entries',
        ['assembly_id', 'component_id'],
    )

    # branches: partial unique index — only one OPEN branch per name per repo.
    # Names remain reusable after a branch is merged/closed.
    # Don't delete duplicate branches (commits reference branch_id); instead
    # keep the most recently created open branch per name and close the rest.
    op.execute(
        """
        UPDATE branches b
        SET status = 'closed'
        FROM branches newer
        WHERE b.repository_id = newer.repository_id
          AND b.name = newer.name
          AND b.status = 'open'
          AND newer.status = 'open'
          AND (newer.created_at, newer.id) > (b.created_at, b.id)
        """
    )
    op.create_index(
        'uq_branches_one_open_per_name',
        'branches',
        ['repository_id', 'name'],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade():
    op.drop_index('uq_branches_one_open_per_name', table_name='branches')
    op.drop_constraint('uq_bom_assembly_component', 'bom_entries', type_='unique')
    op.drop_constraint('uq_documents_repo_part_number', 'documents', type_='unique')

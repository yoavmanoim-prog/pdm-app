import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.config import settings
from app.models.bom import BOMEntry
from app.models.commit import Commit, CommitFile
from app.models.repository import Repository
from app.models.document import Document

router = APIRouter(prefix="/vault", tags=["vault"])


def _require_remote():
    """Guard — these endpoints only work on the remote vault."""
    if settings.VAULT_MODE != "remote":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only available on the remote vault",
        )


# ── Incoming push ─────────────────────────────────────────────────────────────

class CommitFilePayload(BaseModel):
    document_id: uuid.UUID
    s3_key_pdf: str | None
    content_hash: str | None
    change_type: str


class CommitPayload(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    branch_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    author: str
    message: str
    short_hash: str
    diff_report: dict | None
    protocol_violations: list | None
    timestamp: datetime
    files: list[CommitFilePayload]


class DocumentPayload(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    part_number: str
    title: str
    doc_type: str


class BOMEntryPayload(BaseModel):
    id: uuid.UUID
    assembly_id: uuid.UUID
    component_id: uuid.UUID
    quantity: int = 1
    position: str | None = None
    find_number: int | None = None
    part_revision: str | None = None
    material: str | None = None
    description: str | None = None
    product_line: str | None = None
    item_type: str = "part"


class RevisionPayload(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    commit_id: uuid.UUID
    revision_code: str
    status: str
    published_by: str | None = None
    published_at: datetime | None = None
    change_note: str | None = None
    passed_protocol: bool = False
    violations: list | None = None


class RepositoryPayload(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None


class DiffReportPatch(BaseModel):
    short_hash: str
    diff_report: dict | None = None


class PushPayload(BaseModel):
    commits: list[CommitPayload]
    repository: RepositoryPayload | None = None
    documents: list[DocumentPayload] = []
    bom_entries: list[BOMEntryPayload] = []


@router.post("/incoming/commits")
def receive_commits(payload: PushPayload, db: Session = Depends(get_db)):
    _require_remote()

    with db.no_autoflush:
        # upsert repository
        if payload.repository:
            repo = db.get(Repository, payload.repository.id)
            if not repo:
                db.add(Repository(
                    id=payload.repository.id,
                    name=payload.repository.name,
                    description=payload.repository.description,
                ))
            else:
                repo.name = payload.repository.name
                repo.description = payload.repository.description

        # upsert documents — update existing so edits propagate
        for doc_data in payload.documents:
            doc = db.get(Document, doc_data.id)
            if not doc:
                db.add(Document(
                    id=doc_data.id,
                    repository_id=doc_data.repository_id,
                    part_number=doc_data.part_number,
                    title=doc_data.title,
                    doc_type=doc_data.doc_type,
                ))
            else:
                doc.part_number = doc_data.part_number
                doc.title = doc_data.title
                doc.doc_type = doc_data.doc_type

    db.flush()

    stored = 0
    skipped = 0

    for c in payload.commits:
        if db.query(Commit).filter(Commit.short_hash == c.short_hash).first():
            skipped += 1
            continue

        # ensure the repository record exists on the remote side
        repo = db.get(Repository, c.repository_id)
        if not repo:
            db.add(Repository(id=c.repository_id, name=str(c.repository_id)))
            db.flush()

        commit = Commit(
            id=c.id,
            repository_id=c.repository_id,
            branch_id=None,  # branches are local-only; remote stores commits flat
            parent_id=c.parent_id,
            author=c.author,
            message=c.message,
            short_hash=c.short_hash,
            is_local=False,  # on the remote vault, nothing is "local"
            diff_report=c.diff_report,
            protocol_violations=c.protocol_violations,
            timestamp=c.timestamp,
        )
        db.add(commit)
        db.flush()

        for f in c.files:
            db.add(CommitFile(
                commit_id=commit.id,
                document_id=f.document_id,
                s3_key_pdf=f.s3_key_pdf,
                content_hash=f.content_hash,
                change_type=f.change_type,
            ))

        stored += 1

    # upsert BOM entries
    for b in payload.bom_entries:
        entry = db.get(BOMEntry, b.id)
        if not entry:
            db.add(BOMEntry(
                id=b.id,
                assembly_id=b.assembly_id,
                component_id=b.component_id,
                quantity=b.quantity,
                position=b.position,
                find_number=b.find_number,
                part_revision=b.part_revision,
                material=b.material,
                description=b.description,
                product_line=b.product_line,
                item_type=b.item_type,
            ))
        else:
            entry.quantity = b.quantity
            entry.position = b.position
            entry.part_revision = b.part_revision
            entry.material = b.material
            entry.description = b.description
            entry.item_type = b.item_type

    # revisions are NOT accepted via push — the remote vault is the sole authority.
    # Revisions are created here by POST /vault/revisions/publish and flow to local
    # via pull (GET /vault/snapshot). Accepting them on push would let a local vault
    # with a stale 'draft' state overwrite a 'released' revision on the remote.

    # apply diff_report patches — bulk fetch then patch in memory (avoids N+1)
    if payload.diff_report_patches:
        patch_hashes = [p.short_hash for p in payload.diff_report_patches]
        commits_by_hash = {
            c.short_hash: c
            for c in db.query(Commit).filter(Commit.short_hash.in_(patch_hashes)).all()
        }
        for patch in payload.diff_report_patches:
            commit = commits_by_hash.get(patch.short_hash)
            if commit:
                commit.diff_report = patch.diff_report

    db.commit()
    return {"stored": stored, "skipped": skipped}


# ── Snapshot for pull — returns everything the local vault needs ──────────────

@router.get("/snapshot/{repo_id}")
def snapshot(
    repo_id: uuid.UUID,
    since_hash: str | None = None,
    db: Session = Depends(get_db),
):
    """Return commits (optionally since a hash), all documents, BOM entries, and revisions."""
    _require_remote()

    # commits — optionally filtered to only those after since_hash
    all_commits = (
        db.query(Commit)
        .filter(Commit.repository_id == repo_id)
        .order_by(Commit.timestamp)
        .all()
    )
    if since_hash:
        pivot = next((i for i, c in enumerate(all_commits) if c.short_hash == since_hash), None)
        if pivot is not None:
            all_commits = all_commits[pivot + 1:]

    commits_out = [
        {
            "id": str(c.id),
            "repository_id": str(c.repository_id),
            "branch_id": str(c.branch_id) if c.branch_id else None,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "author": c.author,
            "message": c.message,
            "short_hash": c.short_hash,
            "diff_report": c.diff_report,
            "protocol_violations": c.protocol_violations,
            "timestamp": c.timestamp.isoformat(),
            "files": [
                {
                    "document_id": str(f.document_id),
                    "s3_key_pdf": f.s3_key_pdf,
                    "content_hash": f.content_hash,
                    "change_type": f.change_type,
                }
                for f in c.files
            ],
        }
        for c in all_commits
    ]

    # all documents in the repo (full set — not filtered to since_hash)
    docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    docs_out = [
        {
            "id": str(d.id),
            "repository_id": str(d.repository_id),
            "part_number": d.part_number,
            "title": d.title,
            "doc_type": d.doc_type,
        }
        for d in docs
    ]

    # all BOM entries where both assembly and component belong to this repo
    repo_doc_ids = {d.id for d in docs}
    bom_entries = db.query(BOMEntry).filter(
        BOMEntry.assembly_id.in_(repo_doc_ids)
    ).all()
    bom_out = [
        {
            "id": str(b.id),
            "assembly_id": str(b.assembly_id),
            "component_id": str(b.component_id),
            "quantity": b.quantity,
            "position": b.position,
            "find_number": b.find_number,
            "part_revision": b.part_revision,
            "material": b.material,
            "description": b.description,
            "product_line": b.product_line,
            "item_type": b.item_type,
        }
        for b in bom_entries
    ]

    # all revisions for docs in this repo
    revisions = db.query(Revision).filter(
        Revision.document_id.in_(repo_doc_ids)
    ).all()
    revisions_out = [
        {
            "id": str(r.id),
            "document_id": str(r.document_id),
            "commit_id": str(r.commit_id),
            "revision_code": r.revision_code,
            "status": r.status,
            "published_by": r.published_by,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "change_note": r.change_note,
            "passed_protocol": r.passed_protocol,
            "violations": r.violations,
        }
        for r in revisions
    ]

    return {
        "commits": commits_out,
        "documents": docs_out,
        "bom_entries": bom_out,
        "revisions": revisions_out,
    }


# ── Serve commits for pull (kept for backwards compatibility) ─────────────────

@router.get("/commits")
def serve_commits(
    repo_id: uuid.UUID,
    since_hash: str | None = None,
    db: Session = Depends(get_db),
):
    _require_remote()

    query = db.query(Commit).filter(
        Commit.repository_id == repo_id
    ).order_by(Commit.timestamp)

    commits = query.all()

    # if since_hash given, return only commits AFTER that commit
    if since_hash:
        pivot = next((i for i, c in enumerate(commits) if c.short_hash == since_hash), None)
        if pivot is not None:
            commits = commits[pivot + 1:]

    result = []
    for c in commits:
        result.append({
            "id": str(c.id),
            "repository_id": str(c.repository_id),
            "branch_id": str(c.branch_id) if c.branch_id else None,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "author": c.author,
            "message": c.message,
            "short_hash": c.short_hash,
            "diff_report": c.diff_report,
            "protocol_violations": c.protocol_violations,
            "timestamp": c.timestamp.isoformat(),
            "files": [
                {
                    "document_id": str(f.document_id),
                    "s3_key_pdf": f.s3_key_pdf,
                    "content_hash": f.content_hash,
                    "change_type": f.change_type,
                }
                for f in c.files
            ],
        })

    return result

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.config import settings
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


class RepositoryPayload(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None


class PushPayload(BaseModel):
    commits: list[CommitPayload]
    repository: RepositoryPayload | None = None
    documents: list[DocumentPayload] = []


@router.post("/incoming/commits")
def receive_commits(payload: PushPayload, db: Session = Depends(get_db)):
    _require_remote()

    with db.no_autoflush:
        # upsert repository
        if payload.repository:
            if not db.get(Repository, payload.repository.id):
                db.add(Repository(
                    id=payload.repository.id,
                    name=payload.repository.name,
                    description=payload.repository.description,
                ))

        # upsert documents — must exist before commit_files FK is checked
        for doc_data in payload.documents:
            if not db.get(Document, doc_data.id):
                db.add(Document(
                    id=doc_data.id,
                    repository_id=doc_data.repository_id,
                    part_number=doc_data.part_number,
                    title=doc_data.title,
                    doc_type=doc_data.doc_type,
                ))

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

    db.commit()
    return {"stored": stored, "skipped": skipped}


# ── Serve commits for pull ────────────────────────────────────────────────────

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

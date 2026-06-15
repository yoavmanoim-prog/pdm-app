import logging
import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.repository import Repository
from app.models.document import Document
from app.models.commit import Commit, CommitFile
from app.models.audit import AuditEvent
from app.schemas.commits import CommitResponse, CommitFileResponse, CommitAmend
from app.config import settings
from app.protocol.engine import run_commit_checks
from app import storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/repos", tags=["commits"])


# ── Step 12 — commit endpoint ──────────────────────────────────────────────────

@router.post("/{repo_id}/commit", response_model=CommitResponse, status_code=201)
async def create_commit(
    repo_id: uuid.UUID,
    doc_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    author: str = Form(...),
    message: str = Form(...),
    branch_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db),
):
    if not settings.S3_BUCKET:
        raise HTTPException(status_code=503, detail="S3 not configured — set S3_BUCKET env var")

    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # block commits to released documents
    check = run_commit_checks(doc, db)
    if not check["passed"]:
        raise HTTPException(status_code=422, detail={
            "message": "Commit blocked by protocol",
            "violations": check["violations"],
        })

    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    # include branch + doc in the short hash so the same file on different branches is unique
    short_hash = hashlib.sha256(
        f"{content_hash}-{branch_id or 'main'}-{doc_id}".encode()
    ).hexdigest()[:8]

    # find the most recent commit file for this document on the same branch (or main)
    prev_file = (
        db.query(CommitFile)
        .join(Commit)
        .filter(
            Commit.repository_id == repo_id,
            CommitFile.document_id == doc_id,
            Commit.branch_id == branch_id,
        )
        .order_by(desc(Commit.timestamp))
        .first()
    )

    if prev_file and prev_file.content_hash == content_hash:
        raise HTTPException(status_code=400, detail="No changes detected — file is identical to the current version")

    # change_type is based on whether the document has ever been committed anywhere
    any_prior = (
        db.query(CommitFile)
        .join(Commit)
        .filter(Commit.repository_id == repo_id, CommitFile.document_id == doc_id)
        .first()
    )
    change_type = "added" if any_prior is None else "modified"

    s3_key_pdf = storage.upload_file(
        pdf_bytes,
        f"{repo_id}/{doc_id}/{short_hash}.pdf",
        "application/pdf",
    )

    # the parent commit is the most recent commit in this repo
    parent = (
        db.query(Commit)
        .filter(Commit.repository_id == repo_id)
        .order_by(desc(Commit.timestamp))
        .first()
    )

    commit = Commit(
        repository_id=repo_id,
        branch_id=branch_id,
        parent_id=parent.id if parent else None,
        author=author,
        message=message,
        short_hash=short_hash,
        is_local=True,
        diff_report={"document": doc.part_number, "change_type": change_type},
        protocol_violations=[],
    )
    db.add(commit)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Commit hash collision — please retry")

    commit_file = CommitFile(
        commit_id=commit.id,
        document_id=doc_id,
        s3_key_pdf=s3_key_pdf,
        content_hash=content_hash,
        change_type=change_type,
    )
    db.add(commit_file)

    db.add(AuditEvent(
        repository_id=repo_id,
        actor=author,
        action="commit",
        entity_type="document",
        entity_id=str(doc_id),
        details={
            "part_number": doc.part_number,
            "commit_hash": short_hash,
            "change_type": change_type,
            "message": message,
        },
        is_breach=False,
    ))

    db.commit()
    db.refresh(commit)

    # auto-link BOM sons and retroactively link this doc to existing assemblies
    try:
        from app.services.pdf_bom import auto_link_sons, retro_link_fathers
        auto_link_sons(pdf_bytes, repo_id, doc_id, db)
        retro_link_fathers(repo_id, doc_id, db)
    except Exception as e:
        logger.warning("pdf_bom extraction failed for commit %s: %s", short_hash, e)

    return commit


# ── Step 13 — commit log ───────────────────────────────────────────────────────

@router.get("/{repo_id}/log", response_model=list[CommitResponse])
def get_log(
    repo_id: uuid.UUID,
    limit: int = 50,
    branch_id: str | None = None,   # uuid string or "main" for default branch
    db: Session = Depends(get_db),
):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    q = db.query(Commit).filter(Commit.repository_id == repo_id)

    if branch_id == "main":
        q = q.filter(Commit.branch_id.is_(None))
    elif branch_id:
        q = q.filter(Commit.branch_id == uuid.UUID(branch_id))

    commits = q.order_by(desc(Commit.timestamp)).limit(limit).all()

    # build a doc_id → part_number lookup so the frontend can show drawing IDs
    doc_ids = {f.document_id for c in commits for f in c.files}
    part_numbers = {
        d.id: d.part_number
        for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()
    } if doc_ids else {}

    result = []
    for c in commits:
        files = [
            CommitFileResponse(
                id=f.id,
                document_id=f.document_id,
                part_number=part_numbers.get(f.document_id),
                s3_key_pdf=f.s3_key_pdf,
                content_hash=f.content_hash,
                change_type=f.change_type,
            )
            for f in c.files
        ]
        result.append(CommitResponse(
            id=c.id,
            repository_id=c.repository_id,
            branch_id=c.branch_id,
            parent_id=c.parent_id,
            author=c.author,
            message=c.message,
            short_hash=c.short_hash,
            is_local=c.is_local,
            timestamp=c.timestamp,
            files=files,
        ))
    return result


# ── Step 14 — commit diff ─────────────────────────────────────────────────────

@router.get("/{repo_id}/commits/{short_hash}", response_model=CommitResponse)
def get_commit(repo_id: uuid.UUID, short_hash: str, db: Session = Depends(get_db)):
    commit = (
        db.query(Commit)
        .filter(Commit.repository_id == repo_id, Commit.short_hash == short_hash)
        .first()
    )
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")
    return commit


@router.patch("/{repo_id}/commits/{short_hash}", response_model=CommitResponse)
def amend_commit(
    repo_id: uuid.UUID,
    short_hash: str,
    body: CommitAmend,
    db: Session = Depends(get_db),
):
    commit = (
        db.query(Commit)
        .filter(Commit.repository_id == repo_id, Commit.short_hash == short_hash)
        .first()
    )
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")
    if not commit.is_local:
        raise HTTPException(status_code=409, detail="Cannot amend a pushed commit — it is already on the remote vault")
    old_author = commit.author
    old_message = commit.message
    if body.author is not None:
        commit.author = body.author
    if body.message is not None:
        commit.message = body.message
    db.add(AuditEvent(
        repository_id=repo_id,
        actor=commit.author,
        action="amend_commit",
        entity_type="commit",
        entity_id=str(commit.id),
        details={
            "commit_hash": commit.short_hash,
            "old_author": old_author,
            "new_author": commit.author,
            "old_message": old_message,
            "new_message": commit.message,
        },
        is_breach=False,
    ))
    db.commit()
    db.refresh(commit)

    # soft recommit — re-run BOM extraction against the existing PDF in S3
    from app.services.pdf_bom import auto_link_sons, retro_link_fathers
    for cf in commit.files:
        if not cf.s3_key_pdf:
            continue
        try:
            pdf_bytes = storage.download_file(cf.s3_key_pdf)
            auto_link_sons(pdf_bytes, repo_id, cf.document_id, db)
            retro_link_fathers(repo_id, cf.document_id, db)
        except Exception as e:
            logger.warning("pdf_bom re-extraction failed on amend %s: %s", short_hash, e)

    return commit


@router.get("/{repo_id}/diff/{short_hash}")
def get_diff(repo_id: uuid.UUID, short_hash: str, db: Session = Depends(get_db)):
    """
    Returns the changed files in a commit and presigned URLs for:
    - current_pdf: the new version uploaded in this commit
    - previous_pdf: the version from the parent commit (None for first commit)
    UI uses these two URLs to show a side-by-side comparison.
    """
    commit = (
        db.query(Commit)
        .filter(Commit.repository_id == repo_id, Commit.short_hash == short_hash)
        .first()
    )
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")

    result = []
    for cf in commit.files:
        # get the previous version of this document by looking at the parent commit
        prev_pdf_url = None
        if commit.parent_id:
            prev_cf = (
                db.query(CommitFile)
                .join(Commit)
                .filter(
                    Commit.repository_id == repo_id,
                    CommitFile.document_id == cf.document_id,
                    Commit.timestamp < commit.timestamp,
                )
                .order_by(desc(Commit.timestamp))
                .first()
            )
            if prev_cf:
                prev_pdf_url = storage.presigned_url_if_exists(prev_cf.s3_key_pdf)

        current_pdf_url = storage.presigned_url_if_exists(cf.s3_key_pdf)

        doc = db.get(Document, cf.document_id)
        result.append({
            "document_id": str(cf.document_id),
            "part_number": doc.part_number if doc else None,
            "change_type": cf.change_type,
            "content_hash": cf.content_hash,
            "current_pdf_url": current_pdf_url,
            "previous_pdf_url": prev_pdf_url,
        })

    return {"commit_hash": short_hash, "author": commit.author, "message": commit.message, "files": result}

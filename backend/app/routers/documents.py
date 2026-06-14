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
from app.models.bom import BOMEntry
from app.models.audit import AuditEvent
from app.schemas.documents import DocumentCreate, DocumentResponse
from app.config import settings
from app import storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/repos", tags=["documents"])


@router.post("/{repo_id}/documents/", response_model=DocumentResponse, status_code=201)
def create_document(repo_id: uuid.UUID, body: DocumentCreate, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # part numbers must be unique within a repository
    existing = db.query(Document).filter(
        Document.repository_id == repo_id,
        Document.part_number == body.part_number,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Part number '{body.part_number}' already exists in this repository",
        )

    if body.doc_type not in ("detail", "assembly", "part"):
        raise HTTPException(status_code=400, detail="doc_type must be 'detail', 'assembly', or 'part'")

    doc = Document(
        repository_id=repo_id,
        part_number=body.part_number,
        title=body.title,
        doc_type=body.doc_type,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{repo_id}/documents/", response_model=list[DocumentResponse])
def list_documents(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return db.query(Document).filter(Document.repository_id == repo_id).all()


@router.patch("/{repo_id}/documents/{doc_id}", response_model=DocumentResponse)
def edit_document(repo_id: uuid.UUID, doc_id: uuid.UUID, body: DocumentCreate, db: Session = Depends(get_db)):
    if settings.VAULT_MODE != "local":
        raise HTTPException(status_code=403, detail="Document metadata can only be edited on the local vault")
    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if body.doc_type not in ("detail", "assembly", "part"):
        raise HTTPException(status_code=400, detail="doc_type must be 'detail', 'assembly', or 'part'")
    if body.part_number != doc.part_number:
        clash = db.query(Document).filter(
            Document.repository_id == repo_id,
            Document.part_number == body.part_number,
            Document.id != doc_id,
        ).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Part number '{body.part_number}' already exists")
    doc.part_number = body.part_number
    doc.title = body.title
    doc.doc_type = body.doc_type
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{repo_id}/documents/{doc_id}", response_model=DocumentResponse)
def get_document(repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{repo_id}/documents/{doc_id}/commits")
def get_document_commits(repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Returns every commit that touched this document, newest first.
    Each entry includes a presigned URL for the PDF at that version and for
    the version immediately before it — so the viewer can show old vs new.
    """
    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # fetch all CommitFile rows for this document, ordered newest-first via the parent Commit
    commit_files = (
        db.query(CommitFile)
        .join(Commit)
        .filter(
            Commit.repository_id == repo_id,
            CommitFile.document_id == doc_id,
        )
        .order_by(desc(Commit.timestamp))
        .all()
    )

    versions = []
    for i, cf in enumerate(commit_files):
        commit = cf.commit
        current_url = storage.generate_presigned_url(cf.s3_key_pdf) if cf.s3_key_pdf else None

        # the "previous" version is the next item in the list (we are sorted newest-first)
        prev_url = None
        if i + 1 < len(commit_files):
            prev_cf = commit_files[i + 1]
            if prev_cf.s3_key_pdf:
                prev_url = storage.generate_presigned_url(prev_cf.s3_key_pdf)

        versions.append({
            "commit_hash": commit.short_hash,
            "author": commit.author,
            "message": commit.message,
            "timestamp": commit.timestamp.isoformat(),
            "change_type": cf.change_type,       # "added" or "modified"
            "current_pdf_url": current_url,      # presigned URL for this version
            "previous_pdf_url": prev_url,        # presigned URL for the version before this one
        })

    return {
        "document_id": str(doc_id),
        "part_number": doc.part_number,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "versions": versions,
    }


@router.get("/{repo_id}/documents/{doc_id}/latest-commit")
def get_latest_commit(repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns just the author/message/hash of the most recent commit — no presigned URLs generated."""
    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")
    latest = (
        db.query(CommitFile)
        .join(Commit)
        .filter(Commit.repository_id == repo_id, CommitFile.document_id == doc_id)
        .order_by(desc(Commit.timestamp))
        .first()
    )
    if not latest:
        return None
    c = latest.commit
    return {
        "commit_hash": c.short_hash,
        "author": c.author,
        "message": c.message,
        "is_local": c.is_local,
    }


@router.get("/{repo_id}/documents/{doc_id}/bom")
def get_document_bom(repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns BOM entries for a document (pre-populates the edit form's sons section)."""
    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")
    entries = db.query(BOMEntry).filter(BOMEntry.assembly_id == doc_id).all()
    result = []
    for e in entries:
        comp = db.get(Document, e.component_id)
        result.append({
            "id": str(e.id),
            "component_id": str(e.component_id),
            "part_number": comp.part_number if comp else None,
            "title": comp.title if comp else None,
            "quantity": e.quantity,
            "position": e.position or "",
        })
    return result


@router.post("/{repo_id}/documents/{doc_id}/upload")
async def upload_document(
    repo_id: uuid.UUID,
    doc_id: uuid.UUID,
    file: UploadFile = File(...),
    author: str = Form(...),
    message: str = Form("Initial upload"),
    branch_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")

    filename = file.filename or ""
    if not settings.S3_BUCKET:
        raise HTTPException(status_code=503, detail="S3 not configured — set S3_BUCKET env var")

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()

    # SHA-256 of the PDF — used to reject commits with no actual changes
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # no-op guard: compare against the LATEST committed version of this document on
    # this branch. (commit_id is a UUID, so ordering by it is random — join Commit
    # and order by timestamp, as create_commit does.)
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

    # include branch + doc so the same PDF in different documents/branches still gets a
    # unique short_hash (short_hash has a global unique constraint).
    short_hash = hashlib.sha256(
        f"{content_hash}-{branch_id or 'main'}-{doc_id}".encode()
    ).hexdigest()[:8]

    # store PDF in S3 under a stable path: {repo}/{doc}/{hash}.pdf
    s3_key_pdf = storage.upload_file(
        pdf_bytes,
        f"{repo_id}/{doc_id}/{short_hash}.pdf",
        "application/pdf",
    )

    # find the most recent commit to set as parent (null = first commit)
    parent = (
        db.query(Commit)
        .filter(Commit.repository_id == repo_id)
        .order_by(Commit.timestamp.desc())
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
        diff_report={"note": "initial upload", "document": doc.part_number},
        protocol_violations=[],
    )
    db.add(commit)
    try:
        db.flush()  # get commit.id before creating CommitFile
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Commit hash collision — please retry")

    commit_file = CommitFile(
        commit_id=commit.id,
        document_id=doc_id,
        s3_key_pdf=s3_key_pdf,
        content_hash=content_hash,
        change_type="added",
    )
    db.add(commit_file)

    db.add(AuditEvent(
        repository_id=repo_id,
        actor=author,
        action="upload",
        entity_type="document",
        entity_id=str(doc_id),
        details={"part_number": doc.part_number, "commit_hash": short_hash, "filename": filename},
        is_breach=False,
    ))

    db.commit()

    # auto-link BOM sons and retroactively link this doc to existing assemblies
    try:
        from app.services.pdf_bom import auto_link_sons, retro_link_fathers
        auto_link_sons(pdf_bytes, repo_id, doc_id, db)
        retro_link_fathers(repo_id, doc_id, db)
    except Exception as e:
        logger.warning("pdf_bom extraction failed for doc %s: %s", doc_id, e)

    return {
        "commit_hash": short_hash,
        "document_id": str(doc_id),
        "s3_key_pdf": s3_key_pdf,
        "content_hash": content_hash,
    }

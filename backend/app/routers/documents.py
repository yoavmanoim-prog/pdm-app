import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.repository import Repository
from app.models.document import Document
from app.models.commit import Commit, CommitFile
from app.models.audit import AuditEvent
from app.schemas.documents import DocumentCreate, DocumentResponse
from app.config import settings
from app import storage

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

    if body.doc_type not in ("detail", "assembly"):
        raise HTTPException(status_code=400, detail="doc_type must be 'detail' or 'assembly'")

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


@router.get("/{repo_id}/documents/{doc_id}", response_model=DocumentResponse)
def get_document(repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/{repo_id}/documents/{doc_id}/upload")
async def upload_document(
    repo_id: uuid.UUID,
    doc_id: uuid.UUID,
    file: UploadFile = File(...),
    author: str = Form(...),
    message: str = Form("Initial upload"),
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

    # check if this exact file was already uploaded (no-op commit guard)
    prev = (
        db.query(CommitFile)
        .filter(CommitFile.document_id == doc_id)
        .order_by(CommitFile.commit_id)
        .first()
    )
    if prev and prev.content_hash == content_hash:
        raise HTTPException(status_code=400, detail="No changes detected — file is identical to the current version")

    short_hash = content_hash[:8]

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
        branch_id=None,
        parent_id=parent.id if parent else None,
        author=author,
        message=message,
        short_hash=short_hash,
        is_local=True,
        diff_report={"note": "initial upload", "document": doc.part_number},
        protocol_violations=[],
    )
    db.add(commit)
    db.flush()  # get commit.id before creating CommitFile

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

    return {
        "commit_hash": short_hash,
        "document_id": str(doc_id),
        "s3_key_pdf": s3_key_pdf,
        "content_hash": content_hash,
    }

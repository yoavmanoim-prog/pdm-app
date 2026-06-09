"""
Working-directory watcher.

The engineer mounts a local folder into the container (e.g. ~/Desktop/drawings → /watch).
This router scans that folder, compares each PDF's SHA-256 hash against the last committed
version in the repo, and returns one of three statuses per file:

  committed  — hash matches the latest commit for that document
  modified   — file exists in PDM but the on-disk hash differs (file changed since last commit)
  untracked  — no document in this repo matches the filename's part number
"""
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.commit import Commit, CommitFile
from app.models.document import Document

router = APIRouter(prefix="/repos", tags=["watch"])


def _hash_file(path: Path) -> str:
    """SHA-256 of a file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _latest_hash(doc_id: uuid.UUID, repo_id: uuid.UUID, db: Session) -> str | None:
    """Return the SHA-256 of the most recently committed PDF for a document."""
    cf = (
        db.query(CommitFile)
        .join(Commit)
        .filter(Commit.repository_id == repo_id, CommitFile.document_id == doc_id)
        .order_by(desc(Commit.timestamp))
        .first()
    )
    return cf.content_hash if cf else None


@router.get("/{repo_id}/watch/status")
def watch_status(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Scan WATCH_DIR and return the status of every PDF found.
    The filename (without extension) is treated as the document part number.
    """
    if not settings.WATCH_DIR:
        raise HTTPException(status_code=503, detail="WATCH_DIR is not configured")

    watch_path = Path(settings.WATCH_DIR)
    if not watch_path.exists():
        raise HTTPException(status_code=503, detail=f"WATCH_DIR '{settings.WATCH_DIR}' does not exist")

    # build a lookup of part_number → Document for this repo
    docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    doc_by_part = {d.part_number.upper(): d for d in docs}

    results = []
    for pdf in sorted(watch_path.glob("*.pdf")):
        # derive a candidate part number from the filename (strip extension)
        candidate = pdf.stem.upper()
        file_hash = _hash_file(pdf)

        doc = doc_by_part.get(candidate)

        if doc is None:
            # no document with this part number exists in the repo
            results.append({
                "filename": pdf.name,
                "part_number": pdf.stem,
                "status": "untracked",
                "doc_id": None,
                "hash": file_hash[:8],
            })
        else:
            committed_hash = _latest_hash(doc.id, repo_id, db)
            if committed_hash and file_hash == committed_hash:
                status = "committed"
            else:
                # file exists in PDM but the on-disk copy has changed
                status = "modified" if committed_hash else "untracked"

            results.append({
                "filename": pdf.name,
                "part_number": doc.part_number,
                "title": doc.title,
                "doc_type": doc.doc_type,
                "status": status,
                "doc_id": str(doc.id),
                "hash": file_hash[:8],
                "committed_hash": committed_hash[:8] if committed_hash else None,
            })

    return {"watch_dir": str(watch_path), "files": results}


@router.post("/{repo_id}/watch/commit")
async def watch_commit(
    repo_id: uuid.UUID,
    filename: str = Form(...),      # filename in WATCH_DIR to commit
    author: str = Form(...),
    message: str = Form(...),
    doc_id: uuid.UUID | None = Form(None),        # existing document to update
    part_number: str | None = Form(None),         # for creating a new document
    title: str | None = Form(None),
    doc_type: str = Form("detail"),
    db: Session = Depends(get_db),
):
    """
    Commit a file from WATCH_DIR without a browser upload.
    The backend reads the file directly from the mounted folder.
    If doc_id is given → commit a new version of that document.
    If part_number/title are given → create the document first, then upload.
    """
    if not settings.WATCH_DIR:
        raise HTTPException(status_code=503, detail="WATCH_DIR is not configured")

    path = Path(settings.WATCH_DIR) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in WATCH_DIR")

    pdf_bytes = path.read_bytes()

    # re-use the existing upload / commit logic via the storage module
    if doc_id:
        # update an existing document — same path as /documents/{id}/upload
        from app.routers.documents import upload_document

        class _FakeUpload:
            filename = filename
            async def read(self): return pdf_bytes

        fake = _FakeUpload()
        return await upload_document(
            repo_id=repo_id, doc_id=doc_id,
            file=fake, author=author, message=message, db=db,
        )
    else:
        # create a new document then upload
        if not part_number or not title:
            raise HTTPException(status_code=400, detail="part_number and title required for new documents")

        from app.routers.documents import create_document, upload_document
        from app.schemas.documents import DocumentCreate

        doc = create_document(
            repo_id=repo_id,
            body=DocumentCreate(part_number=part_number, title=title, doc_type=doc_type),
            db=db,
        )

        class _FakeUpload:
            async def read(self): return pdf_bytes

        fake = _FakeUpload()
        fake.filename = filename
        return await upload_document(
            repo_id=repo_id, doc_id=doc.id,
            file=fake, author=author, message=message, db=db,
        )

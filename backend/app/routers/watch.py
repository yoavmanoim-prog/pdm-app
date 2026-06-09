"""
Working-directory watcher.

The user's home directory is mounted at WATCH_BASE (/homedir).
The user types any subfolder path in the UI — no docker-compose changes needed.
The backend scans that path, compares each PDF's SHA-256 against committed versions,
and returns one of three statuses:

  committed  — hash matches the latest commit
  modified   — filename matches a document but the file changed on disk
  untracked  — file not yet in this repo
"""
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.commit import Commit, CommitFile
from app.models.document import Document

router = APIRouter(prefix="/repos", tags=["watch"])


def _resolve(user_path: str) -> Path:
    """Resolve a user-supplied relative path under WATCH_BASE, blocking traversal."""
    base = Path(settings.WATCH_BASE)
    # strip leading slash so Path joining works correctly
    rel = user_path.lstrip("/")
    resolved = (base / rel).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise HTTPException(status_code=400, detail="Path outside home directory")
    return resolved


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _latest_hash(doc_id: uuid.UUID, repo_id: uuid.UUID, db: Session) -> str | None:
    cf = (
        db.query(CommitFile)
        .join(Commit)
        .filter(Commit.repository_id == repo_id, CommitFile.document_id == doc_id)
        .order_by(desc(Commit.timestamp))
        .first()
    )
    return cf.content_hash if cf else None


@router.get("/{repo_id}/watch/status")
def watch_status(
    repo_id: uuid.UUID,
    path: str = Query(..., description="Subfolder path relative to home directory"),
    db: Session = Depends(get_db),
):
    """
    Scan a folder chosen by the user and return the status of every PDF.
    `path` is relative to the home directory (e.g. Desktop/drawings).
    """
    watch_path = _resolve(path)

    if not watch_path.exists():
        raise HTTPException(status_code=404, detail=f"Folder '{path}' not found")
    if not watch_path.is_dir():
        raise HTTPException(status_code=400, detail=f"'{path}' is not a folder")

    docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    doc_by_part = {d.part_number.upper(): d for d in docs}

    results = []
    for pdf in sorted(watch_path.glob("*.pdf")):
        candidate = pdf.stem.upper()
        file_hash = _hash_file(pdf)
        doc = doc_by_part.get(candidate)

        if doc is None:
            results.append({
                "filename": pdf.name,
                "part_number": pdf.stem,
                "status": "untracked",
                "doc_id": None,
                "hash": file_hash[:8],
            })
        else:
            committed_hash = _latest_hash(doc.id, repo_id, db)
            status = "committed" if (committed_hash and file_hash == committed_hash) \
                else ("modified" if committed_hash else "untracked")
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

    return {"watch_dir": str(watch_path), "path": path, "files": results}


@router.post("/{repo_id}/watch/commit")
async def watch_commit(
    repo_id: uuid.UUID,
    path: str = Form(...),            # subfolder path relative to home directory
    filename: str = Form(...),
    author: str = Form(...),
    message: str = Form(...),
    doc_id: uuid.UUID | None = Form(None),
    part_number: str | None = Form(None),
    title: str | None = Form(None),
    doc_type: str = Form("detail"),
    db: Session = Depends(get_db),
):
    """
    Commit a file from a user-chosen folder without a browser upload.
    `path` is relative to the home directory.
    """
    watch_path = _resolve(path)
    file_path = watch_path / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in '{path}'")

    pdf_bytes = file_path.read_bytes()

    if doc_id:
        from app.routers.documents import upload_document

        class _FakeUpload:
            async def read(self): return pdf_bytes

        fake = _FakeUpload()
        fake.filename = filename
        return await upload_document(
            repo_id=repo_id, doc_id=doc_id,
            file=fake, author=author, message=message, db=db,
        )
    else:
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

"""
Working-directory watcher — git-init style.

Each repo stores a watch_path set at creation time (relative to WATCH_BASE).
The UI scans that path automatically — no path input after init.
"""
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.commit import Commit, CommitFile
from app.models.document import Document
from app.models.repository import Repository

router = APIRouter(tags=["watch"])


def _resolve(watch_path: str) -> Path:
    """Resolve repo watch_path under WATCH_BASE, blocking directory traversal."""
    base = Path(settings.WATCH_BASE)
    resolved = (base / watch_path.lstrip("/")).resolve()
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


@router.get("/watch/browse")
def browse(path: str = Query("", description="Relative path to browse (empty = root)")):
    """List subdirectories at a given path under WATCH_BASE — used by the folder picker."""
    base = Path(settings.WATCH_BASE)
    target = (base / path.lstrip("/")).resolve() if path else base.resolve()

    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=400, detail="Path outside watch root")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Path not found")

    entries = []
    for entry in sorted(target.iterdir()):
        if entry.name.startswith('.'):
            continue  # skip hidden dirs before stat-ing (avoids PermissionError on macOS .Trash etc.)
        try:
            if entry.is_dir():
                rel = str(entry.relative_to(base))
                entries.append({"name": entry.name, "path": rel})
        except PermissionError:
            continue

    return {
        "current": path or "",
        "parent": str(Path(path).parent) if path and Path(path).parent != Path(path) else None,
        "dirs": entries,
    }


def _get_watch_path(repo_id: uuid.UUID, db: Session) -> Path:
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if not repo.watch_path:
        raise HTTPException(status_code=409, detail="No watch directory set for this repository")
    return _resolve(repo.watch_path)


@router.get("/repos/{repo_id}/watch/status")
def watch_status(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Scan the repo's watch directory and return the status of every PDF."""
    watch_path = _get_watch_path(repo_id, db)

    if not watch_path.exists():
        raise HTTPException(status_code=503, detail=f"Watch directory no longer exists: {watch_path}")

    docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    doc_by_part = {}
    for d in docs:
        doc_by_part[d.part_number.upper()] = d
        # also index by the short base part number (before " -" title separator)
        short = d.part_number.split(' -')[0].strip().upper()
        if short not in doc_by_part:
            doc_by_part[short] = d

    results = []
    for pdf in sorted(watch_path.glob("*.pdf")):
        file_hash = _hash_file(pdf)
        # look up by full stem first, then by short base part number
        stem = pdf.stem
        short_stem = stem.split(' -')[0].strip().upper()
        doc = doc_by_part.get(stem.upper()) or doc_by_part.get(short_stem)

        if doc is None:
            # pre-fill part_number and title by splitting the filename on " -"
            parts = stem.split(' -', 1)
            results.append({
                "filename": pdf.name,
                "part_number": parts[0].strip(),
                "title": parts[1].strip() if len(parts) > 1 else '',
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

    return {"watch_dir": str(watch_path), "files": results}


@router.get("/repos/{repo_id}/watch/preview/{filename:path}")
def watch_preview(repo_id: uuid.UUID, filename: str, db: Session = Depends(get_db)):
    """Stream a PDF from the watch directory so the browser can display it inline."""
    watch_path = _get_watch_path(repo_id, db)
    file_path = watch_path / filename
    if not file_path.exists() or not file_path.suffix.lower() == '.pdf':
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/pdf", filename=filename)


@router.post("/repos/{repo_id}/watch/commit")
async def watch_commit(
    repo_id: uuid.UUID,
    filename: str = Form(...),
    author: str = Form(...),
    message: str = Form(...),
    branch_id: uuid.UUID | None = Form(None),   # None = main branch
    doc_id: uuid.UUID | None = Form(None),
    part_number: str | None = Form(None),
    title: str | None = Form(None),
    doc_type: str = Form("detail"),
    db: Session = Depends(get_db),
):
    """Commit a file from the repo's watch directory — no browser upload needed."""
    watch_path = _get_watch_path(repo_id, db)
    file_path = watch_path / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in watch directory")

    pdf_bytes = file_path.read_bytes()

    if doc_id:
        from app.routers.documents import upload_document

        class _FakeUpload:
            async def read(self): return pdf_bytes

        fake = _FakeUpload()
        fake.filename = filename
        return await upload_document(
            repo_id=repo_id, doc_id=doc_id,
            file=fake, author=author, message=message, branch_id=branch_id, db=db,
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
            file=fake, author=author, message=message, branch_id=branch_id, db=db,
        )

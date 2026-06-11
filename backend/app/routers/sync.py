import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.config import settings
from app.models.bom import BOMEntry
from app.models.commit import Commit, CommitFile
from app.models.document import Document
from app.models.repository import Repository
from app.models.revision import Revision
from app.vault_client import VaultClient

router = APIRouter(prefix="/sync", tags=["sync"])


def _require_local():
    """Push/pull only makes sense on the local vault."""
    if settings.VAULT_MODE != "local":
        raise HTTPException(
            status_code=403,
            detail="Sync endpoints are only available on the local vault",
        )


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status/{repo_id}")
def sync_status(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    _require_local()

    client = VaultClient()
    if not client.ping():
        return {"status": "remote_unreachable", "ahead": 0, "behind": 0}

    # local unpushed commits = is_local=True
    local_unpushed = db.query(Commit).filter(
        Commit.repository_id == repo_id,
        Commit.is_local.is_(True),
    ).count()

    # remote commits not present locally
    local_hashes = {
        c.short_hash for c in db.query(Commit.short_hash)
        .filter(Commit.repository_id == repo_id).all()
    }
    try:
        remote_data = client.pull_snapshot(str(repo_id))
        behind = sum(1 for c in remote_data["commits"] if c["short_hash"] not in local_hashes)
    except Exception:
        behind = 0

    status = "synced"
    if local_unpushed > 0 and behind > 0:
        status = "diverged"
    elif local_unpushed > 0:
        status = "ahead"
    elif behind > 0:
        status = "behind"

    return {"status": status, "ahead": local_unpushed, "behind": behind}


# ── Push ──────────────────────────────────────────────────────────────────────

@router.post("/push/{repo_id}")
def push(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    _require_local()

    unpushed = db.query(Commit).filter(
        Commit.repository_id == repo_id,
        Commit.is_local.is_(True),
    ).order_by(Commit.timestamp).all()

    if not unpushed:
        return {"pushed": 0, "message": "Nothing to push"}

    # collect all document IDs referenced in these commits
    doc_ids = {f.document_id for c in unpushed for f in c.files}
    docs = {d.id: d for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()}

    repo = db.get(Repository, repo_id)

    # BOM entries where assembly or component is among the pushed docs
    bom_entries = db.query(BOMEntry).filter(
        BOMEntry.assembly_id.in_(doc_ids)
    ).all()

    # revisions for the pushed docs
    revisions = db.query(Revision).filter(
        Revision.document_id.in_(doc_ids)
    ).all()

    payload = []
    for c in unpushed:
        payload.append({
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

    client = VaultClient()
    try:
        result = client.push_commits(
            payload,
            repository={"id": str(repo.id), "name": repo.name, "description": repo.description},
            documents=[
                {"id": str(d.id), "repository_id": str(d.repository_id),
                 "part_number": d.part_number, "title": d.title, "doc_type": d.doc_type}
                for d in docs.values()
            ],
            bom_entries=[
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
            ],
            revisions=[
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
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Remote vault unreachable: {e}")

    # mark all pushed commits as no longer local-only
    for c in unpushed:
        c.is_local = False
    db.commit()

    return {"pushed": result.get("stored", 0), "skipped": result.get("skipped", 0)}


# ── Pull ──────────────────────────────────────────────────────────────────────

@router.post("/pull/{repo_id}")
def pull(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    _require_local()

    # find the latest local commit to use as the starting point for new commits
    latest_local = db.query(Commit).filter(
        Commit.repository_id == repo_id,
    ).order_by(desc(Commit.timestamp)).first()

    since_hash = latest_local.short_hash if latest_local else None

    client = VaultClient()
    try:
        remote = client.pull_snapshot(str(repo_id), since_hash=since_hash)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Remote vault unreachable: {e}")

    # upsert documents so the local vault has all metadata even for docs it hasn't committed
    for doc_data in remote.get("documents", []):
        doc = db.get(Document, uuid.UUID(doc_data["id"]))
        if not doc:
            db.add(Document(
                id=uuid.UUID(doc_data["id"]),
                repository_id=uuid.UUID(doc_data["repository_id"]),
                part_number=doc_data["part_number"],
                title=doc_data["title"],
                doc_type=doc_data["doc_type"],
            ))
        else:
            doc.part_number = doc_data["part_number"]
            doc.title = doc_data["title"]
            doc.doc_type = doc_data["doc_type"]
    db.flush()

    # new commits only
    local_hashes = {
        c.short_hash for c in db.query(Commit.short_hash)
        .filter(Commit.repository_id == repo_id).all()
    }

    pulled = 0
    for c in remote.get("commits", []):
        if c["short_hash"] in local_hashes:
            continue

        commit = Commit(
            id=uuid.UUID(c["id"]),
            repository_id=uuid.UUID(c["repository_id"]),
            branch_id=uuid.UUID(c["branch_id"]) if c["branch_id"] else None,
            parent_id=uuid.UUID(c["parent_id"]) if c["parent_id"] else None,
            author=c["author"],
            message=c["message"],
            short_hash=c["short_hash"],
            is_local=False,
            diff_report=c.get("diff_report"),
            protocol_violations=c.get("protocol_violations"),
            timestamp=c["timestamp"],
        )
        db.add(commit)
        db.flush()

        for f in c.get("files", []):
            db.add(CommitFile(
                commit_id=commit.id,
                document_id=uuid.UUID(f["document_id"]),
                s3_key_pdf=f.get("s3_key_pdf"),
                content_hash=f.get("content_hash"),
                change_type=f["change_type"],
            ))

        pulled += 1

    # upsert BOM entries
    for b in remote.get("bom_entries", []):
        entry = db.get(BOMEntry, uuid.UUID(b["id"]))
        if not entry:
            db.add(BOMEntry(
                id=uuid.UUID(b["id"]),
                assembly_id=uuid.UUID(b["assembly_id"]),
                component_id=uuid.UUID(b["component_id"]),
                quantity=b["quantity"],
                position=b.get("position"),
                find_number=b.get("find_number"),
                part_revision=b.get("part_revision"),
                material=b.get("material"),
                description=b.get("description"),
                product_line=b.get("product_line"),
                item_type=b["item_type"],
            ))
        else:
            entry.quantity = b["quantity"]
            entry.position = b.get("position")
            entry.part_revision = b.get("part_revision")
            entry.material = b.get("material")
            entry.description = b.get("description")
            entry.item_type = b["item_type"]

    # upsert revisions
    for r in remote.get("revisions", []):
        rev = db.get(Revision, uuid.UUID(r["id"]))
        if not rev:
            db.add(Revision(
                id=uuid.UUID(r["id"]),
                document_id=uuid.UUID(r["document_id"]),
                commit_id=uuid.UUID(r["commit_id"]),
                revision_code=r["revision_code"],
                status=r["status"],
                published_by=r.get("published_by"),
                published_at=r.get("published_at"),
                change_note=r.get("change_note"),
                passed_protocol=r.get("passed_protocol", False),
                violations=r.get("violations"),
            ))
        else:
            rev.status = r["status"]
            rev.published_by = r.get("published_by")
            rev.published_at = r.get("published_at")
            rev.change_note = r.get("change_note")
            rev.passed_protocol = r.get("passed_protocol", False)
            rev.violations = r.get("violations")

    db.commit()

    if not pulled and not remote.get("bom_entries") and not remote.get("revisions"):
        return {"pulled": 0, "message": "Already up to date"}

    return {"pulled": pulled}

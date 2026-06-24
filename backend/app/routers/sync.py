import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.authz import APPROVE_DRAWING, has_privilege
from app.database import get_db
from app.config import settings
from app import storage
from app.models.bom import BOMEntry
from app.models.commit import Commit, CommitFile
from app.models.document import Document
from app.models.repository import Repository
from app.models.revision import Revision
from app.models.user import User
from app.routers.approvals import latest_unpushed_file, stamp_approval
from app.security import get_current_user
from app.vault_client import VaultClient, RemoteRepoNotFoundError

router = APIRouter(prefix="/sync", tags=["sync"])


def _require_local():
    """Push/pull only makes sense on the local vault."""
    if settings.VAULT_MODE != "local":
        raise HTTPException(
            status_code=403,
            detail="Sync endpoints are only available on the local vault",
        )


def _parse_dt(value):
    """Snapshot serializes datetimes to ISO strings; turn them back into datetime
    objects before persisting. Postgres will implicitly cast an ISO string but
    SQLite will not, so parse explicitly to stay portable across DB backends."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _remote_target(repo) -> uuid.UUID:
    """The repo id to use when talking to the remote vault: the linked
    remote_repo_id if set, otherwise this repo's own id (legacy: same id on both
    sides). Lets a local repo sync with a remote repo that has a different id."""
    return repo.remote_repo_id or repo.id


# ── Remote repo discovery (for the link picker) ────────────────────────────────

@router.get("/remote-repos")
def list_remote_repos(remote_url: str, db: Session = Depends(get_db)):
    """List repos on a remote vault so the user can choose which one to link to
    (or decide to create a new one). Used by the link dialog before saving."""
    _require_local()
    client = VaultClient(remote_url=remote_url)
    if client.health() != "ok":
        raise HTTPException(status_code=502, detail="Remote vault unreachable or misconfigured")
    try:
        repos = client.list_repos()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not list remote repos: {e}")
    return [
        {"id": str(r["id"]), "name": r.get("name"), "document_count": r.get("document_count", 0)}
        for r in repos
    ]


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status/{repo_id}")
def sync_status(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    _require_local()

    repo = db.get(Repository, repo_id)
    client = VaultClient(remote_url=repo.remote_url if repo else None)
    health = client.health()
    if health != "ok":
        # "misconfigured" = a server answered but it isn't a vault (usually the
        # remote URL is missing /api and hit the frontend); "unreachable" = the
        # connection failed outright
        status = "remote_misconfigured" if health == "misconfigured" else "remote_unreachable"
        return {"status": status, "ahead": 0, "behind": 0}

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
        remote_data = client.pull_snapshot(str(_remote_target(repo)))
        behind = sum(1 for c in remote_data["commits"] if c["short_hash"] not in local_hashes)
    except RemoteRepoNotFoundError:
        # Remote doesn't have this repo yet — everything local is ahead. Keep the
        # link so the next push re-creates it (don't auto-unlink behind the user).
        total = len(local_hashes)
        return {"status": "ahead" if total else "synced", "ahead": total, "behind": 0}
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
def push(
    repo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _require_local()

    repo = db.get(Repository, repo_id)
    client = VaultClient(remote_url=repo.remote_url if repo else None)
    # the repo id on the remote (may differ from ours if linked to a chosen repo)
    target = _remote_target(repo)

    # Has this repo ever been pushed? A non-local commit means yes. This tells a
    # genuine remote deletion apart from a never-synced repo's first push: a 404
    # for a previously-synced repo means the remote repo was deleted; a 404 for a
    # never-synced repo is just its first push (the remote will create it).
    previously_synced = db.query(Commit).filter(
        Commit.repository_id == repo_id,
        Commit.is_local.is_(False),
    ).first() is not None

    # Ask the remote what it already has, then send exactly what it's missing,
    # ordered by timestamp so a parent commit always lands before its children.
    # Relying on the local is_local flag instead desyncs whenever the remote
    # loses history (deleted & recreated, restored from backup, ...): push would
    # send a commit whose parent the remote lacks and hit a foreign-key error.
    try:
        snapshot = client.pull_snapshot(str(target))
        remote_hashes = {c["short_hash"] for c in snapshot["commits"]}
    except RemoteRepoNotFoundError:
        if previously_synced:
            # the remote repo was deleted out from under us — clear the link and
            # report it rather than silently re-creating a deliberately-removed
            # remote. Re-linking (which resets is_local) re-enables a fresh push.
            repo.remote_url = None
            db.commit()
            raise HTTPException(status_code=404, detail="Remote repository was deleted — link cleared")
        remote_hashes = set()  # brand-new repo — push_commits will create it
    except Exception as e:
        # Can't determine remote state — refuse rather than push a partial set
        # that might violate a parent foreign key on the remote.
        raise HTTPException(status_code=502, detail=f"Remote vault unreachable: {e}")

    all_local = db.query(Commit).filter(
        Commit.repository_id == repo_id,
    ).order_by(Commit.timestamp).all()
    unpushed = [c for c in all_local if c.short_hash not in remote_hashes]

    if not unpushed:
        return {"pushed": 0, "message": "Nothing to push"}

    # --- drawing-approval gate ---
    # Every drawing in this push must be approved (approve_drawing sign-off). If
    # the pusher holds the privilege, auto-approve in their name; otherwise the
    # push is blocked until a privileged user has signed off each drawing.
    pusher_can_approve = has_privilege(current, APPROVE_DRAWING)
    unpushed_doc_ids = {f.document_id for c in unpushed for f in c.files}
    unapproved = []
    for doc_id in unpushed_doc_ids:
        head = latest_unpushed_file(db, repo_id, doc_id)
        if head is None or head.approved_by_id is not None:
            continue
        if pusher_can_approve:
            stamp_approval(head, current)  # privileged push = auto-approve as self
        else:
            unapproved.append(doc_id)
    if unapproved:
        names = [
            (db.get(Document, d).part_number if db.get(Document, d) else str(d))
            for d in unapproved
        ]
        raise HTTPException(
            status_code=422,
            detail=f"These drawings need approval before they can be pushed: {', '.join(names)}",
        )
    db.flush()  # persist any auto-approvals before we serialize the payload

    # send ALL documents and BOM entries for the whole repo — not just the docs
    # in the current push batch — so the remote always has the full picture.
    # A BOM entry created by retro_link_fathers references an already-pushed
    # assembly, which wouldn't appear in the batch and would be silently dropped.
    all_docs = {d.id: d for d in db.query(Document).filter(Document.repository_id == repo_id).all()}
    all_doc_ids = set(all_docs.keys())

    bom_entries = db.query(BOMEntry).filter(
        BOMEntry.assembly_id.in_(all_doc_ids)
    ).all()

    payload = []
    for c in unpushed:
        payload.append({
            "id": str(c.id),
            # remap to the remote's repo id so commits land under the linked repo
            "repository_id": str(target),
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
                    "approved_by": f.approved_by,
                    "approved_by_id": str(f.approved_by_id) if f.approved_by_id else None,
                    "approved_at": f.approved_at.isoformat() if f.approved_at else None,
                }
                for f in c.files
            ],
        })

    # diff_report patches — send current diff_report for ALL repo commits so the remote
    # gets missing_components updates even on already-pushed commits (retro_link_fathers
    # updates diff_report locally after a commit is no longer local-only)
    all_commits = db.query(Commit).filter(Commit.repository_id == repo_id).all()
    diff_report_patches = [
        {"short_hash": c.short_hash, "diff_report": c.diff_report}
        for c in all_commits
        if c.diff_report is not None
    ]

    try:
        result = client.push_commits(
            payload,
            # repository + documents are remapped to the remote's repo id (target)
            repository={"id": str(target), "name": repo.name, "description": repo.description},
            documents=[
                {"id": str(d.id), "repository_id": str(target),
                 "part_number": d.part_number, "title": d.title, "doc_type": d.doc_type}
                for d in all_docs.values()
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
            diff_report_patches=diff_report_patches,
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

    repo = db.get(Repository, repo_id)
    client = VaultClient(remote_url=repo.remote_url if repo else None)
    target = _remote_target(repo)
    try:
        remote = client.pull_snapshot(str(target), since_hash=since_hash)
    except RemoteRepoNotFoundError:
        # Nothing to pull — the remote doesn't have this repo yet. Keep the link
        # so the user can push to create it (don't auto-unlink behind them).
        raise HTTPException(status_code=404, detail="Remote has no such repository yet — push first to create it")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Remote vault unreachable: {e}")

    # upsert documents so the local vault has all metadata even for docs it hasn't committed
    for doc_data in remote.get("documents", []):
        doc = db.get(Document, uuid.UUID(doc_data["id"]))
        if not doc:
            db.add(Document(
                id=uuid.UUID(doc_data["id"]),
                # store under THIS local repo, not the remote's repo id
                repository_id=repo_id,
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
            # store under THIS local repo, not the remote's repo id
            repository_id=repo_id,
            # pulled commits are flat main-line history — branches are local-only
            # and the remote's branch rows don't exist here, so never carry a
            # branch_id (mirrors how the remote stores pushed commits flat).
            branch_id=None,
            parent_id=uuid.UUID(c["parent_id"]) if c["parent_id"] else None,
            author=c["author"],
            message=c["message"],
            short_hash=c["short_hash"],
            is_local=False,
            diff_report=c.get("diff_report"),
            protocol_violations=c.get("protocol_violations"),
            timestamp=_parse_dt(c["timestamp"]),
        )
        db.add(commit)
        db.flush()

        for f in c.get("files", []):
            # copy the PDF from the remote vault's prefix into this local vault's
            # own prefix so each vault owns its copy (deletes stay isolated)
            if f.get("s3_key_pdf"):
                storage.copy_from_peer(f["s3_key_pdf"])
            db.add(CommitFile(
                commit_id=commit.id,
                document_id=uuid.UUID(f["document_id"]),
                s3_key_pdf=f.get("s3_key_pdf"),
                content_hash=f.get("content_hash"),
                change_type=f["change_type"],
                approved_by=f.get("approved_by"),
                approved_by_id=uuid.UUID(f["approved_by_id"]) if f.get("approved_by_id") else None,
                approved_at=_parse_dt(f.get("approved_at")),
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
                published_at=_parse_dt(r.get("published_at")),
                change_note=r.get("change_note"),
                passed_protocol=r.get("passed_protocol", False),
                violations=r.get("violations"),
            ))
        else:
            rev.status = r["status"]
            rev.published_by = r.get("published_by")
            rev.published_at = _parse_dt(r.get("published_at"))
            rev.change_note = r.get("change_note")
            rev.passed_protocol = r.get("passed_protocol", False)
            rev.violations = r.get("violations")

    db.commit()

    if not pulled and not remote.get("bom_entries") and not remote.get("revisions"):
        return {"pulled": 0, "message": "Already up to date"}

    return {"pulled": pulled}

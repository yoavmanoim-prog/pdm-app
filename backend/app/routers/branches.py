import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models.repository import Repository
from app.models.branch import Branch
from app.models.commit import Commit, CommitFile
from app.models.audit import AuditEvent
from app.schemas.branches import BranchCreate, BranchResponse

router = APIRouter(prefix="/repos", tags=["branches"])


# ── Step 16 — branch CRUD ─────────────────────────────────────────────────────

@router.post("/{repo_id}/branches/", response_model=BranchResponse, status_code=201)
def create_branch(repo_id: uuid.UUID, body: BranchCreate, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # duplicate branch name check
    existing = db.query(Branch).filter(
        Branch.repository_id == repo_id,
        Branch.name == body.name,
        Branch.status == "open",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Branch '{body.name}' already exists")

    # base commit = latest commit on main at the moment the branch is created
    base_commit = (
        db.query(Commit)
        .filter(Commit.repository_id == repo_id, Commit.branch_id.is_(None))
        .order_by(desc(Commit.timestamp))
        .first()
    )

    branch = Branch(
        repository_id=repo_id,
        name=body.name,
        base_commit_id=base_commit.id if base_commit else None,
        status="open",
        created_by=body.created_by,
    )
    db.add(branch)

    db.add(AuditEvent(
        repository_id=repo_id,
        actor=body.created_by,
        action="branch_create",
        entity_type="branch",
        entity_id=None,
        details={"branch": body.name},
        is_breach=False,
    ))

    db.commit()
    db.refresh(branch)
    return branch


@router.get("/{repo_id}/branches/", response_model=list[BranchResponse])
def list_branches(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return db.query(Branch).filter(Branch.repository_id == repo_id).all()


@router.get("/{repo_id}/branches/{branch_id}", response_model=BranchResponse)
def get_branch(repo_id: uuid.UUID, branch_id: uuid.UUID, db: Session = Depends(get_db)):
    branch = db.get(Branch, branch_id)
    if not branch or branch.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


# ── Steps 17-19 — merge request ───────────────────────────────────────────────

def _branch_changes(branch_id: uuid.UUID, base_commit_id: uuid.UUID | None, db: Session) -> dict:
    """
    Returns the latest CommitFile per document for commits on this branch
    that happened after the base commit. These are the changes to be merged.
    """
    query = db.query(CommitFile).join(Commit).filter(Commit.branch_id == branch_id)
    if base_commit_id:
        base = db.get(Commit, base_commit_id)
        if base:
            query = query.filter(Commit.timestamp > base.timestamp)

    # keep only the latest file per document
    latest: dict[uuid.UUID, CommitFile] = {}
    for cf in query.order_by(Commit.timestamp).all():
        latest[cf.document_id] = cf
    return latest


def _main_changes_since(repo_id: uuid.UUID, base_commit_id: uuid.UUID | None, db: Session) -> set:
    """
    Returns the set of document IDs changed on main (branch_id IS NULL)
    after the base commit. Used to detect conflicts.
    """
    query = db.query(CommitFile).join(Commit).filter(
        Commit.repository_id == repo_id,
        Commit.branch_id.is_(None),
    )
    if base_commit_id:
        base = db.get(Commit, base_commit_id)
        if base:
            query = query.filter(Commit.timestamp > base.timestamp)

    return {cf.document_id for cf in query.all()}


@router.post("/{repo_id}/branches/{branch_id}/merge-request")
def open_merge_request(repo_id: uuid.UUID, branch_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Preview what would happen if this branch were merged.
    Returns: list of changed documents, and any conflicts.
    Does NOT execute the merge — call /merge to do that.
    """
    branch = db.get(Branch, branch_id)
    if not branch or branch.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    if branch.status != "open":
        raise HTTPException(status_code=409, detail=f"Branch is already {branch.status}")

    branch_changes = _branch_changes(branch_id, branch.base_commit_id, db)
    main_changed_docs = _main_changes_since(repo_id, branch.base_commit_id, db)

    conflicts = [str(doc_id) for doc_id in branch_changes if doc_id in main_changed_docs]

    changed_files = [
        {"document_id": str(doc_id), "change_type": cf.change_type, "content_hash": cf.content_hash}
        for doc_id, cf in branch_changes.items()
    ]

    return {
        "branch": branch.name,
        "base_commit_id": str(branch.base_commit_id) if branch.base_commit_id else None,
        "changed_files": changed_files,
        "conflicts": conflicts,
        "can_merge": len(conflicts) == 0,
    }


@router.post("/{repo_id}/branches/{branch_id}/merge")
def execute_merge(
    repo_id: uuid.UUID,
    branch_id: uuid.UUID,
    author: str,
    db: Session = Depends(get_db),
):
    """
    Execute the merge: promote branch PDFs to main and close the branch.
    Blocked if there are conflicts (same document changed on both branch and main).
    """
    branch = db.get(Branch, branch_id)
    if not branch or branch.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    if branch.status != "open":
        raise HTTPException(status_code=409, detail=f"Branch is already {branch.status}")

    branch_changes = _branch_changes(branch_id, branch.base_commit_id, db)
    if not branch_changes:
        raise HTTPException(status_code=400, detail="Branch has no commits — nothing to merge")

    main_changed_docs = _main_changes_since(repo_id, branch.base_commit_id, db)
    conflicts = [str(doc_id) for doc_id in branch_changes if doc_id in main_changed_docs]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={"message": "Merge blocked — conflicts detected", "conflicts": conflicts},
        )

    # find the latest main commit to use as parent for the merge commit
    parent = (
        db.query(Commit)
        .filter(Commit.repository_id == repo_id, Commit.branch_id.is_(None))
        .order_by(desc(Commit.timestamp))
        .first()
    )

    # build a stable hash for the merge commit from all document hashes combined
    sorted_files = sorted(branch_changes.values(), key=lambda x: str(x.document_id))
    combined = "".join(cf.content_hash or "" for cf in sorted_files)
    merge_hash = hashlib.sha256(f"merge-{branch.name}-{combined}".encode()).hexdigest()[:8]

    merge_commit = Commit(
        repository_id=repo_id,
        branch_id=None,  # merge commit lives on main
        parent_id=parent.id if parent else None,
        author=author,
        message=f"Merge branch '{branch.name}'",
        short_hash=merge_hash,
        is_local=True,
        diff_report={
            "merge_from": branch.name,
            "documents_merged": len(branch_changes),
        },
        protocol_violations=[],
    )
    db.add(merge_commit)
    db.flush()

    # create CommitFiles on main pointing to the branch's latest PDFs
    for doc_id, branch_cf in branch_changes.items():
        db.add(CommitFile(
            commit_id=merge_commit.id,
            document_id=doc_id,
            s3_key_pdf=branch_cf.s3_key_pdf,
            content_hash=branch_cf.content_hash,
            change_type=branch_cf.change_type,
        ))

    branch.status = "merged"

    db.add(AuditEvent(
        repository_id=repo_id,
        actor=author,
        action="merge",
        entity_type="branch",
        entity_id=str(branch_id),
        details={
            "branch": branch.name,
            "merge_commit": merge_hash,
            "documents_merged": len(branch_changes),
        },
        is_breach=False,
    ))

    db.commit()

    return {
        "merge_commit_hash": merge_hash,
        "branch": branch.name,
        "status": "merged",
        "documents_merged": len(branch_changes),
    }

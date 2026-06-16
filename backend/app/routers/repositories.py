import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models.repository import Repository
from app.models.document import Document
from app.models.commit import Commit, CommitFile
from app.models.branch import Branch
from app.models.bom import BOMEntry
from app.models.revision import Revision
from app.models.revision_request import RevisionRequest
from app.models.audit import AuditEvent
from app.schemas.repositories import RepositoryCreate, RepositoryUpdate, RepositoryResponse, RepositoryListResponse
from app.vault_client import VaultClient
from app import storage

# all routes in this file are prefixed with /repos
router = APIRouter(prefix="/repos", tags=["repositories"])


def _resolve_remote_url(raw: str) -> str:
    """Turn a user-entered remote vault URL into a reachable base URL.

    Behind CloudFront the backend lives under /api, but a direct backend
    (e.g. http://localhost:8001) has no prefix — so we can't just append /api
    blindly. Instead we probe: try the URL as given, then with /api appended,
    and store whichever a healthy vault answers on. Raises if neither works,
    giving the user immediate feedback at link time instead of a silent
    "remote_unreachable" badge later.
    """
    url = raw.strip().rstrip("/")
    candidates = [url]
    if not url.endswith("/api"):
        candidates.append(f"{url}/api")

    for candidate in candidates:
        if VaultClient(remote_url=candidate).ping():
            return candidate

    raise HTTPException(
        status_code=502,
        detail=(
            f"No reachable vault found at '{url}' (tried with and without /api). "
            "Check the URL and that the remote vault is running."
        ),
    )


@router.post("/", response_model=RepositoryResponse, status_code=201)
def create_repository(body: RepositoryCreate, db: Session = Depends(get_db)):
    # check if a repository with this name already exists
    existing = db.query(Repository).filter(Repository.name == body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Repository '{body.name}' already exists")

    repo = Repository(
        name=body.name,
        description=body.description,
        remote_url=body.remote_url,
        watch_path=body.watch_path,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)  # reload from DB to get generated fields like id and created_at
    return repo


@router.get("/", response_model=list[RepositoryListResponse])
def list_repositories(db: Session = Depends(get_db)):
    repos = db.query(Repository).order_by(Repository.created_at.desc()).all()
    result = []
    for repo in repos:
        # count how many documents belong to this repository
        doc_count = db.query(Document).filter(Document.repository_id == repo.id).count()

        # find the most recent commit — None if the repo has never been committed to
        latest = (
            db.query(Commit)
            .filter(Commit.repository_id == repo.id)
            .order_by(desc(Commit.timestamp))
            .first()
        )

        result.append(RepositoryListResponse(
            id=repo.id,
            name=repo.name,
            description=repo.description,
            remote_url=repo.remote_url,
            created_at=repo.created_at,
            document_count=doc_count,
            latest_commit={
                "hash": latest.short_hash,
                "author": latest.author,
                "message": latest.message,
                "timestamp": latest.timestamp.isoformat(),
            } if latest else None,
        ))
    return result


@router.patch("/{repo_id}", response_model=RepositoryResponse)
def update_repository(repo_id: uuid.UUID, body: RepositoryUpdate, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if body.remote_url is not None:
        cleaned = body.remote_url.strip().rstrip("/")
        # empty string clears the link; otherwise probe and store a reachable URL
        new_url = _resolve_remote_url(cleaned) if cleaned else None
        # which remote repo to target: a chosen one, or None = create new (own id)
        new_target = body.remote_repo_id if new_url else None

        # if connecting to a specific remote repo, make sure it actually exists
        # there, so we link to it rather than silently creating a stray repo
        if new_url and new_target is not None:
            try:
                remote_ids = {str(r["id"]) for r in VaultClient(remote_url=new_url).list_repos()}
            except Exception:
                remote_ids = set()
            if str(new_target) not in remote_ids:
                raise HTTPException(status_code=404, detail="Chosen remote repository not found on that vault")

        # If the effective remote target (url OR repo id) changed, none of this
        # repo's commits exist there yet. Mark every commit unpushed so the next
        # push re-creates/populates the target and sends full history. Without
        # this, commits stay is_local=False from a past push, push reads that as
        # "previously synced", and a 404 from the fresh target is misread as
        # "remote deleted" — which clears the link and blocks every push.
        target_changed = (new_url != repo.remote_url) or (new_target != repo.remote_repo_id)
        if new_url and target_changed:
            db.query(Commit).filter(
                Commit.repository_id == repo_id,
                Commit.is_local.is_(False),
            ).update({"is_local": True}, synchronize_session=False)

        repo.remote_url = new_url
        repo.remote_repo_id = new_target if new_url else None
    db.commit()
    db.refresh(repo)
    return repo


@router.get("/{repo_id}", response_model=RepositoryResponse)
def get_repository(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.delete("/{repo_id}", status_code=204)
def delete_repository(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    doc_ids = [d.id for d in db.query(Document.id).filter(Document.repository_id == repo_id)]
    commit_ids = [c.id for c in db.query(Commit.id).filter(Commit.repository_id == repo_id)]

    # collect S3 keys before any DB deletes
    s3_keys = []
    if commit_ids:
        s3_keys = [
            cf.s3_key_pdf
            for cf in db.query(CommitFile.s3_key_pdf).filter(CommitFile.commit_id.in_(commit_ids))
            if cf.s3_key_pdf
        ]

    # revision requests carry repository_id directly — scope by it so none are
    # left behind even if a request's document row is already gone
    db.query(RevisionRequest).filter(RevisionRequest.repository_id == repo_id).delete(synchronize_session=False)

    # delete leaf records first (no children pointing to them)
    if doc_ids:
        db.query(BOMEntry).filter(BOMEntry.assembly_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(BOMEntry).filter(BOMEntry.component_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(Revision).filter(Revision.document_id.in_(doc_ids)).delete(synchronize_session=False)
    if commit_ids:
        db.query(CommitFile).filter(CommitFile.commit_id.in_(commit_ids)).delete(synchronize_session=False)

    db.query(AuditEvent).filter(AuditEvent.repository_id == repo_id).delete(synchronize_session=False)

    # break the commit ↔ branch circular FK before deleting either table
    db.query(Branch).filter(Branch.repository_id == repo_id).update(
        {"base_commit_id": None}, synchronize_session=False
    )
    # break the commit self-reference (parent_id) so bulk delete works
    if commit_ids:
        db.query(Commit).filter(Commit.repository_id == repo_id).update(
            {"parent_id": None}, synchronize_session=False
        )

    db.query(Commit).filter(Commit.repository_id == repo_id).delete(synchronize_session=False)
    db.query(Branch).filter(Branch.repository_id == repo_id).delete(synchronize_session=False)
    if doc_ids:
        db.query(Document).filter(Document.repository_id == repo_id).delete(synchronize_session=False)

    db.delete(repo)
    db.commit()

    # drain S3 files after the DB transaction succeeds
    for key in s3_keys:
        storage.delete_file(key)

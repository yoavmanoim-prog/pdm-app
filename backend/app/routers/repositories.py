import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models.repository import Repository
from app.models.document import Document
from app.models.commit import Commit
from app.schemas.repositories import RepositoryCreate, RepositoryResponse, RepositoryListResponse

# all routes in this file are prefixed with /repos
router = APIRouter(prefix="/repos", tags=["repositories"])


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
    db.delete(repo)
    db.commit()

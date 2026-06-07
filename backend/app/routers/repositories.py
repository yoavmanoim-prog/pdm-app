import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.repository import Repository
from app.schemas.repositories import RepositoryCreate, RepositoryResponse

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


@router.get("/", response_model=list[RepositoryResponse])
def list_repositories(db: Session = Depends(get_db)):
    # return all repositories ordered by creation time, newest first
    return db.query(Repository).order_by(Repository.created_at.desc()).all()


@router.get("/{repo_id}", response_model=RepositoryResponse)
def get_repository(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo

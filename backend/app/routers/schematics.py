import uuid
from typing import List
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Schematic
from app.schemas import DownloadResponse, SchematicResponse
from app import storage

router = APIRouter(prefix="/schematics", tags=["schematics"])


@router.post("/upload", response_model=SchematicResponse, status_code=201)
async def upload_schematic(
    file: UploadFile = File(...),
    part_number: str = Form(...),
    vehicle_make: str = Form(None),
    model: str = Form(None),
    description: str = Form(None),
    parent_id: uuid.UUID = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    version = 1
    if parent_id:
        parent = db.get(Schematic, parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent schematic not found")
        version = parent.version + 1

    s3_key = f"schematics/{part_number}/{uuid.uuid4()}.pdf"
    file_bytes = await file.read()
    storage.upload_file(file_bytes, s3_key)

    schematic = Schematic(
        part_number=part_number,
        vehicle_make=vehicle_make,
        model=model,
        description=description,
        s3_key=s3_key,
        version=version,
        parent_id=parent_id,
    )
    db.add(schematic)
    db.commit()
    db.refresh(schematic)
    return schematic


@router.get("", response_model=List[SchematicResponse])
def list_schematics(
    part_number: str = None,
    vehicle_make: str = None,
    model: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(Schematic).filter(Schematic.deleted == False, Schematic.parent_id.is_(None))  # noqa: E712
    if part_number:
        query = query.filter(Schematic.part_number.ilike(f"%{part_number}%"))
    if vehicle_make:
        query = query.filter(Schematic.vehicle_make.ilike(f"%{vehicle_make}%"))
    if model:
        query = query.filter(Schematic.model.ilike(f"%{model}%"))
    return query.all()


@router.get("/{schematic_id}", response_model=SchematicResponse)
def get_schematic(schematic_id: uuid.UUID, db: Session = Depends(get_db)):
    schematic = db.get(Schematic, schematic_id)
    if not schematic or schematic.deleted:
        raise HTTPException(status_code=404, detail="Schematic not found")
    return schematic


@router.get("/{schematic_id}/download", response_model=DownloadResponse)
def download_schematic(schematic_id: uuid.UUID, db: Session = Depends(get_db)):
    schematic = db.get(Schematic, schematic_id)
    if not schematic or schematic.deleted:
        raise HTTPException(status_code=404, detail="Schematic not found")
    url = storage.generate_presigned_url(schematic.s3_key)
    return {"url": url}


@router.get("/{schematic_id}/versions", response_model=List[SchematicResponse])
def get_versions(schematic_id: uuid.UUID, db: Session = Depends(get_db)):
    schematic = db.get(Schematic, schematic_id)
    if not schematic or schematic.deleted:
        raise HTTPException(status_code=404, detail="Schematic not found")
    return [schematic] + schematic.versions

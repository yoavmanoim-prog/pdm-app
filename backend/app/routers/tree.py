import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models.document import Document
from app.models.bom import BOMEntry
from app.models.commit import Commit, CommitFile
from app.models.revision import Revision
from app.schemas.bom import BOMEntryCreate, BOMEntryResponse

router = APIRouter(prefix="/repos", tags=["product-tree"])


# ── Step 21 — BOM endpoints ───────────────────────────────────────────────────

@router.post("/{repo_id}/bom", response_model=BOMEntryResponse, status_code=201)
def add_bom_entry(
    repo_id: uuid.UUID,
    assembly_id: uuid.UUID,
    body: BOMEntryCreate,
    db: Session = Depends(get_db),
):
    assembly = db.get(Document, assembly_id)
    if not assembly or assembly.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Assembly document not found")
    if assembly.doc_type != "assembly":
        raise HTTPException(status_code=400, detail="Target document is not an assembly")

    component = db.get(Document, body.component_id)
    if not component or component.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Component document not found")

    if body.component_id == assembly_id:
        raise HTTPException(status_code=400, detail="A document cannot be a component of itself")

    exists = db.query(BOMEntry).filter(
        BOMEntry.assembly_id == assembly_id,
        BOMEntry.component_id == body.component_id,
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Component already in this assembly's BOM")

    entry = BOMEntry(
        assembly_id=assembly_id,
        component_id=body.component_id,
        quantity=body.quantity,
        position=body.position,
        find_number=body.find_number,
        part_revision=body.part_revision,
        material=body.material,
        description=body.description,
        item_type=body.item_type,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{repo_id}/bom/{entry_id}", status_code=204)
def remove_bom_entry(repo_id: uuid.UUID, entry_id: uuid.UUID, db: Session = Depends(get_db)):
    entry = db.get(BOMEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="BOM entry not found")
    assembly = db.get(Document, entry.assembly_id)
    if not assembly or assembly.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="BOM entry not found")
    db.delete(entry)
    db.commit()


# ── Step 22 — product tree endpoint ──────────────────────────────────────────

def _build_node(doc: Document, db: Session, visited: set) -> dict:
    """Recursively build one tree node. visited prevents infinite loops."""
    visited = visited | {doc.id}

    latest_revision = (
        db.query(Revision)
        .filter(Revision.document_id == doc.id, Revision.status == "released")
        .order_by(desc(Revision.published_at))
        .first()
    )

    has_drawing = db.query(CommitFile).join(Commit).filter(
        CommitFile.document_id == doc.id,
        Commit.branch_id.is_(None),
    ).first() is not None

    node = {
        "id": str(doc.id),
        "part_number": doc.part_number,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "revision": latest_revision.revision_code if latest_revision else None,
        "revision_status": latest_revision.status if latest_revision else "unreleased",
        "has_drawing": has_drawing,
        "children": [],
    }

    if doc.doc_type == "assembly":
        for entry in db.query(BOMEntry).filter(BOMEntry.assembly_id == doc.id).all():
            if entry.component_id in visited:
                continue
            child_doc = db.get(Document, entry.component_id)
            if child_doc:
                child_node = _build_node(child_doc, db, visited)
                child_node["quantity"] = entry.quantity
                child_node["position"] = entry.position
                child_node["find_number"] = entry.find_number
                node["children"].append(child_node)

    return node


@router.get("/{repo_id}/tree")
def get_product_tree(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Top-level nodes = documents not used as a component anywhere."""
    all_docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    component_ids = {e.component_id for e in db.query(BOMEntry).all()}
    roots = [d for d in all_docs if d.id not in component_ids]
    return [_build_node(doc, db, set()) for doc in roots]


# ── Step 23 — tree validation ─────────────────────────────────────────────────

@router.get("/{repo_id}/tree/validate")
def validate_tree(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Status report for every document — used by protocol engine before publish."""
    docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    result = []

    for doc in docs:
        latest_rev = (
            db.query(Revision)
            .filter(Revision.document_id == doc.id)
            .order_by(desc(Revision.published_at))
            .first()
        )
        has_drawing = db.query(CommitFile).join(Commit).filter(
            CommitFile.document_id == doc.id,
            Commit.branch_id.is_(None),
        ).first() is not None

        result.append({
            "document_id": str(doc.id),
            "part_number": doc.part_number,
            "title": doc.title,
            "doc_type": doc.doc_type,
            "has_drawing": has_drawing,
            "revision": latest_rev.revision_code if latest_rev else None,
            "revision_status": latest_rev.status if latest_rev else "unreleased",
            "is_released": latest_rev is not None and latest_rev.status == "released",
        })

    released = sum(1 for r in result if r["is_released"])
    missing = sum(1 for r in result if not r["has_drawing"])

    return {
        "total": len(result),
        "released": released,
        "unreleased": len(result) - released,
        "missing_drawing": missing,
        "documents": result,
    }

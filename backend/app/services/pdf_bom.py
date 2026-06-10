import re
import uuid

import fitz  # pymupdf
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app import storage
from app.models.bom import BOMEntry
from app.models.commit import Commit, CommitFile
from app.models.document import Document

# Matches engineering part number formats: EVC-SA-8000, FW-PT-0001, ASM-001-1234
PART_NUMBER_RE = re.compile(r'\b[A-Z]{2,6}-[A-Z]{2,6}-\d{3,8}\b')


def _extract_text(pdf_bytes: bytes) -> str:
    parts = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page in pdf:
            t = page.get_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


def _extract_part_numbers(text: str) -> set:
    return {m.group() for m in PART_NUMBER_RE.finditer(text.upper())}


def _latest_commit_file(doc_id: uuid.UUID, repo_id: uuid.UUID, db: Session):
    return (
        db.query(CommitFile)
        .join(Commit)
        .filter(Commit.repository_id == repo_id, CommitFile.document_id == doc_id)
        .order_by(desc(Commit.timestamp))
        .first()
    )


def auto_link_sons(pdf_bytes: bytes, repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session) -> dict:
    """
    Scan a committed PDF for part numbers and auto-create BOM son entries for
    any that match existing documents in the repository.

    Part numbers found in the PDF but not yet in the repo are stored in the
    commit's diff_report["missing_components"] so validate_tree can surface them.

    Returns {"created": int, "missing": list[str]}
    """
    doc = db.get(Document, doc_id)
    if not doc or doc.doc_type not in ("assembly", "part"):
        return {"created": 0, "missing": []}

    repo_docs = (
        db.query(Document)
        .filter(Document.repository_id == repo_id, Document.id != doc_id)
        .all()
    )
    repo_by_part = {d.part_number.upper(): d for d in repo_docs}

    text = _extract_text(pdf_bytes)
    found = _extract_part_numbers(text)
    found.discard(doc.part_number.upper())

    if not found:
        return {"created": 0, "missing": []}

    created = 0
    missing = []

    for pn in found:
        if pn not in repo_by_part:
            missing.append(pn)
            continue

        candidate = repo_by_part[pn]
        if db.query(BOMEntry).filter(
            BOMEntry.assembly_id == doc_id,
            BOMEntry.component_id == candidate.id,
        ).first():
            continue

        db.add(BOMEntry(
            assembly_id=doc_id,
            component_id=candidate.id,
            quantity=1,
            item_type="assembly" if candidate.doc_type == "assembly" else "part",
        ))
        created += 1

    # persist missing parts in the latest commit for validate warnings
    if missing:
        cf = _latest_commit_file(doc_id, repo_id, db)
        if cf:
            report = dict(cf.commit.diff_report or {})
            report["missing_components"] = sorted(missing)
            cf.commit.diff_report = report

    if created or missing:
        db.commit()

    return {"created": created, "missing": missing}


def retro_link_fathers(repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session) -> int:
    """
    When a new document is committed, scan every existing assembly/part PDF in
    S3 to find any that reference this document's part number.
    Creates BOM entries retroactively and clears the part from missing_components.
    Returns the number of new BOM entries created.
    """
    doc = db.get(Document, doc_id)
    if not doc:
        return 0

    assembly_docs = (
        db.query(Document)
        .filter(
            Document.repository_id == repo_id,
            Document.id != doc_id,
            Document.doc_type.in_(["assembly", "part"]),
        )
        .all()
    )
    if not assembly_docs:
        return 0

    target = doc.part_number.upper()
    created = 0

    for assembly in assembly_docs:
        cf = _latest_commit_file(assembly.id, repo_id, db)
        if not cf or not cf.s3_key_pdf:
            continue

        # skip if already linked
        if db.query(BOMEntry).filter(
            BOMEntry.assembly_id == assembly.id,
            BOMEntry.component_id == doc_id,
        ).first():
            continue

        try:
            pdf_bytes = storage.download_file(cf.s3_key_pdf)
            found = _extract_part_numbers(_extract_text(pdf_bytes))
        except Exception:
            continue

        if target not in found:
            continue

        db.add(BOMEntry(
            assembly_id=assembly.id,
            component_id=doc_id,
            quantity=1,
            item_type="assembly" if doc.doc_type == "assembly" else "part",
        ))
        created += 1

        # remove this part from the assembly's missing_components list
        report = dict(cf.commit.diff_report or {})
        missing = report.get("missing_components", [])
        report["missing_components"] = [m for m in missing if m.upper() != target]
        cf.commit.diff_report = report

    if created:
        db.commit()

    return created

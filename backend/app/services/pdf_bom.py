import io
import logging
import re
import uuid

import fitz  # pymupdf
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app import storage
from app.models.bom import BOMEntry
from app.models.commit import Commit, CommitFile
from app.models.document import Document

logger = logging.getLogger(__name__)

# Used only for detecting MISSING parts (not for BOM creation).
# BOM creation uses direct substring search so any naming convention works.
PART_NUMBER_RE = re.compile(r'\b[A-Z]{2,6}-[A-Z]{2,6}-\d{3,8}\b')

# If the text layer has fewer characters than this, the PDF is likely
# image-based and we fall back to OCR.
_OCR_THRESHOLD = 30


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF. Falls back to OCR for image-based (scanned) drawings."""
    parts = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page in pdf:
            t = page.get_text()
            if t:
                parts.append(t)
    text = "\n".join(parts)

    if len(text.strip()) >= _OCR_THRESHOLD:
        return text

    # Text layer is empty or too sparse — fall back to Tesseract OCR
    logger.info("pdf_bom: sparse text layer (%d chars), running OCR", len(text.strip()))
    return _ocr_pdf(pdf_bytes)


def _ocr_pdf(pdf_bytes: bytes) -> str:
    """Render each PDF page as an image and run Tesseract OCR on it."""
    try:
        import pytesseract
        from PIL import Image

        parts = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            for page in pdf:
                # 3× zoom (~216 DPI) — engineering drawings have small text
                pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_text = pytesseract.image_to_string(img)
                if ocr_text:
                    parts.append(ocr_text)

        return "\n".join(parts)
    except Exception as e:
        logger.warning("pdf_bom: OCR failed: %s", e)
        return ""


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
    Scan a committed PDF and auto-create BOM son entries.

    Uses direct substring search against known repo part numbers — works with
    any naming convention, no regex required for BOM creation.

    Also records unmatched regex-matched tokens as missing_components for
    the validate tab (best-effort, requires AAA-BB-0000 format).

    Returns {"created": int, "missing": list[str]}
    """
    doc = db.get(Document, doc_id)
    if not doc or doc.doc_type not in ("assembly", "part"):
        return {"created": 0, "missing": []}

    # extract text first — missing detection must run even with 0 other docs
    text_upper = _extract_text(pdf_bytes).upper()
    if not text_upper.strip():
        logger.info("pdf_bom: no extractable text in PDF for doc %s (image-based?)", doc_id)
        return {"created": 0, "missing": []}

    repo_docs = (
        db.query(Document)
        .filter(Document.repository_id == repo_id, Document.id != doc_id)
        .all()
    )

    # BOM creation — direct substring match, works with any part number format
    created = 0
    for candidate in repo_docs:
        if candidate.part_number.upper() not in text_upper:
            continue
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
        logger.info("pdf_bom: auto-linked %s as son of %s", candidate.part_number, doc.part_number)

    # Missing detection — regex tokens not found in the repo (best-effort)
    known = {d.part_number.upper() for d in repo_docs} | {doc.part_number.upper()}
    regex_found = {m.group() for m in PART_NUMBER_RE.finditer(text_upper)}
    missing = sorted(regex_found - known)

    if missing:
        cf = _latest_commit_file(doc_id, repo_id, db)
        if cf:
            report = dict(cf.commit.diff_report or {})
            report["missing_components"] = missing
            cf.commit.diff_report = report

    if created or missing:
        db.commit()

    return {"created": created, "missing": missing}


def retro_link_fathers(repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session) -> int:
    """
    When a new document is committed, scan existing assembly/part PDFs in S3
    using direct substring search to find retroactive parent references.
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

        if db.query(BOMEntry).filter(
            BOMEntry.assembly_id == assembly.id,
            BOMEntry.component_id == doc_id,
        ).first():
            continue

        try:
            text_upper = _extract_text(storage.download_file(cf.s3_key_pdf)).upper()
        except Exception as e:
            logger.warning("pdf_bom: could not read S3 PDF for %s: %s", assembly.part_number, e)
            continue

        if target not in text_upper:
            continue

        db.add(BOMEntry(
            assembly_id=assembly.id,
            component_id=doc_id,
            quantity=1,
            item_type="assembly" if doc.doc_type == "assembly" else "part",
        ))
        created += 1
        logger.info("pdf_bom: retro-linked %s as component of %s", doc.part_number, assembly.part_number)

        # clear from missing_components now that the part is committed
        report = dict(cf.commit.diff_report or {})
        report["missing_components"] = [
            m for m in report.get("missing_components", []) if m.upper() != target
        ]
        cf.commit.diff_report = report

    if created:
        db.commit()

    return created

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
from app.models.repository import Repository
from app.settings_config import effective_settings, example_to_pattern

logger = logging.getLogger(__name__)

# Default pattern for detecting MISSING parts (not for BOM creation), used when a
# repo hasn't configured its own part-number format. BOM creation uses direct
# substring search so any naming convention works.
PART_NUMBER_RE = re.compile(r'\b[A-Z]{2,6}-[A-Z]{2,6}-\d{3,8}\b')


def _missing_detection_re(repo_id: uuid.UUID, db: Session) -> "re.Pattern":
    """The pattern used to spot part-number-shaped tokens in a drawing. Uses the
    repo's configured format (from its sample part number) if set, else the
    built-in default."""
    repo = db.get(Repository, repo_id)
    example = effective_settings(repo)["part_number_example"]
    if example:
        return re.compile(r'\b' + example_to_pattern(example) + r'\b', re.IGNORECASE)
    return PART_NUMBER_RE


# If the text layer has fewer characters than this, the PDF is likely
# image-based and we fall back to OCR.
_OCR_THRESHOLD = 30


def _token_present(text_upper: str, token: str) -> bool:
    """True if token appears as a standalone part number in the text.

    A plain substring test would let AB-CD-1 match inside AB-CD-12, creating
    false BOM links. We require that the characters bordering the match are
    not part-number characters (letters, digits, hyphen), so only whole
    part-number tokens count. Both args are expected to be uppercase.
    """
    if not token:
        return False
    pattern = r'(?<![A-Z0-9-])' + re.escape(token) + r'(?![A-Z0-9-])'
    return re.search(pattern, text_upper) is not None


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

    # BOM creation — match on base part number (strips " -Title" suffix if present)
    created = 0
    for candidate in repo_docs:
        base = candidate.part_number.split(' -')[0].strip().upper()
        if not _token_present(text_upper, base):
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
    # Build known set: full part_number string + base part number (before " -" title separator)
    known = set()
    for d in [*repo_docs, doc]:
        known.add(d.part_number.upper())
        known.add(d.part_number.split(' -')[0].strip().upper())
    regex_found = {m.group().upper() for m in _missing_detection_re(repo_id, db).finditer(text_upper)}
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

    # use base part number for matching (strips " -Title" suffix if present)
    target = doc.part_number.split(' -')[0].strip().upper()
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

        if not _token_present(text_upper, target):
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

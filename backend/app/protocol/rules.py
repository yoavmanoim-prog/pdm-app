"""
Protocol rules for the metal factory PDM system.
Each rule is a class with a validate() method.
Empty list = passed. Non-empty list = violations that block the action.
"""
import fitz  # PyMuPDF — used to read PDF content
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.document import Document
from app.models.revision import Revision
from app.models.bom import BOMEntry
from app.models.commit import Commit, CommitFile
from app import storage

# Valid revision sequence — I and O are skipped (look like 1 and 0)
REVISION_SEQUENCE = list("ABCDEFGHJKLMNP")

# Keywords that indicate a BOM table is present in the drawing
# Any two of these found together = BOM table detected
BOM_TABLE_KEYWORDS = {"ITEM", "QTY", "QUANTITY", "PART NO", "PART NUMBER", "DESCRIPTION", "DESC", "MATERIAL"}


def _next_expected(current_code: str) -> str | None:
    """Returns the letter that must follow current_code."""
    try:
        idx = REVISION_SEQUENCE.index(current_code.upper())
        return REVISION_SEQUENCE[idx + 1] if idx + 1 < len(REVISION_SEQUENCE) else None
    except ValueError:
        return None


def _extract_pdf_text(document: Document, db: Session) -> str | None:
    """Download and extract all text from the latest committed PDF for a document."""
    latest_file = (
        db.query(CommitFile)
        .join(Commit)
        .filter(CommitFile.document_id == document.id, Commit.branch_id.is_(None))
        .order_by(desc(Commit.timestamp))
        .first()
    )
    if not latest_file or not latest_file.s3_key_pdf:
        return None
    try:
        pdf_bytes = storage.download_file(latest_file.s3_key_pdf)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = " ".join(page.get_text() for page in doc).upper()
        doc.close()
        return text
    except Exception:
        return None


class RevisionSequenceRule:
    """Cannot skip revision letters. A must come before B, B before C, etc."""

    def validate(self, document: Document, proposed_code: str, db: Session) -> list[str]:
        proposed_code = proposed_code.upper()

        if proposed_code not in REVISION_SEQUENCE:
            return [
                f"'{proposed_code}' is not a valid revision letter. "
                f"Valid sequence: {', '.join(REVISION_SEQUENCE)}"
            ]

        latest = (
            db.query(Revision)
            .filter(Revision.document_id == document.id)
            .order_by(Revision.published_at.desc())
            .first()
        )

        if latest is None:
            if proposed_code != "A":
                return [f"First revision must be Rev A, not Rev {proposed_code}"]
            return []

        expected = _next_expected(latest.revision_code)
        if expected is None:
            return ["Maximum revision letter reached"]
        if proposed_code != expected:
            return [
                f"Revision sequence violation: current is Rev {latest.revision_code}, "
                f"next must be Rev {expected}, not Rev {proposed_code}"
            ]
        return []


class AssemblyHasBOMTableRule:
    """
    The assembly drawing PDF must contain a BOM table in its content.
    Checks for standard engineering drawing BOM column headers
    (ITEM, QTY, PART NO, DESCRIPTION, etc.) inside the PDF text.
    """

    def validate(self, document: Document, db: Session) -> list[str]:
        if document.doc_type != "assembly":
            return []

        text = _extract_pdf_text(document, db)

        if text is None:
            return [
                f"Assembly '{document.part_number}' has no drawing uploaded. "
                f"Upload the drawing PDF before publishing."
            ]

        # count how many BOM keywords appear in the drawing text
        found = {kw for kw in BOM_TABLE_KEYWORDS if kw in text}
        if len(found) < 2:
            return [
                f"Assembly drawing '{document.part_number}' does not appear to contain a BOM table. "
                f"The drawing must include a parts list with columns such as "
                f"ITEM, QTY, PART NO, and DESCRIPTION."
            ]
        return []


class AssemblyChildrenReleasedRule:
    """All component parts in an assembly's BOM must be released before the assembly can be."""

    def validate(self, document: Document, db: Session) -> list[str]:
        if document.doc_type != "assembly":
            return []

        violations = []
        for entry in db.query(BOMEntry).filter(BOMEntry.assembly_id == document.id).all():
            component = db.get(Document, entry.component_id)
            if not component:
                continue
            released = (
                db.query(Revision)
                .filter(
                    Revision.document_id == entry.component_id,
                    Revision.status == "released",
                )
                .first()
            )
            if not released:
                violations.append(
                    f"Component '{component.part_number} — {component.title}' is not released. "
                    f"All components must be released before releasing the assembly."
                )
        return violations


class ChangeReasonRequiredRule:
    """Rev B and later require a documented change reason (change_note)."""

    def validate(self, document: Document, proposed_code: str, change_note: str | None, db: Session) -> list[str]:
        if proposed_code.upper() == "A":
            return []

        if not change_note or not change_note.strip():
            return [
                f"Rev {proposed_code.upper()} requires a change note explaining what changed. "
                f"Mandatory for all revisions after Rev A."
            ]
        return []


class ReleasedDocumentImmutableRule:
    """A released document cannot be committed to — a new revision must be opened."""

    def validate(self, document: Document, db: Session) -> list[str]:
        latest = (
            db.query(Revision)
            .filter(Revision.document_id == document.id)
            .order_by(Revision.published_at.desc())
            .first()
        )
        if latest and latest.status == "released":
            return [
                f"Document '{document.part_number}' is at Rev {latest.revision_code} (released). "
                f"Publish a new revision to modify it."
            ]
        return []

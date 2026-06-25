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
from app.models.repository import Repository
from app.settings_config import effective_settings
from app import storage

# Valid revision sequence for the "letters" scheme — I and O are skipped
# (look like 1 and 0). The "numbers" scheme uses 001, 002, 003 ...
REVISION_SEQUENCE = list("ABCDEFGHJKLMNP")


def _scheme_for(document: Document, db: Session) -> str:
    """The repo's revision-code scheme ('letters' or 'numbers')."""
    repo = db.get(Repository, document.repository_id)
    return effective_settings(repo)["revision_scheme"]


def is_valid_revision(scheme: str, code: str) -> bool:
    if scheme == "numbers":
        return bool(code) and code.isdigit()
    return bool(code) and code.upper() in REVISION_SEQUENCE


def revision_rank(scheme: str, code: str):
    """Ordering value for a revision code, or None if it isn't valid for the scheme."""
    if scheme == "numbers":
        return int(code) if code and code.isdigit() else None
    try:
        return REVISION_SEQUENCE.index(code.upper())
    except (ValueError, AttributeError):
        return None


def first_revision(scheme: str) -> str:
    return "001" if scheme == "numbers" else REVISION_SEQUENCE[0]


def next_revision(scheme: str, current: str):
    """Next code after current; None if there's no next (letters maxed at P,
    numbers capped at 999)."""
    if scheme == "numbers":
        nxt = (int(current) + 1) if (current and current.isdigit()) else 1
        return f"{nxt:03d}" if nxt <= 999 else None
    try:
        idx = REVISION_SEQUENCE.index(current.upper())
    except (ValueError, AttributeError):
        return REVISION_SEQUENCE[0]
    return REVISION_SEQUENCE[idx + 1] if idx + 1 < len(REVISION_SEQUENCE) else None


# Keywords that indicate a BOM table is present in the drawing.
# Based on real factory drawing headers: Item, Quantity, Name, Part number, Description, Material, Revision
# PDF extraction sometimes splits words (e.g. "QUANTI TY") so we check partial tokens too.
# At least 3 of these must be found — a single word match is not enough.
BOM_TABLE_KEYWORDS = {
    "ITEM", "QUANTITY", "QUANTI",   # "QUANTI TY" split variant
    "PART NUMBER", "PART NO",
    "DESCRIPTION",
    "MATERIAL",
    "REVISION", "REVISI",           # "REVISI ON" split variant
}


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
    """Revisions move strictly forward through the sequence.

    Skipping is allowed (A -> C is fine), but a release must use a letter that
    comes *later* than the current revision — no duplicates and no going
    backward. The first release can be any valid letter (it does not have to be
    Rev A).
    """

    def validate(self, document: Document, proposed_code: str, db: Session) -> list[str]:
        scheme = _scheme_for(document, db)
        code = (proposed_code or "").strip()

        if not is_valid_revision(scheme, code):
            if scheme == "numbers":
                return [f"'{proposed_code}' is not a valid revision number — use digits, e.g. 001, 002, 003."]
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

        # first release may be any valid value — no requirement to start at A/001
        if latest is None:
            return []

        current_rank = revision_rank(scheme, latest.revision_code)
        if current_rank is None:
            # current code isn't valid for this scheme (e.g. the repo just
            # switched letters<->numbers) — don't block the changeover
            return []

        # strictly forward: later than the current one. Rejects duplicates and
        # going backward, while allowing skips.
        if revision_rank(scheme, code) <= current_rank:
            unit = "number" if scheme == "numbers" else "letter"
            return [
                f"Revision must move forward: current is Rev {latest.revision_code}, "
                f"so Rev {proposed_code} is not allowed — choose a later {unit}."
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
        if len(found) < 3:
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

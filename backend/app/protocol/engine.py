"""
Protocol engine — runs all rules against a document and returns a structured result.
"""
from sqlalchemy.orm import Session
from app.models.document import Document
from app.protocol.rules import (
    RevisionSequenceRule,
    AssemblyHasBOMTableRule,
    AssemblyChildrenReleasedRule,
    ChangeReasonRequiredRule,
    ReleasedDocumentImmutableRule,
)


def run_publish_checks(
    document: Document,
    proposed_code: str,
    change_note: str | None,
    db: Session,
) -> dict:
    """
    Run all protocol rules before publishing a revision.
    Returns {"passed": bool, "violations": [str]}.
    """
    violations = []

    violations += RevisionSequenceRule().validate(document, proposed_code, db)
    violations += AssemblyHasBOMTableRule().validate(document, db)
    violations += AssemblyChildrenReleasedRule().validate(document, db)
    violations += ChangeReasonRequiredRule().validate(document, proposed_code, change_note, db)

    return {"passed": len(violations) == 0, "violations": violations}


def run_commit_checks(document: Document, db: Session) -> dict:
    """
    Run commit-time checks — only the immutability rule applies here.
    Returns {"passed": bool, "violations": [str]}.
    """
    violations = ReleasedDocumentImmutableRule().validate(document, db)
    return {"passed": len(violations) == 0, "violations": violations}

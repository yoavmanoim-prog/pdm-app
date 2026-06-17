"""Protocol rules — release-gating rules in app/protocol/rules.py."""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.repository import Repository
from app.models.document import Document
from app.models.revision import Revision
from app.protocol.rules import RevisionSequenceRule


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _doc(db):
    repo = Repository(name="r-" + uuid.uuid4().hex[:8])
    db.add(repo)
    db.flush()
    doc = Document(repository_id=repo.id, part_number="P-1", title="t", doc_type="part")
    db.add(doc)
    db.flush()
    return doc


def _release(db, doc, code, minutes=0):
    # commit_id FK isn't enforced by sqlite in tests, so a placeholder is fine
    db.add(Revision(
        document_id=doc.id, commit_id=uuid.uuid4(), revision_code=code,
        status="released", published_at=datetime(2026, 1, 1) + timedelta(minutes=minutes),
    ))
    db.flush()


def _check(db, doc, code):
    return RevisionSequenceRule().validate(doc, code, db)


# ── Rule 1: revisions move strictly forward ────────────────────────────────────

def test_first_release_can_be_any_letter(db):
    doc = _doc(db)
    assert _check(db, doc, "A") == []
    assert _check(db, doc, "C") == []   # A is not required to be first


def test_skipping_forward_is_allowed(db):
    doc = _doc(db)
    _release(db, doc, "A")
    assert _check(db, doc, "C") == []   # skip B -> allowed


def test_immediate_next_is_allowed(db):
    doc = _doc(db)
    _release(db, doc, "B")
    assert _check(db, doc, "C") == []


def test_duplicate_is_blocked(db):
    doc = _doc(db)
    _release(db, doc, "B")
    assert _check(db, doc, "B")         # same letter -> violation


def test_backward_is_blocked(db):
    doc = _doc(db)
    _release(db, doc, "C")
    assert _check(db, doc, "B")         # earlier letter -> violation


def test_invalid_letter_is_blocked(db):
    doc = _doc(db)
    assert _check(db, doc, "I")         # I is excluded from the sequence
    assert _check(db, doc, "Z")


def test_compares_against_latest_release(db):
    doc = _doc(db)
    _release(db, doc, "A", minutes=0)
    _release(db, doc, "D", minutes=10)  # latest is D
    assert _check(db, doc, "E") == []   # forward from D
    assert _check(db, doc, "C")         # behind the latest (D) -> blocked

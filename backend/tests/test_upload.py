"""
Tests for the document upload path — specifically the two bugs that mirrored
create_commit incorrectly: the no-op guard compared against a random prior
version (ordered by a UUID), and short_hash wasn't salted so the same PDF in
two documents collided on the global unique constraint.

S3 and BOM extraction are stubbed so the endpoint runs without AWS or PyMuPDF.
"""
from app.models.document import Document
from app.models.repository import Repository


def _seed_repo_with_two_docs(sm):
    db = sm()
    repo = Repository(name="Gearbox")
    db.add(repo)
    db.flush()
    d1 = Document(repository_id=repo.id, part_number="GB-1", title="A", doc_type="detail")
    d2 = Document(repository_id=repo.id, part_number="GB-2", title="B", doc_type="detail")
    db.add_all([d1, d2])
    db.commit()
    ids = (repo.id, d1.id, d2.id)
    db.close()
    return ids


def _stub_io(monkeypatch):
    monkeypatch.setattr("app.config.settings.S3_BUCKET", "test-bucket")
    monkeypatch.setattr("app.storage.upload_file", lambda content, key, content_type="": key)
    monkeypatch.setattr("app.services.pdf_bom.auto_link_sons", lambda *a, **k: {"created": 0, "missing": []})
    monkeypatch.setattr("app.services.pdf_bom.retro_link_fathers", lambda *a, **k: 0)


def _upload(client, repo_id, doc_id, body):
    return client.post(
        f"/repos/{repo_id}/documents/{doc_id}/upload",
        files={"file": ("drawing.pdf", body, "application/pdf")},
        data={"author": "alice", "message": "m"},
    )


def test_same_pdf_in_two_documents_gets_distinct_hashes(vaults, monkeypatch):
    """The same PDF uploaded to two documents must both succeed with different
    short_hashes — before the salting fix the second collided on the global
    unique constraint and returned a 409 that no retry could clear."""
    _stub_io(monkeypatch)
    repo_id, d1, d2 = _seed_repo_with_two_docs(vaults.local)
    pdf = b"%PDF-1.4 identical bytes"

    r1 = _upload(vaults.client, repo_id, d1, pdf)
    r2 = _upload(vaults.client, repo_id, d2, pdf)

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["commit_hash"] != r2.json()["commit_hash"]


def test_reupload_same_pdf_is_noop_but_changed_pdf_is_accepted(vaults, monkeypatch):
    """The no-op guard must compare against the LATEST version of this document:
    re-uploading the same bytes is rejected, a different file is accepted."""
    _stub_io(monkeypatch)
    repo_id, d1, _ = _seed_repo_with_two_docs(vaults.local)

    assert _upload(vaults.client, repo_id, d1, b"%PDF-1.4 v1").status_code == 200
    assert _upload(vaults.client, repo_id, d1, b"%PDF-1.4 v1").status_code == 400  # no-op
    assert _upload(vaults.client, repo_id, d1, b"%PDF-1.4 v2").status_code == 200  # real change

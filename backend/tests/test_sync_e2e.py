"""
End-to-end push/pull tests between a local and a remote vault.

These guard against the class of bug that has repeatedly killed sync in merges:
undefined names (the F821 NameErrors) and dropped payload fields (the
diff_report_patches mismatch). Both only surface when push and pull actually run
the full serialize → validate → persist round trip, which is what these do.
"""
import uuid
from datetime import datetime

from app.models.bom import BOMEntry
from app.models.commit import Commit, CommitFile
from app.models.document import Document
from app.models.repository import Repository
from app.models.revision import Revision


class SimpleIds(dict):
    """Attribute access over a dict of seeded ids, e.g. ids.repo_id."""
    __getattr__ = dict.__getitem__


def _seed_local_repo(sm, *, is_local=True):
    """A local repo with one document and one committed PDF, ready to push."""
    db = sm()
    repo = Repository(name="Gearbox", description="d", remote_url="http://remote.test")
    db.add(repo)
    db.flush()
    doc = Document(repository_id=repo.id, part_number="GB-100", title="Housing", doc_type="detail")
    db.add(doc)
    db.flush()
    commit = Commit(
        repository_id=repo.id,
        author="alice",
        message="initial",
        short_hash="aaaa1111",
        is_local=is_local,
        diff_report={"missing_components": ["GB-999"]},
        protocol_violations=[],
    )
    db.add(commit)
    db.flush()
    db.add(CommitFile(
        commit_id=commit.id,
        document_id=doc.id,
        s3_key_pdf="gearbox/housing/aaaa1111.pdf",
        content_hash="hash-housing",
        change_type="added",
    ))
    db.commit()
    ids = SimpleIds(repo_id=repo.id, doc_id=doc.id, commit_id=commit.id)
    db.close()
    return ids


def _seed_remote_repo(sm):
    """A remote repo with a document, commit, BOM entry, and released revision —
    the full set a fresh local vault should receive on pull."""
    db = sm()
    repo = Repository(name="Gearbox", description="d")
    db.add(repo)
    db.flush()
    assembly = Document(repository_id=repo.id, part_number="GB-100", title="Housing", doc_type="assembly")
    component = Document(repository_id=repo.id, part_number="GB-101", title="Bolt", doc_type="part")
    db.add_all([assembly, component])
    db.flush()
    commit = Commit(
        repository_id=repo.id,
        author="bob",
        message="release",
        short_hash="bbbb2222",
        is_local=False,
        diff_report={"note": "ok"},
        protocol_violations=[],
        timestamp=datetime(2026, 1, 2, 3, 4, 5),
    )
    db.add(commit)
    db.flush()
    db.add(CommitFile(
        commit_id=commit.id,
        document_id=assembly.id,
        s3_key_pdf="gearbox/housing/bbbb2222.pdf",
        content_hash="hash-remote",
        change_type="added",
    ))
    db.add(BOMEntry(
        assembly_id=assembly.id,
        component_id=component.id,
        quantity=4,
        item_type="part",
    ))
    db.add(Revision(
        document_id=assembly.id,
        commit_id=commit.id,
        revision_code="A",
        status="released",
        published_by="bob",
        published_at=datetime(2026, 1, 2, 3, 4, 5),
        passed_protocol=True,
        violations=[],
    ))
    db.commit()
    ids = SimpleIds(repo_id=repo.id, assembly_id=assembly.id, component_id=component.id, commit_id=commit.id)
    db.close()
    return ids


def _link_local_repo(sm, repo_id):
    """Create the bare local Repository row a vault has after linking a remote,
    before it has pulled anything. pull() relies on this row already existing."""
    db = sm()
    db.add(Repository(id=repo_id, name="Gearbox", remote_url="http://remote.test"))
    db.commit()
    db.close()


# ── Push ──────────────────────────────────────────────────────────────────────

def test_first_push_creates_repo_on_remote(vaults):
    """A brand-new repo's first push must succeed and create it on the remote.
    Regression guard: the remote 404s because the repo doesn't exist there yet,
    which must NOT be mistaken for 'remote deleted'."""
    ids = _seed_local_repo(vaults.local)

    r = vaults.client.post(f"/sync/push/{ids.repo_id}")
    assert r.status_code == 200, r.text
    assert r.json()["pushed"] == 1

    rdb = vaults.remote()
    assert rdb.get(Repository, ids.repo_id) is not None
    assert rdb.get(Document, ids.doc_id) is not None
    stored = rdb.query(Commit).filter(Commit.repository_id == ids.repo_id).one()
    # diff_report_patches must survive the round trip (the field-drop bug site)
    assert stored.diff_report == {"missing_components": ["GB-999"]}
    rdb.close()

    ldb = vaults.local()
    assert ldb.get(Commit, ids.commit_id).is_local is False  # marked pushed
    ldb.close()


def test_first_push_does_not_clear_remote_url(vaults):
    """The first-push 404 must not unlink the repo's remote_url."""
    ids = _seed_local_repo(vaults.local)
    vaults.client.post(f"/sync/push/{ids.repo_id}")

    ldb = vaults.local()
    assert ldb.get(Repository, ids.repo_id).remote_url == "http://remote.test"
    ldb.close()


def test_push_to_deleted_remote_clears_link(vaults):
    """A previously-synced repo that 404s on the remote really was deleted —
    clear the link and report 404. Guards the PR #80 desync behavior so the
    first-push fix doesn't swallow genuine deletions."""
    db = vaults.local()
    repo = Repository(name="Gearbox", remote_url="http://remote.test")
    db.add(repo)
    db.flush()
    doc = Document(repository_id=repo.id, part_number="GB-100", title="Housing", doc_type="detail")
    db.add(doc)
    db.flush()
    # an already-pushed commit (is_local=False) means the repo was synced before
    db.add(Commit(repository_id=repo.id, author="a", message="old",
                  short_hash="old00001", is_local=False, protocol_violations=[]))
    # a new commit waiting to be pushed
    db.add(Commit(repository_id=repo.id, author="a", message="new",
                  short_hash="new00002", is_local=True, protocol_violations=[]))
    db.commit()
    repo_id = repo.id
    db.close()

    # remote is empty → snapshot 404 → repo was deleted on the remote
    r = vaults.client.post(f"/sync/push/{repo_id}")
    assert r.status_code == 404

    ldb = vaults.local()
    assert ldb.get(Repository, repo_id).remote_url is None  # link cleared
    ldb.close()


def test_push_then_pull_into_second_vault(vaults):
    """Push from vault A, then a second local vault (same linked repo, no commits
    yet) pulls the same commit back — a full A → remote → B round trip."""
    ids = _seed_local_repo(vaults.local)
    push = vaults.client.post(f"/sync/push/{ids.repo_id}")
    assert push.status_code == 200, push.text

    # stand in for a second local vault: keep the linked Repository row, drop the
    # commits/docs it hasn't received yet
    db = vaults.local()
    db.query(CommitFile).delete()
    db.query(Commit).delete()
    db.query(Document).delete()
    db.commit()
    db.close()

    pull = vaults.client.post(f"/sync/pull/{ids.repo_id}")
    assert pull.status_code == 200, pull.text
    assert pull.json()["pulled"] == 1

    ldb = vaults.local()
    assert ldb.query(Commit).filter(Commit.short_hash == "aaaa1111").count() == 1
    assert ldb.query(Document).filter(Document.id == ids.doc_id).count() == 1
    ldb.close()


# ── Pull ──────────────────────────────────────────────────────────────────────

def test_pull_brings_commits_bom_and_revisions(vaults):
    """Pull must hydrate a linked local vault with commits, BOM entries, and
    revisions — the snapshot() + pull() paths where Revision NameErrors lived."""
    ids = _seed_remote_repo(vaults.remote)
    _link_local_repo(vaults.local, ids.repo_id)

    r = vaults.client.post(f"/sync/pull/{ids.repo_id}")
    assert r.status_code == 200, r.text
    assert r.json()["pulled"] == 1

    ldb = vaults.local()
    assert ldb.query(Commit).filter(Commit.short_hash == "bbbb2222").count() == 1
    assert ldb.query(BOMEntry).filter(BOMEntry.assembly_id == ids.assembly_id).count() == 1
    rev = ldb.query(Revision).filter(Revision.document_id == ids.assembly_id).one()
    assert rev.revision_code == "A"
    assert rev.status == "released"
    ldb.close()


def test_pull_missing_remote_repo_returns_404(vaults):
    """Pulling a repo the remote has never seen returns 404 (remote deleted)."""
    missing = uuid.uuid4()
    _link_local_repo(vaults.local, missing)
    r = vaults.client.post(f"/sync/pull/{missing}")
    assert r.status_code == 404


# ── Linking to a chosen remote repo (different id) ─────────────────────────────

def test_push_to_chosen_remote_repo_id(vaults):
    """A local repo linked to a remote repo with a DIFFERENT id pushes its
    commits/docs under the remote's id (populate an empty remote from local)."""
    # an empty remote repo to receive the push
    rdb = vaults.remote()
    remote_repo = Repository(name="Remote Gearbox")
    rdb.add(remote_repo)
    rdb.commit()
    remote_id = remote_repo.id
    rdb.close()

    # local repo (its own id) linked to remote_repo_id = remote_id
    ldb = vaults.local()
    repo = Repository(name="Local Gearbox", remote_url="http://remote.test", remote_repo_id=remote_id)
    ldb.add(repo)
    ldb.flush()
    doc = Document(repository_id=repo.id, part_number="GB-1", title="Housing", doc_type="detail")
    ldb.add(doc)
    ldb.flush()
    commit = Commit(repository_id=repo.id, author="a", message="m", short_hash="aaaa1111",
                    is_local=True, protocol_violations=[])
    ldb.add(commit)
    ldb.flush()
    ldb.add(CommitFile(commit_id=commit.id, document_id=doc.id, s3_key_pdf="k",
                       content_hash="h", change_type="added"))
    ldb.commit()
    local_id, doc_id = repo.id, doc.id
    ldb.close()

    r = vaults.client.post(f"/sync/push/{local_id}")
    assert r.status_code == 200, r.text
    assert r.json()["pushed"] == 1

    # commit + doc landed under the REMOTE repo id, not the local id
    rdb = vaults.remote()
    assert rdb.query(Commit).filter(Commit.short_hash == "aaaa1111").one().repository_id == remote_id
    assert rdb.get(Document, doc_id).repository_id == remote_id
    rdb.close()


def test_pull_from_chosen_remote_repo_id(vaults):
    """Pulling from a remote repo with a different id stores everything under the
    LOCAL repo id (clone a populated remote into a fresh local repo)."""
    ids = _seed_remote_repo(vaults.remote)  # remote repo with commit bbbb2222, docs, etc.

    ldb = vaults.local()
    local_repo = Repository(name="Local", remote_url="http://remote.test", remote_repo_id=ids.repo_id)
    ldb.add(local_repo)
    ldb.commit()
    local_id = local_repo.id
    ldb.close()

    r = vaults.client.post(f"/sync/pull/{local_id}")
    assert r.status_code == 200, r.text
    assert r.json()["pulled"] == 1

    ldb = vaults.local()
    assert ldb.query(Commit).filter(Commit.short_hash == "bbbb2222").one().repository_id == local_id
    assert ldb.get(Document, ids.assembly_id).repository_id == local_id
    ldb.close()


def test_remote_repos_endpoint_lists_remote(vaults, monkeypatch):
    """The link picker endpoint returns the remote vault's repos."""
    from app.vault_client import VaultClient
    monkeypatch.setattr(VaultClient, "health", lambda self: "ok")  # health() bypasses the test _get
    _seed_remote_repo(vaults.remote)  # creates remote repo "Gearbox"

    r = vaults.client.get("/sync/remote-repos?remote_url=http://remote.test")
    assert r.status_code == 200, r.text
    assert "Gearbox" in [x["name"] for x in r.json()]


def test_pull_flattens_branch_id(vaults):
    """Pulled commits are stored flat (branch_id=None). Branches are local-only,
    so the remote's branch rows don't exist here — copying branch_id through
    would violate commits_branch_id_fkey (caught while clone-testing a remote
    repo whose commits carried a branch_id)."""
    from app.models.branch import Branch
    rdb = vaults.remote()
    repo = Repository(name="Branchy")
    rdb.add(repo)
    rdb.flush()
    branch = Branch(repository_id=repo.id, name="feature/x", created_by="a")
    rdb.add(branch)
    rdb.flush()
    rdb.add(Commit(repository_id=repo.id, branch_id=branch.id, author="a", message="m",
                   short_hash="brnch001", is_local=False, protocol_violations=[]))
    rdb.commit()
    remote_id = repo.id
    rdb.close()

    ldb = vaults.local()
    local_repo = Repository(name="Branchy-local", remote_url="http://remote.test", remote_repo_id=remote_id)
    ldb.add(local_repo)
    ldb.commit()
    local_id = local_repo.id
    ldb.close()

    r = vaults.client.post(f"/sync/pull/{local_id}")
    assert r.status_code == 200, r.text
    assert r.json()["pulled"] == 1

    ldb = vaults.local()
    c = ldb.query(Commit).filter(Commit.short_hash == "brnch001").one()
    assert c.branch_id is None        # flattened, no FK violation
    assert c.repository_id == local_id
    ldb.close()


# ── drawing-approval gate (Phase B) ───────────────────────────────────────────
# These swap the get_current_user override mid-test to act as a non-approver.
from app.main import app                         # noqa: E402
from app.security import get_current_user        # noqa: E402
from app.models.user import User                 # noqa: E402


def _member():
    """A logged-in user WITHOUT the approve_drawing privilege."""
    u = User(id=uuid.uuid4(), email="eng@local", role="member", is_active=True)
    u.privileges = []
    return u


def test_push_blocked_until_drawing_approved(vaults):
    ids = _seed_local_repo(vaults.local)
    app.dependency_overrides[get_current_user] = _member        # non-approver
    r = vaults.client.post(f"/sync/push/{ids.repo_id}")
    assert r.status_code == 422
    assert "GB-100" in r.json()["detail"]                       # names the unapproved drawing


def test_approve_endpoint_stamps_and_push_carries_approver(vaults):
    ids = _seed_local_repo(vaults.local)
    a = vaults.client.post(f"/repos/{ids.repo_id}/documents/{ids.doc_id}/approve")
    assert a.status_code == 200
    assert a.json()["approved"] is True and a.json()["approved_by"] == "test@local"

    assert vaults.client.post(f"/sync/push/{ids.repo_id}").status_code == 200
    rdb = vaults.remote()
    cf = rdb.query(CommitFile).first()
    assert cf.approved_by == "test@local" and cf.approved_by_id is not None   # persisted on the remote
    rdb.close()


def test_member_can_push_after_checker_approves(vaults):
    ids = _seed_local_repo(vaults.local)
    vaults.client.post(f"/repos/{ids.repo_id}/documents/{ids.doc_id}/approve")  # admin/checker signs off
    app.dependency_overrides[get_current_user] = _member                        # member pushes
    assert vaults.client.post(f"/sync/push/{ids.repo_id}").status_code == 200


def test_member_cannot_approve(vaults):
    ids = _seed_local_repo(vaults.local)
    app.dependency_overrides[get_current_user] = _member
    r = vaults.client.post(f"/repos/{ids.repo_id}/documents/{ids.doc_id}/approve")
    assert r.status_code == 403

"""
Two-vault end-to-end test harness.

Vault sync involves two FastAPI apps talking over HTTP: a local vault
(VAULT_MODE=local) running push/pull, and a remote vault (VAULT_MODE=remote)
running snapshot/receive_commits. Both live in the same module and read a
single process-global ``settings.VAULT_MODE``, so we simulate the pair in one
process:

  * two SQLite databases (local + remote) stand in for the two Postgres DBs
  * ``get_db`` is overridden to yield from whichever DB is currently "active"
  * ``VaultClient``'s HTTP calls are routed to an in-process TestClient, with
    the active DB + VAULT_MODE flipped to "remote" for the duration of the call

This exercises the real serialization boundary — the local code builds JSON via
VaultClient, the remote validates it through the PushPayload Pydantic model —
which is where the diff_report_patches field-drop bug lived. A push or pull that
NameErrors or drops a payload field fails these tests.
"""
import contextlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config
from app.database import get_db
from app.main import app
from app.models import Base
from app.models.role import Role
from app.models.user import User, ROLE_ADMIN, ROLE_MEMBER
from app.authz import PRIVILEGES
from app.security import get_current_user
from app.vault_client import RemoteRepoNotFoundError, VaultClient

# stable id so the fake admin that overrides get_current_user matches a real row
# seeded in each vault DB — needed now that push auto-approves drawings in the
# pusher's name and the remote validates the approver against its user table.
FAKE_ADMIN_ID = uuid.uuid4()


def _make_db():
    """A fresh in-memory SQLite DB, seeded with the built-in roles + the fake
    admin user that the e2e tests authenticate as. StaticPool keeps the one
    connection alive so every session in the test sees the same in-memory data."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, expire_on_commit=False)
    db = sm()
    db.add(Role(name=ROLE_ADMIN, privileges=list(PRIVILEGES), is_builtin=True))
    db.add(Role(name=ROLE_MEMBER, privileges=[], is_builtin=True))
    db.add(User(id=FAKE_ADMIN_ID, email="test@local", hashed_password="x",
                role=ROLE_ADMIN, is_active=True))
    db.commit()
    db.close()
    return sm


@pytest.fixture
def vaults(monkeypatch):
    local_sm = _make_db()
    remote_sm = _make_db()
    active = {"sm": local_sm}

    def override_get_db():
        db = active["sm"]()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Every data endpoint now requires a logged-in user. These e2e tests predate
    # auth and exercise the sync/data paths, not the login path, so we bypass the
    # real token check with a fake admin (admin == superset of member access).
    # The dedicated auth tests (test_auth.py) run the real security path instead.
    def _fake_admin():
        u = User(id=FAKE_ADMIN_ID, email="test@local", role=ROLE_ADMIN, is_active=True)
        u.privileges = list(PRIVILEGES)  # full catalog so any privilege gate passes
        return u
    app.dependency_overrides[get_current_user] = _fake_admin
    client = TestClient(app)

    @contextlib.contextmanager
    def remote_ctx():
        """While active, requests resolve against the remote DB in remote mode —
        this is what a VaultClient HTTP call to the remote vault sees."""
        prev_sm, prev_mode = active["sm"], config.settings.VAULT_MODE
        active["sm"] = remote_sm
        config.settings.VAULT_MODE = "remote"
        try:
            yield
        finally:
            active["sm"] = prev_sm
            config.settings.VAULT_MODE = prev_mode

    def fake_get(self, path, raise_on_404=False, **kwargs):
        with remote_ctx():
            resp = client.get(path, params=kwargs.get("params"))
        if resp.status_code == 404 and raise_on_404:
            raise RemoteRepoNotFoundError(resp.json().get("detail", "Not found"))
        resp.raise_for_status()
        return resp.json()

    def fake_post(self, path, json=None, **kwargs):
        with remote_ctx():
            resp = client.post(path, json=json)
        resp.raise_for_status()
        return resp.json()

    monkeypatch.setattr(VaultClient, "_get", fake_get)
    monkeypatch.setattr(VaultClient, "_post", fake_post)
    # push/pull copy PDF bytes across vault prefixes; stub it so e2e tests that
    # seed fake S3 keys don't reach real S3
    monkeypatch.setattr("app.storage.copy_from_peer", lambda *a, **k: True)

    prev_mode = config.settings.VAULT_MODE
    config.settings.VAULT_MODE = "local"
    try:
        yield SimpleNamespace(client=client, local=local_sm, remote=remote_sm)
    finally:
        config.settings.VAULT_MODE = prev_mode
        app.dependency_overrides.clear()

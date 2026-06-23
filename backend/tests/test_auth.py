"""Authentication + user-management tests — exercise the REAL security path
(password hashing, JWT signing/verifying, role gating), unlike the e2e tests
which bypass auth with a fake user.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config
from app.authz import PRIVILEGES
from app.database import get_db
from app.main import app
from app.models import Base
from app.models.role import Role
from app.models.user import User, ROLE_ADMIN, ROLE_MEMBER
from app.security import hash_password


def _seed_builtin_roles(sm):
    """Migrations don't run in tests (tables come from Base.metadata), so seed the
    built-in roles the same way migration 0010 does."""
    db = sm()
    db.add(Role(name=ROLE_ADMIN, privileges=list(PRIVILEGES), is_builtin=True))
    db.add(Role(name=ROLE_MEMBER, privileges=[], is_builtin=True))
    db.commit()
    db.close()


@pytest.fixture
def client(monkeypatch):
    """A TestClient backed by a fresh in-memory DB, running as the REMOTE vault —
    the authoritative user store. Only get_db is overridden, so the real
    get_current_user / JWT / token_version logic runs against the DB (a local
    vault would instead delegate to a remote, tested separately below)."""
    monkeypatch.setattr(config.settings, "VAULT_MODE", "remote")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, expire_on_commit=False)
    _seed_builtin_roles(sm)

    def override_get_db():
        db = sm()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app)
    c.sm = sm  # expose the session factory so tests can seed users directly
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


def _seed_user(sm, email, password="password123", role=ROLE_MEMBER, active=True):
    db = sm()
    u = User(email=email, hashed_password=hash_password(password), role=role, is_active=active)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── signup ──────────────────────────────────────────────────────────────────

def test_signup_creates_member_and_returns_token(client):
    r = client.post("/auth/signup", json={"email": "Bob@Factory.com", "password": "hunter2hunter"})
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "bob@factory.com"   # normalized to lowercase
    assert body["user"]["role"] == ROLE_MEMBER           # self-signup is never admin


def test_signup_duplicate_email_conflicts(client):
    client.post("/auth/signup", json={"email": "a@b.com", "password": "password123"})
    r = client.post("/auth/signup", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 409


def test_signup_rejects_short_password(client):
    r = client.post("/auth/signup", json={"email": "a@b.com", "password": "short"})
    assert r.status_code == 422


# ── login ─────────────────────────────────────────────────────────────────────

def test_login_success(client):
    _seed_user(client.sm, "eng@factory.com", "correcthorse")
    r = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_wrong_password_is_401(client):
    _seed_user(client.sm, "eng@factory.com", "correcthorse")
    r = client.post("/auth/login", json={"email": "eng@factory.com", "password": "nope"})
    assert r.status_code == 401


def test_login_unknown_email_is_401(client):
    r = client.post("/auth/login", json={"email": "ghost@factory.com", "password": "whatever12"})
    assert r.status_code == 401


def test_login_deactivated_account_is_403(client):
    _seed_user(client.sm, "old@factory.com", "correcthorse", active=False)
    r = client.post("/auth/login", json={"email": "old@factory.com", "password": "correcthorse"})
    assert r.status_code == 403


# ── the token gate ──────────────────────────────────────────────────────────

def test_protected_endpoint_requires_token(client):
    assert client.get("/repos/").status_code == 401


def test_protected_endpoint_with_valid_token(client):
    _seed_user(client.sm, "eng@factory.com", "correcthorse")
    token = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()[
        "access_token"]
    r = client.get("/repos/", headers=_auth(token))
    assert r.status_code == 200


def test_garbage_token_is_401(client):
    assert client.get("/repos/", headers=_auth("not.a.jwt")).status_code == 401


def test_me_returns_current_user(client):
    _seed_user(client.sm, "eng@factory.com", "correcthorse")
    token = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()[
        "access_token"]
    r = client.get("/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["email"] == "eng@factory.com"


# ── admin user management ─────────────────────────────────────────────────────

def _admin_token(client):
    _seed_user(client.sm, "boss@factory.com", "adminpass123", role=ROLE_ADMIN)
    r = client.post("/auth/login", json={"email": "boss@factory.com", "password": "adminpass123"})
    return r.json()["access_token"]


def test_member_cannot_list_users(client):
    _seed_user(client.sm, "eng@factory.com", "correcthorse")
    token = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()[
        "access_token"]
    assert client.get("/users", headers=_auth(token)).status_code == 403


def test_admin_can_list_and_create_users(client):
    token = _admin_token(client)
    assert client.get("/users", headers=_auth(token)).status_code == 200
    r = client.post("/users", headers=_auth(token),
                    json={"email": "new@factory.com", "password": "password123", "role": "member"})
    assert r.status_code == 201
    assert r.json()["email"] == "new@factory.com"


def test_admin_can_grant_admin_role(client):
    token = _admin_token(client)
    target = _seed_user(client.sm, "eng@factory.com", "correcthorse")
    r = client.patch(f"/users/{target.id}", headers=_auth(token), json={"role": "admin"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_cannot_remove_last_admin(client):
    token = _admin_token(client)
    # boss is the only admin — demoting via the list lookup must be blocked
    me = client.get("/auth/me", headers=_auth(token)).json()
    r = client.patch(f"/users/{me['id']}", headers=_auth(token), json={"is_active": False})
    assert r.status_code == 400


# ── token reset on permission change (token_version) ──────────────────────────

def test_role_change_invalidates_existing_token(client):
    """The heart of 'log out on role change': after an admin edits a user's role,
    that user's already-issued token must stop working (forces re-login)."""
    admin = _admin_token(client)
    target = _seed_user(client.sm, "eng@factory.com", "correcthorse")
    user_token = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()[
        "access_token"]

    # token works before the change
    assert client.get("/auth/me", headers=_auth(user_token)).status_code == 200

    # admin promotes them -> token_version bumps -> old token is now stale
    assert client.patch(f"/users/{target.id}", headers=_auth(admin), json={"role": "admin"}).status_code == 200
    assert client.get("/auth/me", headers=_auth(user_token)).status_code == 401

    # logging in again issues a token at the new version, which works
    fresh = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()[
        "access_token"]
    assert client.get("/auth/me", headers=_auth(fresh)).status_code == 200


def test_deactivation_invalidates_existing_token(client):
    admin = _admin_token(client)
    target = _seed_user(client.sm, "eng@factory.com", "correcthorse")
    user_token = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()[
        "access_token"]
    assert client.get("/repos/", headers=_auth(user_token)).status_code == 200
    client.patch(f"/users/{target.id}", headers=_auth(admin), json={"is_active": False})
    assert client.get("/repos/", headers=_auth(user_token)).status_code == 401


# ── roles & privileges (RBAC) ─────────────────────────────────────────────────

def _member_token(client, email="eng@factory.com", pw="correcthorse"):
    _seed_user(client.sm, email, pw, role=ROLE_MEMBER)
    return client.post("/auth/login", json={"email": email, "password": pw}).json()["access_token"]


def test_me_includes_privileges(client):
    me = client.get("/auth/me", headers=_auth(_admin_token(client))).json()
    assert "manage_users" in me["privileges"] and "manage_roles" in me["privileges"]


def test_member_can_list_but_not_manage_roles(client):
    token = _member_token(client)
    assert client.get("/roles", headers=_auth(token)).status_code == 200  # listing is open
    r = client.post("/roles", headers=_auth(token), json={"name": "checker", "privileges": ["approve_drawing"]})
    assert r.status_code == 403


def test_admin_can_create_and_list_roles(client):
    token = _admin_token(client)
    r = client.post("/roles", headers=_auth(token), json={"name": "Checker", "privileges": ["approve_drawing"]})
    assert r.status_code == 201
    assert r.json()["name"] == "checker"  # normalized
    assert r.json()["privileges"] == ["approve_drawing"] and r.json()["is_builtin"] is False
    names = [x["name"] for x in client.get("/roles", headers=_auth(token)).json()]
    assert "checker" in names and "admin" in names and "member" in names


def test_create_role_rejects_unknown_privilege(client):
    r = client.post("/roles", headers=_auth(_admin_token(client)), json={"name": "x", "privileges": ["fly"]})
    assert r.status_code == 422


def test_builtin_roles_are_immutable(client):
    token = _admin_token(client)
    admin_role = next(r for r in client.get("/roles", headers=_auth(token)).json() if r["name"] == "admin")
    assert client.put(f"/roles/{admin_role['id']}", headers=_auth(token), json={"privileges": []}).status_code == 400
    assert client.delete(f"/roles/{admin_role['id']}", headers=_auth(token)).status_code == 400


def test_assigning_custom_role_grants_its_privileges(client):
    admin = _admin_token(client)
    client.post("/roles", headers=_auth(admin), json={"name": "checker", "privileges": ["approve_drawing"]})
    target = _seed_user(client.sm, "eng@factory.com", "correcthorse")
    assert client.patch(f"/users/{target.id}", headers=_auth(admin), json={"role": "checker"}).status_code == 200
    t = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()["access_token"]
    assert client.get("/auth/me", headers=_auth(t)).json()["privileges"] == ["approve_drawing"]


def test_assign_unknown_role_rejected(client):
    admin = _admin_token(client)
    target = _seed_user(client.sm, "eng@factory.com", "correcthorse")
    assert client.patch(f"/users/{target.id}", headers=_auth(admin), json={"role": "ghost"}).status_code == 400


def test_delete_role_in_use_is_blocked(client):
    admin = _admin_token(client)
    rid = client.post("/roles", headers=_auth(admin),
                      json={"name": "checker", "privileges": ["approve_drawing"]}).json()["id"]
    target = _seed_user(client.sm, "eng@factory.com", "correcthorse")
    client.patch(f"/users/{target.id}", headers=_auth(admin), json={"role": "checker"})
    assert client.delete(f"/roles/{rid}", headers=_auth(admin)).status_code == 400   # in use
    client.patch(f"/users/{target.id}", headers=_auth(admin), json={"role": "member"})
    assert client.delete(f"/roles/{rid}", headers=_auth(admin)).status_code == 204   # now free


# ── local vault delegates auth to the remote ──────────────────────────────────

@pytest.fixture
def local_client(monkeypatch):
    """A TestClient running as a LOCAL vault: it owns no users and delegates auth
    to the remote. get_db is still overridden with an empty DB because FastAPI
    resolves the get_db dependency even on endpoints that return early."""
    monkeypatch.setattr(config.settings, "VAULT_MODE", "local")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = sm()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_local_vault_delegates_validation_to_remote(local_client, monkeypatch):
    """In local mode the vault owns no users — get_current_user must resolve the
    token by calling the remote vault (app.remote_auth.validate_token)."""
    fake_user = {
        "id": str(uuid.uuid4()), "email": "eng@factory.com", "full_name": None,
        "role": "member", "is_active": True, "created_at": "2026-06-21T00:00:00",
    }
    calls = {"n": 0}

    def fake_validate(token):
        calls["n"] += 1
        if token == "good":
            return fake_user
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="bad token")

    monkeypatch.setattr("app.remote_auth.validate_token", fake_validate)
    assert local_client.get("/repos/", headers=_auth("good")).status_code == 200
    assert local_client.get("/repos/", headers=_auth("nope")).status_code == 401
    assert calls["n"] >= 2  # the local vault really did delegate


def test_local_vault_proxies_login_to_remote(local_client, monkeypatch):
    captured = {}

    def fake_remote_request(method, path, token=None, json=None):
        captured["call"] = (method, path)
        return {"access_token": "remote-token", "token_type": "bearer", "user": {
            "id": str(uuid.uuid4()), "email": json["email"], "full_name": None,
            "role": "member", "is_active": True, "created_at": "2026-06-21T00:00:00",
        }}

    monkeypatch.setattr("app.remote_auth.remote_request", fake_remote_request)
    r = local_client.post("/auth/login", json={"email": "eng@factory.com", "password": "whatever12"})
    assert r.status_code == 200
    assert r.json()["access_token"] == "remote-token"
    assert captured["call"] == ("POST", "/auth/login")

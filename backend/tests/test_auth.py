"""Authentication + user-management tests — exercise the REAL security path
(password hashing, JWT signing/verifying, role gating), unlike the e2e tests
which bypass auth with a fake user.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Base
from app.models.user import User, ROLE_ADMIN, ROLE_MEMBER
from app.security import hash_password


@pytest.fixture
def client():
    """A TestClient backed by a fresh in-memory DB. Only get_db is overridden,
    so the real get_current_user/JWT logic runs — this is the whole point."""
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
    token = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()["access_token"]
    r = client.get("/repos/", headers=_auth(token))
    assert r.status_code == 200


def test_garbage_token_is_401(client):
    assert client.get("/repos/", headers=_auth("not.a.jwt")).status_code == 401


def test_me_returns_current_user(client):
    _seed_user(client.sm, "eng@factory.com", "correcthorse")
    token = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()["access_token"]
    r = client.get("/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["email"] == "eng@factory.com"


# ── admin user management ─────────────────────────────────────────────────────

def _admin_token(client):
    _seed_user(client.sm, "boss@factory.com", "adminpass123", role=ROLE_ADMIN)
    return client.post("/auth/login", json={"email": "boss@factory.com", "password": "adminpass123"}).json()["access_token"]


def test_member_cannot_list_users(client):
    _seed_user(client.sm, "eng@factory.com", "correcthorse")
    token = client.post("/auth/login", json={"email": "eng@factory.com", "password": "correcthorse"}).json()["access_token"]
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

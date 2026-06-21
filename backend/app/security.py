"""Authentication primitives: password hashing, JWT tokens, and the FastAPI
dependencies that protect endpoints.

The flow:
  1. signup  -> hash_password() stores a one-way bcrypt hash, never the plaintext
  2. login   -> verify_password() checks the typed password against the hash,
                then create_access_token() returns a signed JWT "wristband"
  3. request -> get_current_user() reads the JWT from the Authorization header,
                verifies the signature, and loads the matching user row
"""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User

# bcrypt only hashes the first 72 bytes of a password; longer inputs raise in
# bcrypt 4.x. We truncate defensively so a long passphrase never 500s.
_BCRYPT_MAX_BYTES = 72

# tells FastAPI to expect "Authorization: Bearer <token>" and adds the Authorize
# button in the /docs UI. auto_error=False so we can raise our own 401 message.
_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    """Turn a plaintext password into a salted bcrypt hash for storage."""
    pw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a typed password against the stored hash. Never throws on bad input."""
    try:
        pw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    """Mint a signed JWT identifying the user. 'sub' (subject) carries the user
    id; 'exp' (expiry) lets the server reject stale tokens without a DB lookup."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        # the permission epoch this token was minted at — bumped on role change /
        # deactivation so stale tokens can be rejected (see get_current_user).
        "ver": user.token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# raised when a token is missing/invalid — sent back as HTTP 401
_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _user_from_remote(data: dict) -> User:
    """Build a throwaway (non-persisted) User from the remote vault's /auth/me
    response. Carries just enough for require_admin and the response model; it is
    never added to a session."""
    created = data.get("created_at")
    return User(
        id=uuid.UUID(data["id"]),
        email=data["email"],
        full_name=data.get("full_name"),
        role=data["role"],
        is_active=data["is_active"],
        created_at=datetime.fromisoformat(created) if isinstance(created, str) else created,
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the logged-in user from the Bearer token, or 401.

    The REMOTE vault owns the user table and validates authoritatively against
    its DB. A LOCAL vault has no user accounts of its own, so it delegates to the
    remote vault (see app.remote_auth) — that's what makes one account work on
    both vaults."""
    if creds is None:
        raise _credentials_error

    if settings.VAULT_MODE != "remote":
        # local vault: ask the authority (remote) who this token belongs to.
        from app import remote_auth  # local import avoids an import cycle
        return _user_from_remote(remote_auth.validate_token(creds.credentials))

    # remote vault: verify the signature/expiry, then check the live DB record.
    try:
        payload = jwt.decode(
            creds.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _credentials_error

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise _credentials_error
    # reject tokens minted before the user's permissions last changed — this is
    # what logs a user out after an admin edits their role or deactivates them.
    if payload.get("ver") != user.token_version:
        raise _credentials_error
    return user


def require_admin(current: User = Depends(get_current_user)) -> User:
    """Dependency for admin-only endpoints. Reuses get_current_user, then checks
    the role — a logged-in member gets 403 (authenticated but not allowed)."""
    if not current.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current

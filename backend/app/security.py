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


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the logged-in user from the Bearer token, or 401.

    This is the gate every protected endpoint passes through. It (a) checks a
    token was sent, (b) verifies the signature + expiry, (c) loads the user, and
    (d) confirms the account is still active."""
    if creds is None:
        raise _credentials_error
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

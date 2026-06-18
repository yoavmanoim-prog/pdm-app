from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, ROLE_MEMBER
from app.schemas.users import UserSignup, UserLogin, UserResponse, TokenResponse
from app.security import hash_password, verify_password, create_access_token, get_current_user

# all routes here are prefixed with /auth
router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(user: User) -> TokenResponse:
    """Shared helper: wrap a user + a freshly signed JWT into the login response."""
    return TokenResponse(access_token=create_access_token(user), user=UserResponse.model_validate(user))


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: UserSignup, db: Session = Depends(get_db)):
    """Public self-registration. New accounts are always plain 'member' role —
    only an existing admin can grant the admin role afterwards. On success we log
    the user straight in by returning a token, so they don't re-type credentials."""
    exists = db.query(User).filter(User.email == body.email).first()
    if exists:
        # 409 Conflict — the email is already taken
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=ROLE_MEMBER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    """Exchange email + password for a token. We return the SAME 401 whether the
    email is unknown or the password is wrong — revealing which one leaks whether
    an account exists."""
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    return _issue_token(user)


@router.get("/me", response_model=UserResponse)
def me(current: User = Depends(get_current_user)):
    """Who am I? The frontend calls this on load to restore the session from a
    stored token and to know whether to show admin-only UI."""
    return current

"""Startup admin bootstrap.

A fresh database has no users, and only an admin can create the first admin —
a chicken-and-egg problem. To break it, set BOOTSTRAP_ADMIN_EMAIL and
BOOTSTRAP_ADMIN_PASSWORD: on startup, if no admin exists yet, we create one (or
promote the matching email). Once an admin exists this is a no-op, so it's safe
to leave the env vars set across restarts.
"""
import logging

from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import session_scope
from app.models.user import User, ROLE_ADMIN
from app.security import hash_password

log = logging.getLogger("uvicorn.error")


def ensure_bootstrap_admin() -> None:
    email = settings.BOOTSTRAP_ADMIN_EMAIL.strip().lower()
    password = settings.BOOTSTRAP_ADMIN_PASSWORD
    if not email or not password:
        return  # bootstrap disabled

    # This runs in EVERY backend pod's startup, so several replicas can execute
    # it at once. The "no admin yet" check is best-effort; the unique email
    # constraint is the real guard. If a racing pod inserts first, our commit
    # raises IntegrityError — we treat that as "already done", not a fatal error,
    # so startup never crashloops on a bootstrap race.
    try:
        with session_scope() as db:
            # already have an admin? then nothing to do — never overwrite live state
            if db.query(User).filter(User.role == ROLE_ADMIN).first():
                return

            existing = db.query(User).filter(User.email == email).first()
            if existing:
                existing.role = ROLE_ADMIN
                existing.is_active = True
                log.info("Bootstrap: promoted existing user %s to admin", email)
            else:
                db.add(User(
                    email=email,
                    full_name="Bootstrap Admin",
                    hashed_password=hash_password(password),
                    role=ROLE_ADMIN,
                    is_active=True,
                ))
                log.info("Bootstrap: created admin %s", email)
    except IntegrityError:
        # another replica won the race and created the same admin — fine.
        log.info("Bootstrap: admin already created by another instance")

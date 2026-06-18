from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from app.config import settings
from app.database import init_db
from app.security import get_current_user
from app.bootstrap import ensure_bootstrap_admin
from app.routers import (
    repositories, documents, commits, branches, tree,
    sync, vault_incoming, revisions, revision_requests, audit, watch,
    auth, users,
)

# every endpoint behind this gate requires a valid login token. Declared once so
# all data routers share the exact same dependency object — which is also what
# the test suite overrides to inject a fake user.
_auth = [Depends(get_current_user)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # runs once at startup — initialises the database connection pool
    # this is why we never read DATABASE_URL at import time
    init_db(settings.DATABASE_URL)
    # seed the first admin if configured and none exists yet (no-op otherwise)
    ensure_bootstrap_admin()
    yield
    # anything after yield runs at shutdown (cleanup if needed)


app = FastAPI(
    title="PDM Vault",
    description="Git-like Product Data Management for engineering schematics",
    version="2.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# allow the local frontend (localhost:3000) to call the remote vault cross-origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# expose GET /metrics — Prometheus scrapes this endpoint every 15 s
# instruments every request automatically: count, latency histogram, status codes
Instrumentator().instrument(app).expose(app)

# --- public routers (no login required) ---
# auth endpoints are how you GET a token, so they can't require one themselves.
app.include_router(auth.router)
# vault_incoming is the machine-to-machine endpoint another vault server pushes
# to over HTTP — it is NOT called by a logged-in user, so a user JWT can't apply
# here. It stays open (as before); securing vault-to-vault traffic is a separate
# concern (shared secret / mTLS) tracked outside this change.
app.include_router(vault_incoming.router)
# watch serves the engineer's LOCAL filesystem (folder picker + PDF preview).
# browseWatch uses a header-less fetch and preview is shown via an <iframe src>,
# neither of which can carry a Bearer token — protecting it would break those
# features. It only ever targets the local (localhost) vault, so it stays open.
app.include_router(watch.router)

# --- protected routers (valid login token required) ---
# every user-facing data endpoint passes through get_current_user via _auth.
app.include_router(users.router)                       # admin-only (guarded inside the router too)
app.include_router(repositories.router, dependencies=_auth)
app.include_router(documents.router, dependencies=_auth)
app.include_router(commits.router, dependencies=_auth)
app.include_router(branches.router, dependencies=_auth)
app.include_router(tree.router, dependencies=_auth)
app.include_router(sync.router, dependencies=_auth)
app.include_router(revisions.router, dependencies=_auth)
app.include_router(revision_requests.router, dependencies=_auth)
app.include_router(audit.router, dependencies=_auth)


@app.get("/")
def root():
    return {
        "status": "ok",
        "app": "PDM Vault",
        "vault_mode": settings.VAULT_MODE,
    }


@app.get("/health")
def health():
    # lightweight probe — does NOT check the database
    # Kubernetes uses this for liveness and readiness checks
    return {"healthy": True, "vault_mode": settings.VAULT_MODE}

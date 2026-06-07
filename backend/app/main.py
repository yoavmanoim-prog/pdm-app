from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.database import init_db
from app.routers import repositories, documents, commits


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # runs once at startup — initialises the database connection pool
    # this is why we never read DATABASE_URL at import time
    init_db(settings.DATABASE_URL)
    yield
    # anything after yield runs at shutdown (cleanup if needed)


app = FastAPI(
    title="PDM Vault",
    description="Git-like Product Data Management for engineering schematics",
    version="2.0.0",
    lifespan=lifespan,
)

# register all routers — each router handles a group of related endpoints
app.include_router(repositories.router)
app.include_router(documents.router)
app.include_router(commits.router)


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

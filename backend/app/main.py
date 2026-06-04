import os
from fastapi import FastAPI

# Read vault mode at startup — "local" (engineer's workspace) or "remote" (shared server)
# Defaults to "local" so the app works without any env vars set
VAULT_MODE = os.getenv("VAULT_MODE", "local")

app = FastAPI(
    title="PDM Vault",
    description="Git-like Product Data Management system for engineering schematics",
    version="2.0.0",
)


@app.get("/")
def root():
    # Basic status check — shows which vault mode this instance is running as
    return {
        "status": "ok",
        "app": "PDM Vault",
        "vault_mode": VAULT_MODE,
    }


@app.get("/health")
def health():
    # Kubernetes uses this endpoint for liveness and readiness probes
    # Intentionally does NOT check the database — the probe should be lightweight
    return {"healthy": True, "vault_mode": VAULT_MODE}

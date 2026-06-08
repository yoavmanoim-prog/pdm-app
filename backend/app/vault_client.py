import httpx
from app.config import settings


class VaultClient:
    """HTTP client for local vault → remote vault communication."""

    def __init__(self):
        self.base_url = settings.REMOTE_VAULT_URL.rstrip("/")

    def _get(self, path: str, **kwargs):
        resp = httpx.get(f"{self.base_url}{path}", timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json=None, **kwargs):
        resp = httpx.post(f"{self.base_url}{path}", json=json, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def ping(self) -> bool:
        """Check if the remote vault is reachable."""
        try:
            data = self._get("/health")
            return data.get("healthy", False)
        except Exception:
            return False

    def push_commits(self, commits: list[dict], repository: dict = None, documents: list = None) -> dict:
        """Send local commits (plus repo/document metadata) to the remote vault."""
        return self._post("/vault/incoming/commits", json={
            "commits": commits,
            "repository": repository,
            "documents": documents or [],
        })

    def pull_commits(self, repo_id: str, since_hash: str | None = None) -> list[dict]:
        """Fetch commits from the remote vault that the local vault doesn't have."""
        params = {"repo_id": repo_id}
        if since_hash:
            params["since_hash"] = since_hash
        return self._get("/vault/commits", params=params)

    def publish_revision(self, payload: dict) -> dict:
        """Ask the remote vault to publish a formal revision."""
        return self._post("/vault/revisions/publish", json=payload)

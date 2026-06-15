import httpx
from app.config import settings


class RemoteRepoNotFoundError(Exception):
    """Raised when the remote vault returns 404 for a repository."""


class VaultClient:
    """HTTP client for local vault → remote vault communication."""

    def __init__(self, remote_url: str | None = None):
        # per-repo remote_url takes priority over the global env var
        url = remote_url or settings.REMOTE_VAULT_URL
        self.base_url = url.rstrip("/")

    def _get(self, path: str, raise_on_404: bool = False, **kwargs):
        resp = httpx.get(f"{self.base_url}{path}", timeout=30, **kwargs)
        if resp.status_code == 404 and raise_on_404:
            raise RemoteRepoNotFoundError(resp.json().get("detail", "Not found"))
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json=None, **kwargs):
        resp = httpx.post(f"{self.base_url}{path}", json=json, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def health(self) -> str:
        """Probe the remote /health endpoint.

        Returns one of:
          "ok"            — a healthy vault answered
          "misconfigured" — something answered but it isn't a vault health
                            endpoint (e.g. the URL is missing /api and we hit
                            the frontend, which returns HTML, not JSON)
          "unreachable"   — the connection itself failed
        """
        try:
            resp = httpx.get(f"{self.base_url}/health", timeout=10)
        except Exception:
            return "unreachable"
        try:
            data = resp.json()
        except Exception:
            return "misconfigured"
        if isinstance(data, dict) and data.get("healthy"):
            return "ok"
        return "misconfigured"

    def ping(self) -> bool:
        """True only if a healthy vault answered."""
        return self.health() == "ok"

    def push_commits(self, commits: list[dict], repository: dict = None,
                     documents: list = None, bom_entries: list = None,
                     diff_report_patches: list = None) -> dict:
        """Send local commits (plus repo/document/BOM metadata) to the remote vault."""
        return self._post("/vault/incoming/commits", json={
            "commits": commits,
            "repository": repository,
            "documents": documents or [],
            "bom_entries": bom_entries or [],
            "diff_report_patches": diff_report_patches or [],
        })

    def pull_snapshot(self, repo_id: str, since_hash: str | None = None) -> dict:
        """Fetch commits, documents, BOM entries, and revisions from the remote vault."""
        params = {}
        if since_hash:
            params["since_hash"] = since_hash
        return self._get(f"/vault/snapshot/{repo_id}", raise_on_404=True, params=params)

    def pull_commits(self, repo_id: str, since_hash: str | None = None) -> list[dict]:
        """Fetch commits from the remote vault (backwards-compatible, used by sync_status)."""
        params = {"repo_id": repo_id}
        if since_hash:
            params["since_hash"] = since_hash
        return self._get("/vault/commits", params=params)

    def publish_revision(self, payload: dict) -> dict:
        """Ask the remote vault to publish a formal revision."""
        return self._post("/vault/revisions/publish", json=payload)

"""Local vault -> remote vault identity bridge.

Users live in ONE place: the remote vault's database. When this process runs as
a LOCAL vault it owns no user accounts, so it forwards auth/user operations to
the remote vault and validates incoming tokens by asking the remote "who is
this?" (GET /auth/me). A short cache keeps that from being a round-trip on every
single request while still letting role/deactivation changes take effect fast.
"""
import time

import httpx
from fastapi import HTTPException, status

from app.config import settings

# token -> (expires_at, user_dict). Validation results only; cleared by TTL.
_validation_cache: dict[str, tuple[float, dict]] = {}
_CACHE_MAX = 2048  # safety cap so a flood of distinct tokens can't grow forever


def _remote_base() -> str:
    return settings.REMOTE_VAULT_URL.rstrip("/")


def remote_request(method: str, path: str, token: str | None = None, json=None) -> dict | None:
    """Call the remote vault and mirror its result. On a 4xx we re-raise the
    remote's status + detail so the frontend sees the real error (e.g. a 401 for
    bad credentials, a 409 for a duplicate email). On a transport failure we
    surface 503 — the identity service is simply unreachable."""
    headers = {"Authorization": f"Bearer {token}"} if token else None
    try:
        resp = httpx.request(method, f"{_remote_base()}{path}", json=json, headers=headers, timeout=30)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity service (remote vault) is unreachable",
        )
    if resp.status_code >= 400:
        # forward the remote's error; fall back to its text if it wasn't JSON
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text or "remote vault error"
        raise HTTPException(status_code=resp.status_code, detail=detail)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


def validate_token(token: str) -> dict:
    """Resolve a token to the current user via the remote vault, cached briefly.
    Raises 401 (propagated from the remote) if the token is invalid/expired or
    the account was deactivated or its permissions changed."""
    now = time.time()
    hit = _validation_cache.get(token)
    if hit and hit[0] > now:
        return hit[1]

    # GET /auth/me on the remote runs the authoritative check (signature, expiry,
    # token_version, is_active) and returns the live user record.
    user = remote_request("GET", "/auth/me", token=token)

    if len(_validation_cache) >= _CACHE_MAX:
        # cheap prune: drop everything expired, then hard-reset if still full
        for k in [k for k, (exp, _) in _validation_cache.items() if exp <= now]:
            _validation_cache.pop(k, None)
        if len(_validation_cache) >= _CACHE_MAX:
            _validation_cache.clear()
    _validation_cache[token] = (now + settings.AUTH_REMOTE_CACHE_TTL, user)
    return user

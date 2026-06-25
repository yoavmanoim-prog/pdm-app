"""
On-site (AWS-free) filesystem storage backend.

This module is a drop-in replacement for ``app.storage``. It exposes the exact
same public functions (``upload_file``, ``download_file``, ``generate_presigned_url``,
``presigned_url_if_exists``, ``copy_from_peer``, ``delete_file``, ``file_exists``)
but reads and writes files on a local disk volume instead of Amazon S3.

It is wired in only by ``app.onsite`` (the on-site entrypoint), which reassigns
the functions on the ``app.storage`` module at startup. The cloud app never
imports this file, so the S3 behaviour stays exactly as-is.

Why a signed URL instead of just returning the bytes?
  In the cloud, the browser opens a PDF by following a short-lived **presigned
  S3 URL** — a link that already carries proof it's allowed, so no login header
  is needed. Our React app uses those URLs directly as ``<a href>`` / ``<iframe
  src>`` (a plain browser navigation that *cannot* attach the JWT login header).
  To keep that exact flow working without S3, we hand back our own equivalent:
  a URL pointing at ``/files/...`` stamped with an expiry and an HMAC signature.
  The signature (made with the app's JWT secret) is the access control — the
  ``files_router`` only serves a file if the signature checks out and hasn't
  expired. Same security model as a presigned URL, no AWS involved.
"""

import hashlib
import hmac
import os
import shutil
import time
from urllib.parse import quote

from app.config import settings

# Root directory on the mounted disk volume where every file lives.
# Defaults to /data/vault (a docker volume in the on-site compose stack).
LOCAL_STORAGE_PATH = os.getenv("LOCAL_STORAGE_PATH", "/data/vault")

# URL prefix the *browser* uses to reach the file endpoint. On the on-site
# bundle the SPA is served by nginx which proxies "/api/..." to the backend,
# so "/api" is correct. (boto3's presigned URLs were absolute https links; this
# is the on-site equivalent.)
FILE_PUBLIC_BASE = os.getenv("FILE_PUBLIC_BASE", "/api")

# How long a generated file link stays valid, mirroring the S3 default of 1h.
DEFAULT_EXPIRY_SECONDS = 3600


# ── Per-vault key prefixing (same scheme as app.storage) ─────────────────────
# Keys are stored "bare" (repo/doc/hash.pdf) in the database; every file lives
# on disk under a top-level folder named after the vault that owns it, so the
# two vault modes never collide.

def _mode() -> str:
    return settings.VAULT_MODE or "local"


def _peer_mode() -> str:
    return "remote" if _mode() == "local" else "local"


def _rel(s3_key: str, mode: str | None = None) -> str:
    # The path *relative to the storage root* — also exactly the path component
    # that appears in the file URL and that we sign.
    return f"{mode or _mode()}/{s3_key}"


def _abs(rel_path: str) -> str:
    # Absolute path on disk for a relative "{mode}/{key}" path.
    return os.path.join(LOCAL_STORAGE_PATH, rel_path)


def _resolve_existing(s3_key: str) -> str | None:
    # This vault's prefixed key, falling back to the legacy un-prefixed key for
    # objects written before per-vault prefixes existed. None if neither exists.
    for candidate in (_rel(s3_key), s3_key):
        if os.path.isfile(_abs(candidate)):
            return candidate
    return None


# ── HMAC signing (the access control for served files) ───────────────────────

def sign(rel_path: str, exp: int) -> str:
    # Sign "<path>:<expiry>" with the app's JWT secret. Same secret the rest of
    # the app trusts, so no extra key to manage.
    msg = f"{rel_path}:{exp}".encode()
    return hmac.new(settings.JWT_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def verify(rel_path: str, exp: int, sig: str) -> bool:
    # Reject anything past its expiry, then constant-time compare the signature
    # (compare_digest avoids leaking byte-by-byte timing information).
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sign(rel_path, exp), sig)


def _signed_url(rel_path: str, expires_in: int) -> str:
    exp = int(time.time()) + expires_in
    # quote each path segment but keep the "/" separators readable in the URL.
    safe = quote(rel_path, safe="/")
    return f"{FILE_PUBLIC_BASE}/files/{safe}?exp={exp}&sig={sign(rel_path, exp)}"


# ── Public API (mirrors app.storage) ─────────────────────────────────────────

def upload_file(content: bytes, s3_key: str, content_type: str = "application/octet-stream") -> str:
    # Write under this vault's prefix, creating parent folders as needed.
    # Returns the BARE key for the DB — the prefix is re-derived on every access.
    dst = _abs(_rel(s3_key))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(content)
    return s3_key


def download_file(s3_key: str) -> bytes:
    # Read raw bytes for this vault's copy (or the legacy un-prefixed file).
    rel = _resolve_existing(s3_key) or _rel(s3_key)
    with open(_abs(rel), "rb") as f:
        return f.read()


def generate_presigned_url(s3_key: str, expires_in: int = DEFAULT_EXPIRY_SECONDS) -> str:
    # Signed, expiring link the browser can open directly — our on-site stand-in
    # for an S3 presigned URL.
    rel = _resolve_existing(s3_key) or _rel(s3_key)
    return _signed_url(rel, expires_in)


def presigned_url_if_exists(s3_key: str | None, expires_in: int = DEFAULT_EXPIRY_SECONDS) -> str | None:
    # Signed URL for the key, or None if it's empty or the file is missing —
    # so the UI can show a clean "file unavailable" state instead of a 404 link.
    if not s3_key:
        return None
    rel = _resolve_existing(s3_key)
    if not rel:
        return None
    return _signed_url(rel, expires_in)


def copy_from_peer(s3_key: str) -> bool:
    # Copy an object from the peer vault's prefix (or legacy key) into this
    # vault's prefix, so each vault owns its own copy. Missing source is
    # non-fatal — the UI degrades via presigned_url_if_exists.
    dst = _abs(_rel(s3_key))
    for src_rel in (_rel(s3_key, _peer_mode()), s3_key):
        src = _abs(src_rel)
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            return True
    return False


def delete_file(s3_key: str) -> None:
    # Delete only THIS vault's file — never the peer's prefix, never the legacy
    # shared key. Missing file is fine; the goal is simply that it's gone.
    try:
        os.remove(_abs(_rel(s3_key)))
    except FileNotFoundError:
        pass


def file_exists(s3_key: str) -> bool:
    # True if this vault's file (or the legacy un-prefixed one) is on disk.
    return _resolve_existing(s3_key) is not None

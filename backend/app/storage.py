import boto3
from botocore.exceptions import ClientError
from app.config import settings


def _s3():
    # boto3 finds AWS credentials automatically:
    # - On EKS: uses the IRSA role attached to the pod's service account
    # - Locally: uses ~/.aws/credentials or environment variables
    # Never hardcode credentials here
    return boto3.client("s3", region_name=settings.AWS_REGION)


# ── Per-vault key prefixing ────────────────────────────────────────────────────
# The local and remote vaults share one bucket. To keep them isolated — so a
# repo deletion on one vault can never wipe the other's drawings — every object
# lives under a top-level prefix named after the vault that owns it
# ("local/..." or "remote/..."). The bare key (repo/doc/hash.pdf) is what we
# store in the DB; the prefix is applied here, per vault, on every S3 call.

def _mode() -> str:
    return settings.VAULT_MODE or "local"


def _peer_mode() -> str:
    return "remote" if _mode() == "local" else "local"


def _full(s3_key: str, mode: str | None = None) -> str:
    return f"{mode or _mode()}/{s3_key}"


def _resolve_existing(s3_key: str) -> str | None:
    # This vault's prefixed key, falling back to the legacy un-prefixed key for
    # objects written before per-vault prefixes existed. None if neither exists.
    for candidate in (_full(s3_key), s3_key):
        try:
            _s3().head_object(Bucket=settings.S3_BUCKET, Key=candidate)
            return candidate
        except ClientError:
            continue
    return None


def upload_file(content: bytes, s3_key: str, content_type: str = "application/octet-stream") -> str:
    # Upload under this vault's prefix. Returns the BARE key for the DB — the
    # prefix is re-derived per vault on every read/write.
    _s3().put_object(
        Bucket=settings.S3_BUCKET,
        Key=_full(s3_key),
        Body=content,
        ContentType=content_type,
    )
    return s3_key


def download_file(s3_key: str) -> bytes:
    # Download a file from S3 and return its raw bytes
    key = _resolve_existing(s3_key) or _full(s3_key)
    response = _s3().get_object(Bucket=settings.S3_BUCKET, Key=key)
    return response["Body"].read()


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    # Generate a temporary URL that anyone can use to download this vault's copy
    # expires_in = seconds until the link expires (default: 1 hour)
    key = _resolve_existing(s3_key) or _full(s3_key)
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )


def presigned_url_if_exists(s3_key: str | None, expires_in: int = 3600) -> str | None:
    # Presigned URL for the key, or None if it's empty or the object is missing.
    # Guards against handing the UI a link to a deleted object (e.g. a PDF that
    # was drained when a repo was removed) — otherwise the browser shows the raw
    # S3 "NoSuchKey" XML instead of a clean "file unavailable" state.
    if not s3_key:
        return None
    key = _resolve_existing(s3_key)
    if not key:
        return None
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )


def copy_from_peer(s3_key: str) -> bool:
    # Copy an object from the peer vault's prefix into this vault's prefix, so
    # each vault holds its own copy and a delete on one never affects the other.
    # Used when ingesting a peer's commits (remote on receive, local on pull).
    # Missing source is non-fatal — the UI degrades via presigned_url_if_exists.
    dst = _full(s3_key)
    # try the peer's prefixed key first, then a legacy un-prefixed source
    for src in (_full(s3_key, _peer_mode()), s3_key):
        try:
            _s3().copy_object(
                Bucket=settings.S3_BUCKET,
                CopySource={"Bucket": settings.S3_BUCKET, "Key": src},
                Key=dst,
            )
            return True
        except ClientError:
            continue
    return False


def delete_file(s3_key: str) -> None:
    # Delete only THIS vault's object — never the peer's prefix, never the legacy
    # shared key — so cleaning up one vault's repo can't strip the other's files.
    try:
        _s3().delete_object(Bucket=settings.S3_BUCKET, Key=_full(s3_key))
    except ClientError:
        pass  # if the file doesn't exist, that's fine — goal is it's gone


def file_exists(s3_key: str) -> bool:
    # Check if a file exists in S3 (this vault's prefix or legacy) without downloading
    return _resolve_existing(s3_key) is not None

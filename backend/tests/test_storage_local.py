"""
Filesystem storage backend (app.storage_local) used by the on-site, AWS-free
build. Mirrors the per-vault prefix guarantees of the S3 backend and verifies the
HMAC-signed file links that stand in for S3 presigned URLs.
"""
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app import config, storage_local


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    # Point the backend at a throwaway dir and pin a known signing secret/mode.
    monkeypatch.setattr(storage_local, "LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(storage_local, "FILE_PUBLIC_BASE", "/api")
    monkeypatch.setattr(config.settings, "VAULT_MODE", "local")
    monkeypatch.setattr(config.settings, "JWT_SECRET", "test-secret")
    return tmp_path


def test_upload_download_roundtrip_under_vault_prefix(local_store):
    key = storage_local.upload_file(b"hello", "repo/doc/h.pdf", "application/pdf")
    assert key == "repo/doc/h.pdf"                       # bare key returned for the DB
    # the bytes land under this vault's prefix on disk
    assert (local_store / "local" / "repo" / "doc" / "h.pdf").read_bytes() == b"hello"
    assert storage_local.download_file("repo/doc/h.pdf") == b"hello"
    assert storage_local.file_exists("repo/doc/h.pdf") is True


def test_delete_only_touches_this_vault(local_store):
    storage_local.upload_file(b"x", "repo/doc/h.pdf")
    peer = local_store / "remote" / "repo" / "doc"        # peer vault's own copy
    peer.mkdir(parents=True)
    (peer / "h.pdf").write_bytes(b"peer")
    storage_local.delete_file("repo/doc/h.pdf")
    assert not (local_store / "local" / "repo" / "doc" / "h.pdf").exists()
    assert (peer / "h.pdf").exists()                      # peer untouched


def test_copy_from_peer_pulls_from_the_other_prefix(local_store, monkeypatch):
    monkeypatch.setattr(config.settings, "VAULT_MODE", "remote")  # acting as remote
    src = local_store / "local" / "repo" / "doc"
    src.mkdir(parents=True)
    (src / "h.pdf").write_bytes(b"bytes")
    assert storage_local.copy_from_peer("repo/doc/h.pdf") is True
    assert (local_store / "remote" / "repo" / "doc" / "h.pdf").read_bytes() == b"bytes"


def test_signed_url_round_trips_and_rejects_tampering(local_store):
    storage_local.upload_file(b"x", "repo/doc/h.pdf")
    url = storage_local.generate_presigned_url("repo/doc/h.pdf")
    assert url.startswith("/api/files/local/repo/doc/h.pdf?")
    q = parse_qs(urlparse(url).query)
    exp, sig = int(q["exp"][0]), q["sig"][0]
    assert storage_local.verify("local/repo/doc/h.pdf", exp, sig) is True
    assert storage_local.verify("local/repo/doc/h.pdf", exp, "deadbeef") is False   # bad sig
    assert storage_local.verify("local/repo/doc/OTHER.pdf", exp, sig) is False      # bad path


def test_expired_url_is_rejected(local_store):
    rel = "local/repo/doc/h.pdf"
    past = int(time.time()) - 1
    assert storage_local.verify(rel, past, storage_local.sign(rel, past)) is False


def test_missing_object_yields_no_url(local_store):
    assert storage_local.presigned_url_if_exists("repo/doc/missing.pdf") is None


def test_reads_fall_back_to_legacy_unprefixed_files(local_store):
    legacy = local_store / "repo" / "doc"                 # pre-prefix legacy object
    legacy.mkdir(parents=True)
    (legacy / "h.pdf").write_bytes(b"legacy")
    assert storage_local.file_exists("repo/doc/h.pdf") is True
    assert storage_local.presigned_url_if_exists("repo/doc/h.pdf") is not None

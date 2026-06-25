"""Per-vault S3 prefixing: each vault owns a top-level prefix so a repo
deletion on one vault can never touch the other's objects (shared bucket)."""
from app import config, storage


class FakeS3:
    """Records S3 calls and answers head_object from a fixed key set."""
    def __init__(self, existing=()):
        self.existing = set(existing)
        self.put = []
        self.deleted = []
        self.copied = []

    def put_object(self, Bucket, Key, Body, ContentType):
        self.put.append(Key)
        self.existing.add(Key)

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)

    def copy_object(self, Bucket, CopySource, Key):
        if CopySource["Key"] not in self.existing:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "CopyObject")
        self.copied.append((CopySource["Key"], Key))
        self.existing.add(Key)

    def head_object(self, Bucket, Key):
        if Key not in self.existing:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://s3.test/{Params['Key']}?sig=x"


def _use(monkeypatch, fake, mode):
    monkeypatch.setattr(storage, "_s3", lambda: fake)
    monkeypatch.setattr(config.settings, "VAULT_MODE", mode)
    monkeypatch.setattr(config.settings, "S3_BUCKET", "b")


def test_upload_and_delete_are_scoped_to_the_vault_prefix(monkeypatch):
    fake = FakeS3()
    _use(monkeypatch, fake, "local")
    key = storage.upload_file(b"x", "repo/doc/h.pdf")
    assert key == "repo/doc/h.pdf"             # bare key stored in the DB
    assert fake.put == ["local/repo/doc/h.pdf"]  # object lives under local/
    storage.delete_file("repo/doc/h.pdf")
    assert fake.deleted == ["local/repo/doc/h.pdf"]  # delete never leaves the prefix


def test_delete_on_one_vault_does_not_touch_the_peer(monkeypatch):
    # remote has its own copy; a local delete must not name the remote object
    fake = FakeS3(existing={"local/repo/doc/h.pdf", "remote/repo/doc/h.pdf"})
    _use(monkeypatch, fake, "local")
    storage.delete_file("repo/doc/h.pdf")
    assert fake.deleted == ["local/repo/doc/h.pdf"]
    assert "remote/repo/doc/h.pdf" in fake.existing  # peer untouched


def test_copy_from_peer_pulls_from_the_other_prefix(monkeypatch):
    fake = FakeS3(existing={"local/repo/doc/h.pdf"})
    _use(monkeypatch, fake, "remote")  # acting as the remote vault on receive
    assert storage.copy_from_peer("repo/doc/h.pdf") is True
    assert fake.copied == [("local/repo/doc/h.pdf", "remote/repo/doc/h.pdf")]


def test_reads_fall_back_to_legacy_unprefixed_objects(monkeypatch):
    fake = FakeS3(existing={"repo/doc/h.pdf"})  # pre-prefix legacy object
    _use(monkeypatch, fake, "local")
    assert storage.file_exists("repo/doc/h.pdf") is True
    assert storage.presigned_url_if_exists("repo/doc/h.pdf") is not None


def test_missing_object_yields_no_url(monkeypatch):
    fake = FakeS3()
    _use(monkeypatch, fake, "local")
    assert storage.presigned_url_if_exists("repo/doc/h.pdf") is None

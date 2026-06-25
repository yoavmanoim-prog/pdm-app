"""Per-repo settings: the part-number format derived from a sample part number."""
from app.settings_config import mask_from_example, part_number_matches, validate_example


# ── helper unit tests ──────────────────────────────────────────────────────────

def test_mask_from_example():
    assert mask_from_example("FW-PT-0001") == "AA-AA-####"
    assert mask_from_example("ENG.123/ab") == "AAA.###/AA"


def test_part_number_matches():
    assert part_number_matches("FW-PT-0001", "FW-MA-0002") is True
    assert part_number_matches("FW-PT-0001", "fw-ma-0002") is True   # case-insensitive
    assert part_number_matches("FW-PT-0001", "FW-PT-001") is False   # wrong digit count
    assert part_number_matches("FW-PT-0001", "FWPT0001") is False    # missing separators


def test_validate_example():
    assert validate_example("") is not None
    assert validate_example("----") is not None       # no letter/digit
    assert validate_example("FW-PT-0001") is None


# ── endpoint + document validation (via the local-vault TestClient) ─────────────

def _create_doc(client, rid, part_number):
    return client.post(
        f"/repos/{rid}/documents/",
        json={"part_number": part_number, "title": "t", "doc_type": "part"},
    )


def test_settings_endpoint_and_document_validation(vaults):
    c = vaults.client
    rid = c.post("/repos/", json={"name": "fmt-repo"}).json()["id"]

    # no format configured -> any part number is accepted
    assert _create_doc(c, rid, "WHATEVER-1").status_code == 201

    # configure a format from a sample
    s = c.put(f"/repos/{rid}/settings", json={"part_number_example": "FW-PT-0001"}).json()
    assert s["part_number_template"] == "AA-AA-####"
    assert c.get(f"/repos/{rid}/settings").json()["part_number_example"] == "FW-PT-0001"

    # matching part number is accepted, non-matching is rejected
    assert _create_doc(c, rid, "FW-MA-0002").status_code == 201
    assert _create_doc(c, rid, "BAD-1").status_code == 400

    # clearing the format allows any part number again
    assert c.put(f"/repos/{rid}/settings", json={"part_number_example": None}).json()["part_number_example"] is None
    assert _create_doc(c, rid, "ANYTHING9").status_code == 201


def test_invalid_sample_rejected(vaults):
    rid = vaults.client.post("/repos/", json={"name": "fmt-repo-2"}).json()["id"]
    r = vaults.client.put(f"/repos/{rid}/settings", json={"part_number_example": "----"})
    assert r.status_code == 400


# ── pdf_bom missing-detection uses the repo's template ──────────────────────────

def test_missing_detection_uses_repo_template(vaults):
    from app.models.repository import Repository
    from app.services.pdf_bom import _missing_detection_re

    db = vaults.local()
    repo = Repository(name="detect-repo", settings={"part_number_example": "FW-PT-0001"})
    db.add(repo)
    db.commit()
    repo_id = repo.id
    db.close()

    db = vaults.local()
    pattern = _missing_detection_re(repo_id, db)
    found = set(pattern.findall("REFS: FW-PT-0001 AB-CD-9999 and GG-1 nope"))
    db.close()
    assert "FW-PT-0001" in found and "AB-CD-9999" in found
    assert "GG-1" not in found


def test_revision_scheme_setting(vaults):
    c = vaults.client
    rid = c.post("/repos/", json={"name": "scheme-repo"}).json()["id"]

    # default is letters
    assert c.get(f"/repos/{rid}/settings").json()["revision_scheme"] == "letters"

    # switch to numbers
    assert c.put(f"/repos/{rid}/settings", json={"revision_scheme": "numbers"}).json()["revision_scheme"] == "numbers"
    assert c.get(f"/repos/{rid}/settings").json()["revision_scheme"] == "numbers"

    # invalid scheme rejected
    assert c.put(f"/repos/{rid}/settings", json={"revision_scheme": "roman"}).status_code == 400

    # partial update: setting the part-number format must not reset the scheme
    c.put(f"/repos/{rid}/settings", json={"part_number_example": "AA-0001"})
    assert c.get(f"/repos/{rid}/settings").json()["revision_scheme"] == "numbers"

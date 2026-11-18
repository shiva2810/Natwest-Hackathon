"""The left panel's data: every source file, grouped by department, with live sizes and content."""
import importlib

import pytest
from fastapi.testclient import TestClient

from seam.engine import Engine
from seam.governance import ROOT, GovernanceError


@pytest.fixture
def eng(tmp_path):
    e = Engine(ROOT / "data", tmp_path / "a.jsonl", tmp_path / "s.json")
    e.run()
    return e


def test_sources_lists_every_department_file(eng):
    s = eng.sources()
    names = {d["name"]: {f["name"]: f for f in d["files"]} for d in s["departments"]}
    assert list(names) == ["HR", "Finance", "Legal", "Product"]
    assert names["HR"]["roster.csv"]["size"] == 28 and names["HR"]["roster.csv"]["kind"] == "table"
    assert names["Legal"]["legal_policies_excerpt.md"]["kind"] == "document"
    assert names["Legal"]["product_approval.json"]["kind"] == "record"
    assert s["kind"] == "folder" and s["applied_events"] == 0


def test_sources_are_live_after_an_event(eng):
    eng.apply_scenario("fix_support_capacity")                 # inserts three roster rows
    roster = next(f for d in eng.sources()["departments"] for f in d["files"] if f["file"] == "hr/roster.csv")
    assert roster["size"] == 31 and eng.sources()["applied_events"] == 1
    assert eng.source_content("hr/roster.csv")["total"] == 31


def test_source_content_and_unknown_file(eng):
    assert eng.source_content("hr/roster.csv", limit=5)["rows"][0]["employee_id"] == "E001"
    assert "Conduct Policy" in eng.source_content("legal/legal_policies_excerpt.md")["text"]
    assert eng.source_content("legal/product_approval.json")["json"]
    for bad in ("../README.md", "hr/nope.csv", "/etc/passwd"):
        with pytest.raises(GovernanceError):
            eng.source_content(bad)


def test_sources_over_http(tmp_path, monkeypatch):
    monkeypatch.setenv("SEAM_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("SEAM_STATE", str(tmp_path / "state.json"))
    import seam.api
    client = TestClient(importlib.reload(seam.api).app)
    assert client.get("/sources").json()["departments"][0]["name"] == "HR"
    assert client.get("/sources/content", params={"path": "hr/roster.csv"}).json()["total"] == 28
    assert client.get("/sources/content", params={"path": "../x"}).status_code == 409
    import base64
    up = {"dept": "legal", "name": "memo.md", "content_b64": base64.b64encode(b"Counsel memo").decode()}
    assert client.post("/sources/upload", json=up).json()["file"] == "legal/memo.md"
    assert client.post("/sources/upload", json={**up, "name": "memo.exe"}).status_code == 422
    assert client.get("/sources/content", params={"path": "legal/memo.md"}).json()["text"] == "Counsel memo"


# ---------- files added through the UI ----------

def test_add_upload_lists_previews_and_is_searchable(eng):
    before = eng.passport()["overall"]
    out = eng.add_upload("hr", "visa_notes.md", b"# Visa notes\n\nPriya Nair needs a Zephyrine work permit renewal.", "tester")
    assert out["file"] == "hr/visa_notes.md" and out["kind"] == "document"
    hr = next(d for d in eng.sources()["departments"] if d["key"] == "hr")
    added = next(f for f in hr["files"] if f["name"] == "visa_notes.md")
    assert added["uploaded"] is True
    assert "Zephyrine" in eng.source_content("hr/visa_notes.md")["text"]
    from seam.qa import build_corpus
    assert any("Zephyrine" in c["text"] and c["source"].startswith("hr/visa_notes.md") for c in build_corpus(eng))
    assert eng.passport()["overall"] == before                      # reference material: the checks are untouched


def test_add_upload_csv_json_and_persistence(eng, tmp_path):
    eng.add_upload("finance", "extra.csv", b"id,amount\nA1,10\nA2,20\n")
    eng.add_upload("legal", "meta.json", b'{"a": 1, "b": 2}')
    assert eng.source_content("finance/extra.csv")["total"] == 2
    assert eng.source_content("legal/meta.json")["json"] == {"a": 1, "b": 2}
    again = Engine.open(ROOT / "data", tmp_path / "a.jsonl", tmp_path / "s.json")      # resumes the saved state
    assert "finance/extra.csv" in again.dataset.uploads
    again.run()                                                                         # reset starts fresh
    assert not again.dataset.uploads


@pytest.mark.parametrize("dept,name,data", [
    ("hr", "roster.csv", b"a,b\n1,2\n"),            # would replace a file the checks read
    ("hr", "x.exe", b"hello"),                      # wrong type
    ("nope", "x.md", b"hello"),                     # unknown department
    ("hr", "x.json", b"{bad"),                      # invalid JSON
    ("hr", "x.csv", b"only,header\n"),              # no rows
    ("hr", "x.md", b"   "),                         # empty
    ("hr", "x.md", b"\xff\xfe\x00bad"),             # not UTF-8
])
def test_add_upload_rejects_bad_files(eng, dept, name, data):
    with pytest.raises(ValueError):
        eng.add_upload(dept, name, data)


def test_add_upload_strips_path_components(eng):
    assert eng.add_upload("hr", r"..\..\evil.md", b"hello there")["file"] == "hr/evil.md"


def test_add_upload_rejects_oversized_file(eng):
    with pytest.raises(ValueError, match="larger than"):
        eng.add_upload("hr", "big.md", b"a" * (Engine.UPLOAD_MAX + 1))

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

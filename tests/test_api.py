import importlib

import pytest
from fastapi.testclient import TestClient

from seam.governance import ROOT

FIXTURES = str(ROOT / "fixtures" / "records.json")


def _client(tmp_path, monkeypatch, records=None):
    monkeypatch.setenv("SEAM_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("SEAM_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("SEAM_LLM", "off")                 # tests never call a live model
    if records:
        monkeypatch.setenv("SEAM_RECORDS", records)
    else:
        monkeypatch.delenv("SEAM_RECORDS", raising=False)
    import seam.api
    return TestClient(importlib.reload(seam.api).app)


def test_fixture_api_flow(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, FIXTURES)
    p = client.get("/passport").json()
    assert p["overall"] == "no_go" and len(p["seams"]) == 5 and p["drafts"] and p["source"] == "records"
    r = client.post("/events", json={"type": "new_product_version", "data": {"product_id": "prod-swiftsave", "version": "1.4"}})
    assert r.json()["diff"]["closed"] == ["version_drift:leg-approval-swiftsave"]
    assert client.post("/events", json={"type": "resignation", "data": {"person_id": "x", "leaving_on": "2026-12-01"}}).status_code == 422
    assert client.post("/signoffs", json={"decision": "go", "signer_name": "Maya Lin", "signer_role": "Director", "reason": "ship"}).status_code == 409
    assert client.post("/signoffs", json={"decision": "go", "signer_name": "", "signer_role": "Director", "reason": "ship"}).status_code == 422
    body = {"signer_name": "Maya Lin", "signer_role": "Director", "reason": "successor agreed", "params": {"owner_id": "p-james"}}
    r = client.post("/drafts/reassign_owner:orphaned_owner:p-priya/approve", json=body)
    assert r.status_code == 200 and r.json()["draft"]["status"] == "approved"
    assert client.post("/agent/attempt/go_no_go").status_code == 403
    assert client.get("/audit").json()["verify"]["ok"]
    assert client.post("/run").json()["product"]["version"] == "2.0"   # reset


def test_dataset_api_flow(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    p = client.get("/passport").json()
    assert p["source"] == "dataset" and p["overall"] == "no_go" and len(p["seams"]) == 5
    assert [e["event_id"] for e in client.get("/events/stream").json()][:2] == ["EV-01", "EV-02"]
    r = client.post("/events/stream/EV-01").json()
    assert r["diff"]["selective_matches_full"] and "seller_training_gap:OBL-L-002" in r["diff"]["changed"]
    assert client.post("/events/stream/EV-01").status_code == 409            # already applied
    assert client.post("/events", json={"type": "resignation", "data": {}}).status_code == 409   # typed: fixtures only
    r = client.post("/scenarios/fix_data_residency").json()
    assert "data_residency_breach:OBL-L-003" in r["diff"]["closed"]
    bad = {"changes": [{"file": "hr/roster.csv", "op": "update", "match": {"employee_id": "E999"}, "set": {"status": "left"}}]}
    assert client.post("/events/custom", json=bad).status_code == 422
    assert client.post("/scenarios/../etc").status_code in (404, 409)
    assert client.post("/run").json()["as_of"] == "2026-11-18"


def test_client_works_without_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("SEAM_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("SEAM_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("SEAM_LLM", "off")
    monkeypatch.delenv("SEAM_RECORDS", raising=False)
    import seam.api
    importlib.reload(seam.api)
    from seam.client import SeamClient, SeamError
    c = SeamClient("http://127.0.0.1:9")          # nothing listens there
    assert c.mode == "in-process"
    assert c.passport()["overall"] == "no_go"
    assert c.scenario("fix_change_control")["diff"]["closed"] == ["version_drift:OBL-L-001"]
    with pytest.raises(SeamError):
        c.sign("go", "Maya Lin", "Director", "ship")

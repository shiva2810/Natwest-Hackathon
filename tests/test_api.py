import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEAM_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("SEAM_STATE", str(tmp_path / "state.json"))
    import seam.api
    return TestClient(importlib.reload(seam.api).app)


def test_api_flow(client):
    p = client.get("/passport").json()
    assert p["overall"] == "no_go" and len(p["seams"]) == 5 and p["drafts"]
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


def test_client_works_without_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("SEAM_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("SEAM_STATE", str(tmp_path / "state.json"))
    from seam.client import SeamClient, SeamError
    c = SeamClient("http://127.0.0.1:9")          # nothing listens there
    assert c.mode == "in-process"
    assert c.passport()["overall"] == "no_go"
    assert c.event("vendor_change", vendor_id="v-payflow", due_diligence="complete")["diff"]["closed"]
    with pytest.raises(SeamError):
        c.sign("go", "Maya Lin", "Director", "ship")

import importlib
import re

import pytest
from fastapi.testclient import TestClient

from seam.report import render_report


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEAM_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("SEAM_STATE", str(tmp_path / "state.json"))
    import seam.api
    return TestClient(importlib.reload(seam.api).app)


def test_report_matches_passport(client):
    p = client.get("/passport").json()
    page = render_report(p, client.get("/audit").json(), generated_at="2026-11-18T09:00:00+00:00")
    assert page.startswith("<!doctype html>") and "<script src" not in page and "<link" not in page   # self-contained
    assert page.count('class="card finding') == len(p["seams"]) + len(p["records"])
    assert page.count('class="eval"') == page.count('class="card finding')
    for s in p["seams"]:
        assert s["title"].replace("'", "&#x27;") in page      # every seam appears, escaped
    n_fail = page.count('data-status="fail"')
    assert n_fail == (sum(1 for s in p["seams"] if s["severity"] in ("critical", "high"))
                      + sum(1 for r in p["records"] if r["status"] == "unmet"))
    assert "HASH CHAIN INTACT" in page and "Auditor review required" in page
    assert p["product"]["name"] in page and p["company"] in page
    assert render_report(p, generated_at="2026-11-18T09:00:00+00:00") != page   # audit section is optional


def test_report_escapes_html(client):
    p = client.get("/passport").json()
    p["seams"][0]["title"] = "<script>alert(1)</script>"
    assert "<script>alert(1)</script>" not in render_report(p)


def test_report_follows_signoff_and_waivers(client):
    assert "WAIVED" not in client.get("/report").text
    body = {"signer_name": "Maya Lin", "signer_role": "Director", "reason": "reviewed with legal"}
    seam = next(s["id"] for s in client.get("/passport").json()["seams"] if s["status"] == "open")
    assert client.post("/signoffs", json={"decision": "waive", "seam_id": seam, **body}).status_code == 200
    page = client.get("/report").text
    assert "WAIVED" in page and "Maya Lin" in page


def test_report_endpoint_download(client):
    r = client.get("/report")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "attachment" not in r.headers.get("content-disposition", "")
    assert "attachment" in client.get("/report?download=true").headers["content-disposition"]
    assert re.search(r"SD-\d{8}-[0-9A-F]{6}", r.text)


def test_client_report_without_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("SEAM_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("SEAM_STATE", str(tmp_path / "state.json"))
    from seam.client import SeamClient
    page = SeamClient("http://127.0.0.1:9").report()
    assert "Compliance audit report" in page and "QuickPay" in page

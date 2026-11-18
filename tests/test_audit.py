import json

import pytest

from seam.audit import ask, route, scoped
from seam.engine import Engine
from seam.governance import ROOT
from seam.llm import CachedLLM


@pytest.fixture
def eng(tmp_path):
    e = Engine(ROOT / "data", tmp_path / "a.jsonl", tmp_path / "s.json")
    e.run()
    return e


def test_keyword_routing():
    assert route("Is HR compliant?")["domains"] == ["HR"]
    assert route("Check Finance and Legal")["domains"] == ["Finance", "Legal"]
    assert route("Is QuickPay ready to launch?")["domains"] == ["HR", "Finance", "Legal"]
    assert route("What if StreamLedger moves to Frankfurt?")["intent"] == "what_if"
    assert route("tell me a joke")["intent"] == "unclear"


def test_llm_routing_and_fallback(tmp_path):
    llm = CachedLLM(lambda p: json.dumps({"intent": "audit", "domains": ["Legal"]}), cache_dir=tmp_path)
    assert route("anything about contracts", llm) == {"intent": "audit", "domains": ["Legal"], "via": "llm"}
    broken = CachedLLM(lambda p: "not json", cache_dir=tmp_path / "b")
    assert route("Is HR compliant?", broken)["via"] == "keywords"


def test_scoping(eng):
    p = eng.passport()
    hr = scoped(p, ["HR"])
    assert list(hr["departments"]) == ["HR"] and hr["seams"] == []
    assert {s["id"] for s in hr["seams_needing_other_domains"]} >= {"seller_training_gap:OBL-L-002"}
    hl = scoped(p, ["HR", "Legal"])
    assert {s["type"] for s in hl["seams"]} == {"seller_training_gap", "version_drift"} and hl["status"] == "no_go"
    full = scoped(p, ["HR", "Finance", "Legal"])
    assert len(full["seams"]) == 5 and full["status"] == "no_go" and full["note"] is None


def test_ask_end_to_end(eng):
    out = ask(eng, "Is Legal compliant?")
    assert out["route"]["domains"] == ["Legal"] and out["audit"]["totals"]["failed"] == 1
    out = ask(eng, "What if StreamLedger moves to Frankfurt?")       # no model configured: clear fallback
    assert "fallback" in out["route"] and "simulation" not in out
    assert eng.audit.entries()[-1]["kind"] == "audit_question"

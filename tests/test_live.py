"""Live what-if checks: simulate without side effects, validate everything, apply only when confirmed."""
import json

import pytest

from seam.engine import Engine
from seam.governance import ROOT, GovernanceError
from seam.llm import CachedLLM
from seam.whatif import WhatIfError, field_change


@pytest.fixture
def eng(tmp_path):
    e = Engine(ROOT / "data", tmp_path / "a.jsonl", tmp_path / "s.json")
    e.run()
    return e


def test_simulate_changes_nothing(eng):
    before = (json.dumps(eng.dataset.tables, sort_keys=True), sorted(eng.seams), len(eng.audit.entries()))
    sim = eng.simulate(field_change(eng.dataset, "finance/vendors.csv", {"vendor_id": "V002"},
                                    "data_processing_region", "EU-Frankfurt"))
    assert sim["closed"] == ["data_residency_breach:OBL-L-003"] and sim["status_after"] == "no_go"
    assert sim["preview"][0]["before"] == "US-East" and sim["preview"][0]["after"] == "EU-Frankfurt"
    assert (json.dumps(eng.dataset.tables, sort_keys=True), sorted(eng.seams), len(eng.audit.entries())) == before


def test_simulate_opens_seam_and_flags_departments(eng):
    sim = eng.simulate(field_change(eng.dataset, "hr/roster.csv", {"employee_id": "E007"}, "status", "left"))
    assert "orphaned_owner:E007" in sim["opened"]


def test_validation_rejects_bad_changes(eng):
    with pytest.raises(WhatIfError, match="no column"):
        eng.simulate(field_change(eng.dataset, "hr/roster.csv", {"employee_id": "E001"}, "salary", "1"))
    with pytest.raises(WhatIfError, match="no row"):
        eng.simulate(field_change(eng.dataset, "hr/roster.csv", {"employee_id": "E999"}, "status", "left"))
    with pytest.raises(WhatIfError, match="unknown"):
        eng.simulate({"changes": [{"file": "hr/secret.csv", "op": "update", "match": {}, "set": {}}]})
    with pytest.raises(WhatIfError, match="missing column"):
        eng.simulate({"changes": [{"file": "hr/roster.csv", "op": "insert", "row": {"employee_id": "E099"}}]})


def test_apply_needs_a_named_person(eng):
    ev = field_change(eng.dataset, "legal/product_approval.json", {}, "approved_version", "2.0")
    with pytest.raises(GovernanceError, match="named person"):
        eng.apply_live(ev, "")
    out = eng.apply_live(ev, "Grace Kim", "re-approval minuted")
    assert out["diff"]["event"]["id"] == "LIVE-1" and "version_drift:OBL-L-001" in out["diff"]["closed"]
    assert eng.audit.entries()[-1]["actor"] == "Grace Kim"
    out = eng.apply_live(field_change(eng.dataset, "finance/vendors.csv", {"vendor_id": "V002"},
                                      "data_processing_region", "EU-Frankfurt"), "Grace Kim")
    assert out["diff"]["event"]["id"] == "LIVE-2"


def test_plain_english_with_model(eng, tmp_path):
    def fake(prompt):
        if "Question: What if StreamLedger moves" in prompt:
            return json.dumps({"description": "StreamLedger moves to Frankfurt", "changes": [
                {"file": "finance/vendors.csv", "op": "update", "match": {"vendor_id": "V002"},
                 "set": {"data_processing_region": "EU-Frankfurt"}}]})
        return json.dumps({"description": "made up", "changes": [
            {"file": "finance/vendors.csv", "op": "update", "match": {"vendor_id": "V002"}, "set": {"risk_score": "9"}}]})
    eng.llm = CachedLLM(fake, cache_dir=tmp_path / "c")
    sim = eng.propose_what_if("What if StreamLedger moves processing to Frankfurt?")
    assert sim["closed"] == ["data_residency_breach:OBL-L-003"]
    assert eng.audit.entries()[-1]["kind"] == "what_if_proposed"
    with pytest.raises(WhatIfError, match="no column"):              # model invented a column
        eng.propose_what_if("What if StreamLedger gets riskier?")


def test_plain_english_offline(eng, tmp_path):
    eng.llm = None
    with pytest.raises(WhatIfError, match="form editor"):
        eng.propose_what_if("anything")
    eng.llm = CachedLLM(None, cache_dir=tmp_path / "empty")
    with pytest.raises(WhatIfError, match="offline"):
        eng.propose_what_if("anything")


def test_editable_lists_tables_and_docs(eng):
    ed = eng.editable()
    assert ed["tables"]["hr/roster.csv"]["key"] == ["employee_id"] and "approved_version" in ed["docs"]["legal/product_approval.json"]

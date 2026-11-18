"""The real dataset end to end: checks, seams, events, scenarios, drafts, sign-off."""
import pytest

from seam.engine import Engine
from seam.governance import ROOT, GovernanceError, SignOff

DATA = ROOT / "data"
MAYA = dict(signer_name="Helena Brandt", signer_role="Chief Operating Officer")


@pytest.fixture
def eng(tmp_path):
    e = Engine(DATA, tmp_path / "a.jsonl", tmp_path / "s.json")
    e.run()
    return e


def types(e):
    return sorted(s.type for s in e.seams.values() if s.status == "open")


def test_baseline(eng):
    assert types(eng) == ["data_residency_breach", "orphaned_owner", "seller_training_gap",
                          "support_capacity_gap", "version_drift"]
    p = eng.passport()
    assert p["overall"] == "no_go"
    legal = p["departments"]["Legal"]
    assert legal["own_view"] == "conditional" and legal["status"] == "no_go"
    assert set(legal["self_attested"]) == {"OBL-L-002", "OBL-L-003", "OBL-L-005", "OBL-L-007", "OBL-L-009"}
    assert all(s["basis"] for s in p["seams"])


def test_decoys_not_flagged(eng):
    text = str([s.model_dump() for s in eng.seams.values()])
    for decoy in ("V003", "E028", "E017", "PO-2026-0436"):
        assert decoy not in text
    # D4: support agents have no PCT-101 but don't sell - not in the seller seam (they ARE the S4 staffing)
    s2 = str(eng.seams["seller_training_gap:OBL-L-002"].facts)
    assert not any(f"E0{n}" in s2 for n in range(20, 25))


def test_full_event_stream(eng):
    for ev in ["EV-01", "EV-02", "EV-03", "EV-04", "EV-05"]:
        r = eng.apply_stream_event(ev)
        assert r["diff"]["selective_matches_full"]
    s1 = eng.seams["orphaned_owner:E004"]
    assert not any(x.startswith("owner of") for x in s1.facts["roles"])       # Legal side fixed by EV-04
    assert any("PO-2026-0450" in x for x in s1.facts["roles"])
    r = eng.apply_stream_event("EV-06")
    assert "orphaned_owner:E004" in r["diff"]["closed"] and r["passport"]["overall"] == "no_go"


def test_scenarios_fix_everything_then_go(eng):
    for ev in ["EV-01", "EV-02", "EV-03", "EV-04", "EV-05", "EV-06"]:
        eng.apply_stream_event(ev)
    with pytest.raises(GovernanceError):
        eng.sign(SignOff(decision="go", reason="on schedule", **MAYA))
    for sc in ["fix_change_control", "fix_support_capacity", "fix_seller_training"]:
        eng.apply_scenario(sc)
    assert types(eng) == ["data_residency_breach"]            # V002 and V007 both still in the US
    eng.apply_scenario("fix_data_residency")
    assert "V007" in str(eng.seams["data_residency_breach:OBL-L-003"].facts)  # V002 fixed, V007 remains
    s = SignOff(decision="waive", seam_id="data_residency_breach:OBL-L-003",
                reason="VerifyPoint EU region migration signed for 2026-12-15; terms addendum sent", **MAYA)
    eng.sign(s)
    p = eng.sign(SignOff(decision="go", reason="all seams fixed or waived", **MAYA))
    assert p["overall"] == "conditional" and p["signoff"]["state"] == "go"


def test_new_seams_from_scenarios(eng):
    r = eng.apply_scenario("general_counsel_resigns")
    assert r["diff"]["opened"] == ["orphaned_owner:E003"]
    r = eng.apply_scenario("decoy_turns_real")
    assert "data_residency_breach:OBL-L-003" in r["diff"]["changed"]
    assert "V003" in str(eng.seams["data_residency_breach:OBL-L-003"].facts["breaches"])
    r = eng.apply_scenario("new_seller_untrained")
    assert "4 seller(s)" in eng.seams["seller_training_gap:OBL-L-002"].title
    assert all(h["diff"]["selective_matches_full"] for h in eng.history)


def test_draft_reassign_on_real_data(eng):
    d = "reassign_owner:orphaned_owner:E004"
    out = eng.decide_draft(d, True, SignOff(decision="waive", reason="Priya covers until backfill", **MAYA),
                           {"owner_id": "E010"})
    roles = eng.seams["orphaned_owner:E004"].facts["roles"]
    assert out["draft"]["status"] == "approved" and not any(x.startswith("owner of") for x in roles)


def test_state_survives_restart(eng, tmp_path):
    eng.apply_stream_event("EV-01")
    again = Engine.open(DATA, tmp_path / "a.jsonl", tmp_path / "s.json")
    assert again.dataset.applied == ["EV-01"] and len(again.history) == 1
    assert "2 seller(s)" in again.seams["seller_training_gap:OBL-L-002"].title

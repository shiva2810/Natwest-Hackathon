import json
from pathlib import Path

import pytest

from seam.engine import Engine
from seam.pipeline import Event
from seam.schema import Bundle
from seam.governance import GovernanceError, SignOff

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "fixtures" / "records.json"
KEY = json.loads((ROOT / "fixtures" / "answer_key.json").read_text())["expected_seams"]


@pytest.fixture
def eng(tmp_path):
    e = Engine(RECORDS, tmp_path / "audit.jsonl", tmp_path / "state.json")
    e.run()
    return e


def test_finds_all_planted_seams_and_no_false_positives(eng):
    found = {(s.type, s.anchor) for s in eng.seams.values()}
    expected = {(x["type"], x["anchor"]) for x in KEY}
    assert expected <= found, f"missed: {expected - found}"
    assert found == expected, f"false positives: {found - expected}"


def test_every_seam_is_explained_and_ranked(eng):
    p = eng.passport()
    scores = [s["score"] for s in p["seams"]]
    assert scores == sorted(scores, reverse=True)
    assert all(s["explanation"] and s["fix_options"] for s in p["seams"])
    assert p["overall"] == "no_go"


def test_departments_look_fine_alone_but_seams_block(eng):
    legal = eng.passport()["departments"]["Legal"]
    assert legal["own_view"] == "go" and legal["status"] == "no_go"


def test_event_selective_recheck_closes_seam(eng):
    out = eng.apply_event(Event(type="training_completed", data={
        "person_id": "p-ana", "course": "GDPR Advanced",
        "completed_on": "2026-11-20", "expires_on": "2027-11-20"}))
    assert out["diff"]["closed"] == ["training_lapse:leg-dpo-cert"]
    assert "c-brightads" not in out["diff"]["rechecked_nodes"]  # untouched part of the graph


def test_event_opens_seam(eng):
    out = eng.apply_event(Event(type="vendor_change", data={"vendor_id": "v-cloudnest", "due_diligence": "pending"}))
    assert "unvetted_vendor:c-cloudnest" in out["diff"]["opened"]


def test_go_blocked_until_waived_and_named(eng):
    with pytest.raises(GovernanceError):
        eng.sign(SignOff(decision="go", signer_name="Maya Lin", signer_role="Launch Director", reason="ship it"))
    with pytest.raises(ValueError):
        SignOff(decision="no_go", signer_name="", signer_role="x", reason="")
    for s in list(eng.seams.values()):
        eng.sign(SignOff(decision="waive", seam_id=s.id, signer_name="Maya Lin",
                         signer_role="Launch Director", reason="accepted for pilot with controls"))
    p = eng.sign(SignOff(decision="go", signer_name="Maya Lin", signer_role="Launch Director",
                         reason="all seams waived with controls"))
    assert p["signoff"]["state"] == "go"


def test_event_invalidates_signoff(eng):
    eng.sign(SignOff(decision="no_go", signer_name="Maya Lin", signer_role="Launch Director", reason="too many gaps"))
    eng.apply_event(Event(type="new_product_version", data={"product_id": "prod-swiftsave", "version": "1.4"}))
    assert eng.signoff["state"] == "pending"


def test_agent_cannot_sign(eng):
    with pytest.raises(GovernanceError):
        eng.agent_attempt("go_no_go")
    assert eng.agent_attempt("notify_owner") == "draft"


def test_audit_chain_detects_tampering(eng):
    assert eng.audit.verify()["ok"]
    lines = eng.audit.path.read_text().splitlines()
    first = json.loads(lines[0]); first["actor"] = "someone-else"
    lines[0] = json.dumps(first)
    eng.audit.path.write_text("\n".join(lines) + "\n")
    v = eng.audit.verify()
    assert not v["ok"] and v["broken_at"] == 0


def test_llm_failure_falls_back_to_template(tmp_path):
    def broken(_):
        raise TimeoutError("no network")
    e = Engine(RECORDS, tmp_path / "a.jsonl", tmp_path / "s.json", llm=broken)
    e.run()
    assert all(s.facts["explained_by"] == "template" and s.explanation for s in e.seams.values())


def test_pipeline_runs_through_langgraph(eng):
    run = eng.audit.entries()[0]
    assert run["data"]["pipeline"] == ["check_departments", "build_graph", "detect_seams", "score", "referee", "propose_drafts"]
    eng.apply_event(Event(type="vendor_change", data={"vendor_id": "v-payflow", "due_diligence": "complete"}))
    assert eng.audit.entries()[-1]["data"]["pipeline"][0] == "apply_event"


def test_state_survives_restart(eng, tmp_path):
    eng.sign(SignOff(decision="waive", seam_id="training_lapse:leg-dpo-cert", signer_name="Maya Lin",
                     signer_role="Launch Director", reason="renewal booked for 25 Nov"))
    eng.apply_event(Event(type="new_product_version", data={"product_id": "prod-swiftsave", "version": "1.4"}))
    again = Engine.open(RECORDS, tmp_path / "audit.jsonl", tmp_path / "state.json")
    assert again.seams["training_lapse:leg-dpo-cert"].status == "waived"
    assert again.product.launch_version == "1.4"
    assert len(again.history) == 1
    assert len(again.audit.entries()) == len(eng.audit.entries())   # no silent re-run on restart


def test_changed_records_trigger_fresh_run(eng, tmp_path):
    eng.apply_event(Event(type="new_product_version", data={"product_id": "prod-swiftsave", "version": "1.4"}))
    new = tmp_path / "records.json"
    new.write_text(RECORDS.read_text().replace("Harbourline", "Harbourline v2"))
    e2 = Engine.open(new, tmp_path / "audit.jsonl", tmp_path / "state.json")
    assert e2.product.launch_version == "2.0" and not e2.history


def test_bad_bundle_gives_clear_error():
    data = json.loads(RECORDS.read_text())
    data["scenario"]["product_id"] = "nope"
    with pytest.raises(ValueError, match="not in entities.products"):
        Bundle.model_validate(data)
    data = json.loads(RECORDS.read_text())
    data["records"][0]["id"] = "p-tom"
    with pytest.raises(ValueError, match="duplicate ids"):
        Bundle.model_validate(data)


def test_bad_event_changes_nothing(eng):
    before = eng.bundle.model_dump_json()
    with pytest.raises(ValueError):
        eng.apply_event(Event(type="resignation", data={"person_id": "p-ghost", "leaving_on": "2026-12-01"}))
    assert eng.bundle.model_dump_json() == before


def test_agent_drafts_and_human_approval(eng):
    pending = {d.id for d in eng.drafts.values() if d.status == "pending"}
    assert "reassign_owner:orphaned_owner:p-priya" in pending
    # the leaving owner is not notified about her own departure; she gets a reassign draft instead
    # nobody is notified who is leaving: Priya's seams route to her manager, and fixtures have none
    assert len([d for d in pending if d.startswith("notify_owner:")]) == 3
    maya = SignOff(decision="waive", signer_name="Maya Lin", signer_role="Launch Director", reason="successor agreed")
    eng.sign(SignOff(decision="waive", seam_id="training_lapse:leg-dpo-cert", signer_name="Maya Lin",
                     signer_role="Launch Director", reason="renewal booked"))
    assert eng.drafts["notify_owner:training_lapse:leg-dpo-cert"].status == "obsolete"
    with pytest.raises(GovernanceError, match="owner_id"):
        eng.decide_draft("reassign_owner:orphaned_owner:p-priya", True, maya)
    out = eng.decide_draft("reassign_owner:orphaned_owner:p-priya", True, maya, {"owner_id": "p-james"})
    assert out["draft"]["status"] == "approved"
    assert "orphaned_owner:p-priya" not in eng.seams
    assert all(r.owner_id != "p-priya" for r in eng.bundle.records if r.department != "HR")
    with pytest.raises(GovernanceError, match="not pending"):
        eng.decide_draft("reassign_owner:orphaned_owner:p-priya", True, maya, {"owner_id": "p-james"})
    assert eng.audit.verify()["ok"]

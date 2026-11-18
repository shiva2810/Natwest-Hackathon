import json

import pytest

from seam import store
from seam.extract import build_bundle
from seam.extract.clauses import parse_clauses
from seam.extract.llm_extract import quote_ok
from seam.extract.tables import ExtractionError, parse_parameters
from seam.llm import CachedLLM
from seam.sources import EventError, apply_event, load_dataset


@pytest.fixture
def ds():
    return load_dataset()


def test_counts_match_dataset_readme(ds):
    b, rep = build_bundle(ds)
    assert rep["records_by_department"] == {"HR": 5, "Finance": 4, "Legal": 10}
    e = b.entities
    assert (len(e.people), len(e.vendors), len(e.contracts), len(e.staffing)) == (28, 7, 8, 18)


def test_every_quote_is_verbatim(ds):
    b, rep = build_bundle(ds)
    assert rep["quote_check"]["failed"] == [] and rep["quote_check"]["checked"] == 19
    assert all(r.evidence and r.evidence[0].quote for r in b.records)


def test_permissions_and_facts_are_not_obligations(ds):
    _, rep = build_bundle(ds)
    skipped = {s["ref"] for s in rep["policy_text"]["skipped_non_binding"]}
    assert "hr/hr_policy_excerpt.md#5.1" in skipped          # "may work remotely"
    assert [u["ref"] for u in rep["policy_text"]["unmapped"]] == ["finance/finance_policy_excerpt.md#5.1"]


def test_parameters_extracted(ds):
    b, _ = build_bundle(ds)
    by = {r.id: r for r in b.records}
    assert by["HR-4.2"].attributes["course"] == "DPA-110" and by["HR-4.2"].attributes["validity_months"] == 12
    assert by["HR-7.1"].attributes == {**by["HR-7.1"].attributes, "department": "Support", "until": "2027-03-31"}
    assert by["FIN-3.3"].attributes["threshold_gbp"] == 40000
    assert by["OBL-L-003"].attributes["allowed_regions"] == ["UK", "EEA"]
    assert by["OBL-L-005"].attributes["min_hours_per_week"] == 336
    assert by["OBL-L-002"].attributes["self_attested"] == "compliant" and by["OBL-L-002"].status == "unknown"


def test_entities_carry_the_facts_the_seams_need(ds):
    b, _ = build_bundle(ds)
    e = b.entities
    meera = next(p for p in e.people if p.id == "E004")
    assert meera.status == "serving_notice" and str(meera.leaving_on) == "2026-11-27" and meera.active
    assert next(v for v in e.vendors if v.id == "V002").processing_region == "US-East"
    prod = e.products[0]
    assert (prod.launch_version, prod.approval.approved_version, prod.change_control_filed) == ("2.0", "1.4", False)
    assert sum(c.material for c in prod.changes) == 3


def test_replay_all_events(ds):
    for ev in ds.events:
        apply_event(ds, ev)
    b, rep = build_bundle(ds)
    assert rep["events_applied"] == ["EV-01", "EV-02", "EV-03", "EV-04", "EV-05", "EV-06"]
    assert str(b.scenario.as_of) == "2026-11-30"
    assert "V007" in {v.id for v in b.entities.vendors}
    assert next(p for p in b.entities.people if p.id == "E004").active is False
    assert next(r for r in b.records if r.id == "OBL-L-001").owner_id == "E010"
    assert b.entities.products[0].approval.accountable_senior_manager_id == "E010"


def test_bad_event_is_atomic(ds):
    before = json.dumps(ds.tables, sort_keys=True)
    bad = {"event_id": "X", "changes": [
        {"file": "hr/roster.csv", "op": "update", "match": {"employee_id": "E001"}, "set": {"status": "left"}},
        {"file": "hr/roster.csv", "op": "update", "match": {"employee_id": "E999"}, "set": {"status": "left"}}]}
    with pytest.raises(EventError):
        apply_event(ds, bad)
    assert json.dumps(ds.tables, sort_keys=True) == before


def test_missing_file_is_a_clear_error(ds):
    del ds.tables["hr/roster.csv"]
    with pytest.raises(ExtractionError, match="hr/roster.csv"):
        build_bundle(ds)


def test_llm_quote_check_rejects_hallucination(ds, tmp_path):
    hr_text = ds.texts["hr/hr_policy_excerpt.md"]

    def fake_provider(prompt):
        if "hr_policy" not in prompt:
            return "[]"
        return json.dumps([
            {"clause": "4.1", "quote": "All employees must complete Code of Conduct training (course COC-100) "
                                       "at least every 12 months.", "kind": "mandatory_training",
             "parameters": {"course": "COC-100", "validity_months": 12}},
            {"clause": "4.2", "quote": "Employees must complete GDPR training every 6 months.",   # invented
             "kind": "mandatory_training"},
            {"clause": "9.9", "quote": "A department must not exceed its approved headcount.", "kind": "headcount_cap"},
        ])

    llm = CachedLLM(fake_provider, cache_dir=tmp_path)
    b, rep = build_bundle(ds, llm=llm)
    hr = [r for r in b.records if r.department == "HR"]
    assert [r.id for r in hr] == ["HR-4.1"] and hr[0].extracted_by == "llm"
    whys = sorted(x["why"] for x in rep["llm"]["rejected"])
    assert whys == ["clause '9.9' does not exist in hr/hr_policy_excerpt.md", "quote is not verbatim in the source"]
    assert "HR-4.2" in rep["llm"]["files"]["hr/hr_policy_excerpt.md"]["only_rule"]
    assert rep["quote_check"]["failed"] == []

    offline = CachedLLM(None, cache_dir=tmp_path)            # same prompts, no provider: served from cache
    b2, _ = build_bundle(ds, llm=offline)
    assert offline.hits == 2 and [r.id for r in b2.records if r.department == "HR"] == ["HR-4.1"]


def test_offline_cache_miss_falls_back_to_rules(ds, tmp_path):
    b, rep = build_bundle(ds, llm=CachedLLM(None, cache_dir=tmp_path))
    assert rep["records_by_department"] == {"HR": 5, "Finance": 4, "Legal": 10}
    assert all("fallback" in v for v in rep["llm"]["files"].values())


def test_store_roundtrip_and_query(ds, tmp_path):
    b, rep = build_bundle(ds)
    p = store.save(b, tmp_path / "records.json", rep)
    again = store.load(p)
    assert len(store.query(again, department="Legal", attr__evidence_status="held_by_other_dept")) == 5
    assert (tmp_path / "records.report.json").exists()


def test_helpers():
    assert parse_parameters("course=PCT-101; validity_months=12; allowed_regions=UK,EEA") == {
        "course": "PCT-101", "validity_months": 12, "allowed_regions": ["UK", "EEA"]}
    assert quote_ok("All  employees MUST complete", "**4.1** All employees must complete it")
    assert not quote_ok("short", "short text")
    cl = parse_clauses("legal/x.md", "# Legal Policies (excerpt) - Co\n## Conduct Policy\n**5.3** Only staff must.")
    assert (cl[0].doc, cl[0].number) == ("Conduct Policy", "5.3")

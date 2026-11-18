"""The three landing cases: HR passes, Legal passes, yet together they conflict. All read live from the engine."""
import pytest

from seam.conflicts import CASES, conflicts
from seam.engine import Engine
from seam.governance import ROOT


@pytest.fixture
def eng(tmp_path):
    e = Engine(ROOT / "data", tmp_path / "a.jsonl", tmp_path / "s.json")
    e.run()
    return e


def test_three_cases_each_pass_alone_but_conflict_together(eng):
    cases = conflicts(eng.passport())
    assert len(cases) == 3 == len(CASES)
    for c in cases:
        assert c["hr_side"]["result"] == "passed" and c["legal_side"]["result"] == "passed", c["id"]
        assert c["both_pass"] and c["state"] == "conflict"
        assert {"HR", "Legal"} <= set(c["seam_data"]["departments"])


def test_cards_follow_the_data(eng):
    eng.apply_scenario("fix_seller_training")                 # the three sellers complete PCT-101
    states = {c["id"]: c["state"] for c in conflicts(eng.passport())}
    assert states["seller-training"] == "resolved"
    assert states["leaver-owner"] == states["support-hours"] == "conflict"


def test_missing_records_are_reported_not_faked():
    p = {"records": [], "seams": [], "scenarios": []}
    assert all(c["hr_side"]["result"] == "missing" and c["state"] == "resolved" and not c["both_pass"]
               for c in conflicts(p))

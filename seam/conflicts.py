"""The three headline cases: HR passes, Legal passes, yet together they conflict.

Each case pairs one HR record and one Legal record that both pass on their own with the cross-department
seam that only appears when their data are read together. Everything shown is read live from the passport,
so nothing is staged: if a record stops passing, or an event closes the seam, the card changes with it.
"""
from __future__ import annotations

from typing import Any

CASES = [
    {"id": "leaver-owner", "title": "The accountable manager is leaving before launch",
     "hr": "HR-6.2", "legal": "OBL-L-009", "seam": "orphaned_owner:E004",
     "why": "HR followed its leaver process, and Legal has a named accountable manager on file. "
            "They are the same person, and Legal's records never learn that they leave on 27 Nov.",
     "fix_hint": "Approve the agent's reassign-owner draft under Sign-off."},
    {"id": "seller-training", "title": "Sellers start selling before they are trained",
     "hr": "HR-4.1", "legal": "OBL-L-002", "seam": "seller_training_gap:OBL-L-002", "scenario": "fix_seller_training",
     "why": "HR's training programme is current and Legal's conduct obligation is marked compliant. "
            "But the Conduct Policy needs PCT-101 on the day of sale, and HR's staffing plan has sellers starting without it.",
     "fix_hint": "Complete PCT-101 for the three sellers before their first sales date."},
    {"id": "support-hours", "title": "Legal promised 24x7 support that HR cannot staff",
     "hr": "HR-7.1", "legal": "OBL-L-005", "seam": "support_capacity_gap:OBL-L-005", "scenario": "fix_support_capacity",
     "why": "HR respects the Support hiring freeze and Legal's customer terms promise 24x7 cover. "
            "Each is fine alone; the promised hours exceed the staffed hours once you compare them.",
     "fix_hint": "Approve a freeze exception and hire, or amend the customer terms."},
]
RESULT = {"met": "passed", "unmet": "failed", "unknown": "needs_review"}


def _side(rec: dict | None, rid: str) -> dict[str, Any]:
    if rec is None:
        return {"record": rid, "result": "missing", "description": "", "finding": "record not found in this review"}
    check = rec.get("attributes", {}).get("check") or {}
    return {"record": rid, "result": RESULT.get(rec["status"], "needs_review"), "description": rec["description"],
            "finding": check.get("finding") or ""}


def conflicts(p: dict[str, Any]) -> list[dict[str, Any]]:
    """One entry per case. `state` is conflict (seam open), waived, or resolved (seam gone)."""
    recs = {r["id"]: r for r in p.get("records", [])}
    seams = {s["id"]: s for s in p["seams"]}
    scen = {s["name"]: s for s in p.get("scenarios", [])}
    out = []
    for i, c in enumerate(CASES, 1):
        s = seams.get(c["seam"])
        state = "resolved" if s is None else "waived" if s["status"] == "waived" else "conflict"
        hr, legal = _side(recs.get(c["hr"]), c["hr"]), _side(recs.get(c["legal"]), c["legal"])
        out.append({**c, "n": i, "hr_side": hr, "legal_side": legal, "seam_data": s, "state": state,
                    "scenario_info": scen.get(c.get("scenario", "")),
                    "both_pass": hr["result"] == "passed" and legal["result"] == "passed"})
    return out

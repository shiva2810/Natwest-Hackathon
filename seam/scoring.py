"""Severity and priority scoring (component 4.3). Transparent on purpose: every point is explainable."""
from __future__ import annotations

from datetime import date

from .rules import Seam

# Severity is a policy decision per seam type, written down here so it is reviewable. Types not listed
# get severity from the score. blocks_launch: can the launch go ahead while the seam is open?
SEVERITY = {
    "data_residency_breach": "critical",   # contract breach on every customer from day one
    "version_drift": "high",
    "orphaned_owner": "high",
    "support_capacity_gap": "high",
    "seller_training_gap": "high",
}
NON_BLOCKING = {"seller_training_gap"}     # untrained sellers can be kept off sales; launch itself can proceed

BASE = {
    "data_residency_breach": 90,
    "support_capacity_gap": 70,
    "seller_training_gap": 60,
    "version_drift": 85,          # launching something nobody approved
    "unvetted_vendor": 75,        # customer money through an uncleared vendor
    "approval_limit_breach": 65,
    "orphaned_owner": 60,
    "unbudgeted_contract": 55,
    "training_lapse": 50,
}


def score(seam: Seam, as_of: date, launch: date) -> Seam:
    s = BASE.get(seam.type, 50)
    reasons = [f"base {s} for {seam.type}"]

    bites = seam.effective_on or launch
    days = (bites - as_of).days
    if days <= 0:
        s += 15; reasons.append("+15 already in effect")
    elif days <= 14:
        s += 10; reasons.append(f"+10 bites in {days} days")
    elif days <= 30:
        s += 5; reasons.append(f"+5 bites in {days} days")

    extra_depts = max(0, len(seam.departments) - 2)
    if extra_depts:
        s += 5 * extra_depts; reasons.append(f"+{5 * extra_depts} spans {len(seam.departments)} departments")

    if len(seam.record_ids) > 1:
        s += 5; reasons.append(f"+5 affects {len(seam.record_ids)} obligations")

    s = min(s, 100)
    seam.score = s
    seam.severity = SEVERITY.get(seam.type) or (
        "critical" if s >= 85 else "high" if s >= 70 else "medium" if s >= 50 else "low")
    seam.blocks_launch = seam.type not in NON_BLOCKING
    seam.facts["score_reasons"] = reasons
    return seam


def rank(seams: list[Seam], as_of: date, launch: date) -> list[Seam]:
    return sorted((score(s, as_of, launch) for s in seams), key=lambda s: (-s.score, s.id))

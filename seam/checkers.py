"""Department checkers (layer 3, components 3.1-3.3).

Each checker sees ONLY its own department's data (a DeptView), mirroring the dataset's isolation
rule: anything that needs two departments is, by design, a seam and belongs to the seam detector.

Each check sets a record's status and writes `attributes.check` = {basis, finding, items}:
  basis "data"          verified against the department's own records
  basis "self_attested" the department cannot verify it alone (evidence held by another
                        department); status mirrors the owner's own claim. This is the blind spot
                        the seam detector exists to expose.
  basis "no_evidence"   evidence missing and not yet due -> "unknown". Never guess met or unmet.
Records of kinds with no checker keep their status (fixtures arrive pre-checked).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from .schema import Bundle, ObligationRecord


@dataclass
class DeptView:
    as_of: date
    data: dict[str, Any]


def views(b: Bundle) -> dict[str, DeptView]:
    e = b.entities
    prod = next((p for p in e.products if p.id == b.scenario.product_id), None)
    return {
        "HR": DeptView(b.scenario.as_of, {"people": e.people, "staffing": e.staffing, "headcount": e.headcount}),
        "Finance": DeptView(b.scenario.as_of, {"vendors": e.vendors, "limits": e.approval_limits,
                                               "pos": e.purchase_orders, "budget": e.budget_lines}),
        "Legal": DeptView(b.scenario.as_of, {"contracts": e.contracts,
                                             "approval": prod.approval if prod else None}),
    }


def _set(r: ObligationRecord, status: str, basis: str, finding: str, items: list | None = None):
    r.status = status  # type: ignore[assignment]
    r.attributes["check"] = {"basis": basis, "finding": finding, "items": items or []}


def _valid_on(t, day: date) -> bool:
    return t.completed_on is not None and t.status != "not_started" and (t.expires_on is None or t.expires_on > day)


# ---------- HR (3.1): reads roster, training, staffing, headcount only ----------

def hr_headcount_cap(r, v):
    over = [f"{h.department}: {h.filled_heads}/{h.approved_heads}" for h in v.data["headcount"]
            if h.filled_heads > h.approved_heads]
    _set(r, "unmet" if over else "met", "data",
         f"{len(over)} department(s) over approved headcount" if over else "every department within approved headcount", over)


def hr_mandatory_training(r, v):
    course = r.attributes.get("course")
    missing = [f"{p.id} {p.name}" for p in v.data["people"] if p.active
               and not any(t.course == course and _valid_on(t, v.as_of) for t in p.trainings)]
    _set(r, "unmet" if missing else "met", "data",
         f"{len(missing)} active employee(s) without valid {course}" if missing
         else f"all active employees hold valid {course}", missing)


def hr_leaver_handover(r, v):
    leavers = [p for p in v.data["people"] if p.status == "serving_notice"]
    _set(r, "met", "data",
         f"{len(leavers)} leaver(s) serving notice; HR checklist covers HR-owned systems only - duties held in "
         "other departments' systems are not visible to HR", [f"{p.id} {p.name} (last day {p.leaving_on})" for p in leavers])


def hr_hiring_freeze(r, v):
    dept = r.attributes.get("department")
    plan = next((h for h in v.data["headcount"] if h.department == dept), None)
    if plan is None:
        return _set(r, "unknown", "no_evidence", f"no headcount plan for {dept}")
    breach = plan.open_reqs > 0 or plan.filled_heads > plan.approved_heads
    _set(r, "unmet" if breach else "met", "data",
         f"{dept} frozen until {plan.frozen_until}: {plan.open_reqs} open reqs, "
         f"{plan.filled_heads}/{plan.approved_heads} filled")


# ---------- Finance (3.2): reads budget, vendors, approval limits, purchase orders only ----------

def fin_budget_cap(r, v):
    over = [f"{b.id} {b.line_item}: committed {b.committed:,.0f} > approved {b.approved:,.0f}"
            for b in v.data["budget"] if b.committed > b.approved]
    _set(r, "unmet" if over else "met", "data",
         f"{len(over)} budget line(s) over-committed" if over else "all budget lines within approved amounts", over)


def _limit_of(v, person_id: str, on: date | None):
    return max((l.limit for l in v.data["limits"] if l.approver_id == person_id
                and (on is None or ((l.valid_from is None or l.valid_from <= on) and (l.valid_to is None or l.valid_to >= on)))),
               default=0.0)


def fin_po_approval_limit(r, v):
    bad = []
    for po in v.data["pos"]:
        if po.status != "approved" or not po.approver_id:
            continue
        lim = _limit_of(v, po.approver_id, po.approved_on)
        if lim < po.amount:
            bad.append(f"{po.id} {po.amount:,.0f} approved by {po.approver_id} (limit {lim:,.0f})")
    _set(r, "unmet" if bad else "met", "data",
         f"{len(bad)} PO(s) approved above the approver's limit" if bad else "every approved PO within its approver's limit", bad)


def fin_asm_spend(r, v):
    threshold = float(r.attributes.get("threshold_gbp", 40000))
    asms = {l.approver_id for l in v.data["limits"] if "accountable senior manager" in l.role_title.lower()}
    bad = [f"{po.id} {po.amount:,.0f} ({po.product}) approved by {po.approver_id}, not the ASM"
           for po in v.data["pos"] if po.status == "approved" and po.product and po.product != "Corporate"
           and po.amount > threshold and po.approver_id not in asms]
    _set(r, "unmet" if bad else "met", "data",
         f"{len(bad)} product PO(s) above {threshold:,.0f} without ASM approval" if bad
         else f"product spend above {threshold:,.0f} approved by the ASM", bad)


def fin_supplier_dd(r, v):
    vendors = {x.id: x for x in v.data["vendors"]}
    bad = []
    for po in v.data["pos"]:
        if po.status != "approved":
            continue
        vd = vendors.get(po.vendor_id)
        if vd is None or vd.due_diligence != "complete" or (vd.dd_completed_on and po.approved_on and vd.dd_completed_on > po.approved_on):
            bad.append(f"{po.id} to {po.vendor_id}: DD {getattr(vd, 'due_diligence', 'missing')} "
                       f"({getattr(vd, 'dd_completed_on', None)}) vs PO approved {po.approved_on}")
    _set(r, "unmet" if bad else "met", "data",
         f"{len(bad)} PO(s) approved before supplier due diligence" if bad
         else "due diligence completed before every approved PO", bad)


# ---------- Legal (3.3): reads its register, contracts register and product approval only ----------

def legal_approval(r, v):
    ap = v.data["approval"]
    if ap is None:
        return _set(r, "unknown", "no_evidence", "no product approval on file")
    ok = ap.valid_until is None or ap.valid_until > v.as_of
    _set(r, "met" if ok else "unmet", "data",
         f"approval {ap.id} for v{ap.approved_version} valid until {ap.valid_until}")


def legal_policy_review(r, v):
    months = int(r.attributes.get("review_frequency_months", 12))
    last = r.attributes.get("last_reviewed")
    if not last:
        return _set(r, "unknown", "no_evidence", "no review date recorded")
    d = date.fromisoformat(last)
    due = date(d.year + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1, min(d.day, 28))
    _set(r, "met" if due > v.as_of else "unmet", "data", f"last reviewed {last}; next review due {due}")


def legal_reg_notification(r, v):
    if r.attributes.get("evidence_status") == "provided":
        return _set(r, "met", "data", f"filed: {r.attributes.get('evidence_location')}")
    due = r.attributes.get("due_date")
    if due and date.fromisoformat(due) < v.as_of:
        return _set(r, "unmet", "data", f"notification due {due} and not on file")
    _set(r, "unknown", "no_evidence", f"notification not on file yet; due {due}, so not overdue")


def legal_contract_validity(r, v):
    lapsed = [f"{c.id} {c.title} ended {c.end_date}" + (f" ({c.notes})" if c.notes else "")
              for c in v.data["contracts"] if c.end_date and c.end_date < v.as_of]
    _set(r, "unmet" if lapsed else "met", "data",
         f"{len(lapsed)} contract(s) past end date" if lapsed else "all contracts in date", lapsed)


def legal_dpa(r, v):
    bad = [f"{c.id} {c.title}" for c in v.data["contracts"] if c.dpa_required and not c.dpa_signed]
    _set(r, "unmet" if bad else "met", "data",
         f"{len(bad)} contract(s) need a DPA that is not signed" if bad else "every contract needing a DPA has one", bad)


def legal_self_attested(r, v):
    claim = r.attributes.get("self_attested", "")
    status = "met" if claim == "compliant" else "unmet" if claim == "non_compliant" else "unknown"
    _set(r, status, "self_attested",
         f"owner attests '{claim}'; evidence is held by another department "
         f"({r.attributes.get('evidence_location')}), so Legal cannot verify it alone")


CHECKS: dict[tuple[str, str], Callable] = {
    ("HR", "headcount_cap"): hr_headcount_cap,
    ("HR", "mandatory_training"): hr_mandatory_training,
    ("HR", "leaver_handover"): hr_leaver_handover,
    ("HR", "hiring_freeze"): hr_hiring_freeze,
    ("Finance", "budget_cap"): fin_budget_cap,
    ("Finance", "po_approval_limit"): fin_po_approval_limit,
    ("Finance", "asm_spend_approval"): fin_asm_spend,
    ("Finance", "supplier_dd_before_po"): fin_supplier_dd,
    ("Legal", "approval"): legal_approval,
    ("Legal", "policy_review"): legal_policy_review,
    ("Legal", "regulatory_notification"): legal_reg_notification,
    ("Legal", "contract_validity"): legal_contract_validity,
    ("Legal", "dpa"): legal_dpa,
}


def run_checks(b: Bundle) -> dict[str, Any]:
    """Set status on every checkable record in place. Returns a summary per department."""
    vs = views(b)
    summary: dict[str, dict[str, int]] = {}
    for r in b.records:
        fn = CHECKS.get((r.department, r.kind))
        if fn is None and r.department == "Legal" and r.attributes.get("evidence_status") == "held_by_other_dept":
            fn = legal_self_attested
        if fn is None:
            continue
        fn(r, vs[r.department])
        s = summary.setdefault(r.department, {"met": 0, "unmet": 0, "unknown": 0})
        s[r.status] += 1
    return summary

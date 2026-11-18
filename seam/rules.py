"""Deterministic seam rules (component 4.2). NEVER CUT: these are the demo.

A seam is a gap that only shows up when two or more departments' data are read together.
Each rule is a pure function of the graph and returns Seam objects with the facts that prove it.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Literal

import networkx as nx
from pydantic import BaseModel, Field

from .graph import neighbours, nodes_of
from .schema import Bundle

Severity = Literal["critical", "high", "medium", "low"]


class Seam(BaseModel):
    id: str                                  # "<type>:<anchor>", stable across runs
    type: str
    anchor: str                              # node the seam hangs off
    title: str
    departments: list[str]
    nodes: list[str]                         # every node involved (for re-check and the UI)
    record_ids: list[str] = Field(default_factory=list)
    fix_owner_id: str | None = None          # who should act
    effective_on: date | None = None         # when the gap bites
    facts: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = "medium"
    score: float = 0.0
    explanation: str = ""
    fix_options: list[str] = Field(default_factory=list)
    status: Literal["open", "waived"] = "open"
    waiver: dict[str, Any] | None = None
    basis: list[str] = Field(default_factory=list)   # EU law vs internal policy (never present policy as law)
    blocks_launch: bool = True                        # False: fix before the gap bites, launch can proceed


def _product(bundle: Bundle):
    return next(p for p in bundle.entities.products if p.id == bundle.scenario.product_id)


# ---------- the five seam types ----------

def orphaned_owner(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """S1. Someone HR shows leaving before launch still holds roles other departments rely on:
    obligations they own (Legal/Finance), accountable senior manager on the approval, product owner,
    pending purchase orders routed to them, or sole approver for a spending scope (Finance)."""
    launch = _product(b).launch_date
    people = {p.id: p for p in b.entities.people}

    def gone(pid: str | None) -> bool:
        p = people.get(pid or "")
        return p is not None and (not p.active or (p.leaving_on is not None and p.leaving_on <= launch))

    out = []
    for pid, person in nodes_of(g, "person"):
        if not gone(pid):
            continue
        roles: list[str] = []
        nodes: list[str] = [pid]
        depts = {"HR"}
        owned = [(rid, r) for rid, r in neighbours(g, pid, "owned_by", incoming=True) if r.department != "HR"]
        for rid, r in owned:
            roles.append(f"owner of {rid}: {r.description[:70]}")
            nodes.append(rid)
            depts.add(r.department)
        for prid, pr in neighbours(g, pid, "asm", incoming=True):
            roles.append(f"accountable senior manager on approval {pr.approval.id if pr.approval else ''} for {pr.name}")
            nodes.append(prid); depts.add("Legal")
        for prid, pr in neighbours(g, pid, "product_owner", incoming=True):
            roles.append(f"product owner of {pr.name}")
            nodes.append(prid); depts.add("Product")
        for poid, po in neighbours(g, pid, "approver", incoming=True):
            if g.nodes[poid]["type"] == "purchase_order" and po.status == "pending_approval":
                roles.append(f"approver of pending {poid} ({po.amount:,.0f}, {po.description})")
                nodes.append(poid); depts.add("Finance")
            elif g.nodes[poid]["type"] == "approval_limit":
                al = po
                if al.valid_to is not None and al.valid_to < launch:
                    continue
                others = [x for x in b.entities.approval_limits if x.scope == al.scope and x.approver_id != pid
                          and not gone(x.approver_id) and (x.valid_from is None or x.valid_from <= launch)]
                delegate_ok = al.delegate_id is not None and not gone(al.delegate_id)
                if not others and not delegate_ok:
                    roles.append(f"sole approver for '{al.scope}' (limit {al.limit:,.0f}, no delegate)")
                    nodes.append(poid); depts.add("Finance")
        if not roles:
            continue
        when = "is no longer active" if not person.active else f"leaves on {person.leaving_on}"
        out.append(Seam(
            id=f"orphaned_owner:{pid}", type="orphaned_owner", anchor=pid,
            title=f"{person.name} {when} but still holds {len(roles)} role(s) needed at launch",
            departments=sorted(depts), nodes=nodes, record_ids=[rid for rid, _ in owned],
            effective_on=person.leaving_on, facts={
                "person": person.name, "role": person.role, "active": person.active,
                "leaving_on": str(person.leaving_on), "launch_date": str(launch), "roles": roles,
                "obligations": [r.description for _, r in owned]},
        ))
    return out


def version_drift(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """S5. Legal approved one product version; the launch ships another (with material changes)."""
    out = []
    for prid, prod in nodes_of(g, "product"):
        ap = prod.approval
        if ap is None or ap.approved_version == prod.launch_version:
            continue
        material = [c for c in prod.changes if c.material]
        anchor_rec = next((rid for rid, r in nodes_of(g, "obligation") if r.kind == "approval"
                           and r.product_id == prid), None)
        cc = [rid for rid, r in nodes_of(g, "obligation") if r.kind == "change_control"]
        out.append(Seam(
            id=f"version_drift:{anchor_rec or prid}", type="version_drift", anchor=anchor_rec or prid,
            title=f"Approval {ap.id} covers v{ap.approved_version} but {prod.name} launches v{prod.launch_version} "
                  f"with {len(material)} material change(s)"
                  + ("" if prod.change_control_filed else " and no change control request"),
            departments=["Legal", "Product"], nodes=[prid, *(x for x in [anchor_rec] if x), *cc],
            record_ids=[x for x in [anchor_rec, *cc] if x], fix_owner_id=ap.accountable_senior_manager_id,
            effective_on=prod.launch_date,
            facts={"approved_version": ap.approved_version, "launch_version": prod.launch_version,
                   "product": prod.name, "approval_id": ap.id, "approval_valid_until": str(ap.valid_until),
                   "material_changes": [f"{c.id} {c.description} ({c.change_type})" for c in material],
                   "change_control_filed": prod.change_control_filed},
        ))
    for rid, r in nodes_of(g, "obligation"):
        if r.kind != "product_approval" or not r.product_id or r.product_id not in g:
            continue
        prod = g.nodes[r.product_id]["obj"]
        approved = str(r.attributes.get("approved_version", ""))
        if prod and approved != prod.launch_version:
            out.append(Seam(
                id=f"version_drift:{rid}", type="version_drift", anchor=rid,
                title=f"Approval covers v{approved or '?'} but {prod.name} launches v{prod.launch_version}",
                departments=["Legal", "Product"], nodes=[rid, prod.id], record_ids=[rid],
                fix_owner_id=r.owner_id, effective_on=prod.launch_date,
                facts={"approved_version": approved, "launch_version": prod.launch_version,
                       "product": prod.name, "evidence": [ev.model_dump(mode="json") for ev in r.evidence]},
            ))
    return out


def unvetted_vendor(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """Legal has a signed contract with a vendor Finance has not cleared (or whose DD lapses before launch)."""
    launch = _product(b).launch_date
    out = []
    for cid, c in nodes_of(g, "contract"):
        v = g.nodes[c.vendor_id]["obj"] if c.vendor_id in g else None
        if v is None:
            continue
        lapsed = v.dd_expires_on is not None and v.dd_expires_on <= launch
        if v.due_diligence == "complete" and not lapsed:
            continue
        dd_records = [rid for rid, r in neighbours(g, v.id, "about_vendor", incoming=True)
                      if r.kind == "vendor_due_diligence"]
        out.append(Seam(
            id=f"unvetted_vendor:{cid}", type="unvetted_vendor", anchor=cid,
            title=f"Contract '{c.title}' is signed but {v.name} due diligence is "
                  + (f"expiring {v.dd_expires_on}" if lapsed and v.due_diligence == "complete" else v.due_diligence),
            departments=["Finance", "Legal"], nodes=[cid, v.id, *dd_records], record_ids=dd_records,
            fix_owner_id=c.signed_by, effective_on=launch,
            facts={"contract": c.title, "value": c.value, "vendor": v.name,
                   "due_diligence": v.due_diligence, "dd_expires_on": str(v.dd_expires_on),
                   "launch_date": str(launch)},
        ))
    return out


def training_lapse(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """An obligation (usually Legal) needs its owner trained; HR records show no valid training at launch."""
    launch = _product(b).launch_date
    out = []
    for rid, r in nodes_of(g, "obligation"):
        if r.kind != "training_required" or not r.owner_id or r.owner_id not in g:
            continue
        person = g.nodes[r.owner_id]["obj"]
        if person is None:
            continue
        course = r.attributes.get("course")
        held = [t for t in person.trainings if t.course == course and t.completed_on]
        valid = [t for t in held if t.expires_on is None or t.expires_on > launch]
        if valid:
            continue
        expires = max((t.expires_on for t in held if t.expires_on), default=None)
        depts = sorted({"HR", r.department})
        if depts == ["HR"]:
            continue  # HR's own training gap is a department finding, not a seam
        out.append(Seam(
            id=f"training_lapse:{rid}", type="training_lapse", anchor=rid,
            title=f"{person.name} must hold {course} but it "
                  + (f"expires {expires}, before launch" if held else "is not on record"),
            departments=depts, nodes=[rid, person.id], record_ids=[rid],
            fix_owner_id=person.id, effective_on=expires or launch,
            facts={"person": person.name, "course": course, "expires_on": str(expires),
                   "launch_date": str(launch), "requirement": r.description,
                   "quote": next((ev.quote for ev in r.evidence if ev.quote), None)},
        ))
    return out


def approval_limit_breach(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """Legal holds a contract signed by someone whose Finance approval limit is lower than its value."""
    out = []
    for cid, c in nodes_of(g, "contract"):
        if not c.signed_by or c.signed_by not in g:
            continue
        signer = g.nodes[c.signed_by]["obj"]
        if signer is None or c.value <= signer.approval_limit:
            continue
        out.append(Seam(
            id=f"approval_limit_breach:{cid}", type="approval_limit_breach", anchor=cid,
            title=f"{signer.name} signed '{c.title}' for £{c.value:,.0f}; limit is £{signer.approval_limit:,.0f}",
            departments=["Finance", "HR", "Legal"], nodes=[cid, signer.id], record_ids=[],
            fix_owner_id=signer.id, effective_on=_product(b).launch_date,
            facts={"signer": signer.name, "role": signer.role, "value": c.value,
                   "approval_limit": signer.approval_limit, "contract": c.title},
        ))
    return out


def unbudgeted_contract(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """Bonus rule: a signed contract with no Finance budget line covering its value."""
    out = []
    for cid, c in nodes_of(g, "contract"):
        lines = [r for _, r in neighbours(g, cid, "about_contract", incoming=True) if r.kind == "budget_line"]
        budget = sum(float(r.attributes.get("amount", 0)) for r in lines)
        if budget >= c.value:
            continue
        out.append(Seam(
            id=f"unbudgeted_contract:{cid}", type="unbudgeted_contract", anchor=cid,
            title=f"'{c.title}' is £{c.value:,.0f} but only £{budget:,.0f} is budgeted",
            departments=["Finance", "Legal"], nodes=[cid], fix_owner_id=c.signed_by,
            effective_on=_product(b).launch_date,
            facts={"contract": c.title, "value": c.value, "budgeted": budget},
        ))
    return out


def _sale_date(prod, staffing) -> date:
    return staffing.selling_from or prod.first_sales_date or prod.launch_date


def seller_training_gap(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """S2. Legal requires sellers to hold a course on the date of sale; HR's records show sellers who won't."""
    out = []
    people = {p.id: p for p in b.entities.people}
    for rid, r in nodes_of(g, "obligation"):
        if r.kind != "training" or not r.attributes.get("course"):
            continue
        course = r.attributes["course"]
        prod = g.nodes[r.product_id]["obj"] if r.product_id in g else _product(b)
        gaps, nodes = [], [rid, prod.id]
        for s in b.entities.staffing:
            if s.product != prod.name or not s.can_sell or s.person_id not in people:
                continue
            p, day = people[s.person_id], _sale_date(prod, s)
            held = [t for t in p.trainings if t.course == course]
            ok = any(t.completed_on and t.status != "not_started" and (t.expires_on is None or t.expires_on > day)
                     for t in held)
            if ok:
                continue
            why = ("not started" if not held or all(t.status == "not_started" for t in held)
                   else f"expires {max((t.expires_on for t in held if t.expires_on), default=None)}")
            gaps.append(f"{p.id} {p.name}: {course} {why}, first sale {day}")
            nodes.append(p.id)
        if gaps:
            out.append(Seam(
                id=f"seller_training_gap:{rid}", type="seller_training_gap", anchor=rid,
                title=f"{len(gaps)} seller(s) will not hold valid {course} on their first sales date",
                departments=["HR", "Legal"], nodes=nodes, record_ids=[rid], fix_owner_id=r.owner_id,
                effective_on=min((_sale_date(prod, s) for s in b.entities.staffing if s.can_sell), default=prod.launch_date),
                facts={"course": course, "requirement": r.description, "sellers_without_valid_training": gaps,
                       "hr_mandatory_list_includes_course": False},
            ))
    return out


REGION_GROUP = {"UK": "UK", "EU": "EEA", "EEA": "EEA"}


def data_residency_breach(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """S3. Customer terms promise processing only in allowed regions; Finance's vendor master shows
    a supplier in the product's data flows processing elsewhere. Legal sees only a signed DPA."""
    out = []
    contracts_by_vendor: dict[str, list] = {}
    for c in b.entities.contracts:
        contracts_by_vendor.setdefault(c.vendor_id, []).append(c)
    for rid, r in nodes_of(g, "obligation"):
        if r.kind != "data_residency":
            continue
        allowed = r.attributes.get("allowed_regions") or []
        allowed = [allowed] if isinstance(allowed, str) else allowed
        prod = g.nodes[r.product_id]["obj"] if r.product_id in g else _product(b)
        breaches, nodes = [], [rid, prod.id]
        for f in prod.data_flows:
            v = g.nodes[f.vendor_id]["obj"] if f.vendor_id in g else None
            if v is None:
                continue
            group = REGION_GROUP.get((v.processing_region or "").split("-")[0].upper())
            if group in allowed:
                continue
            dpa = [f"{c.id} DPA signed={c.dpa_signed}" for c in contracts_by_vendor.get(v.id, [])]
            breaches.append(f"{v.id} {v.name}: {f.data_category} processed in {v.processing_region} "
                            f"({v.country}); {', '.join(dpa) or 'no contract'}")
            nodes.append(v.id)
        if breaches:
            out.append(Seam(
                id=f"data_residency_breach:{rid}", type="data_residency_breach", anchor=rid,
                title=f"{len(breaches)} supplier(s) process customer data outside {'/'.join(allowed)}, "
                      "against the customer terms",
                departments=["Finance", "Legal", "Product"], nodes=nodes, record_ids=[rid], fix_owner_id=r.owner_id,
                effective_on=prod.launch_date,
                facts={"promise": r.description, "allowed_regions": allowed, "breaches": breaches}))
    return out


def support_capacity_gap(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """S4. Legal promises a staffed service level; HR's staffing and Finance's budget cover fewer hours,
    and a hiring freeze stops the gap closing before launch."""
    out = []
    e = b.entities
    hours = {h.department: h for h in e.headcount}
    people = {p.id: p for p in e.people}
    for rid, r in nodes_of(g, "obligation"):
        if r.kind != "service_level" or not r.attributes.get("min_hours_per_week"):
            continue
        need = float(r.attributes["min_hours_per_week"])
        prod = g.nodes[r.product_id]["obj"] if r.product_id in g else _product(b)
        agents = [s for s in e.staffing if s.product == prod.name and "support agent" in s.role.lower()
                  and s.person_id in people and people[s.person_id].active]
        have = sum(s.allocation_pct / 100 * hours.get(people[s.person_id].department,
                   type("H", (), {"weekly_hours_per_head": 40})).weekly_hours_per_head for s in agents)
        if have >= need:
            continue
        lines = [bl for bl in e.budget_lines if bl.product == prod.name and "support" in bl.line_item.lower()
                 and bl.category == "people"]
        dept = people[agents[0].person_id].department if agents else "Support"
        plan = hours.get(dept)
        frozen = plan is not None and plan.hiring_status == "frozen" and plan.frozen_until and plan.frozen_until > prod.launch_date
        out.append(Seam(
            id=f"support_capacity_gap:{rid}", type="support_capacity_gap", anchor=rid,
            title=f"Promised {need:.0f} staffed hours/week but staffing covers {have:.0f}"
                  + (f"; {dept} hiring frozen until {plan.frozen_until}" if frozen else ""),
            departments=["Finance", "HR", "Legal"],
            nodes=[rid, prod.id, *(bl.id for bl in lines), *([f"dept:{dept}"] if plan else []),
                   *(s.person_id for s in agents)],
            record_ids=[rid], fix_owner_id=r.owner_id, effective_on=r.applies_from or prod.launch_date,
            facts={"promise": r.description, "required_hours_per_week": need, "staffed_hours_per_week": have,
                   "gap_hours": need - have, "agents": len(agents),
                   "budget_coverage": [f"{bl.id} {bl.line_item}: {bl.coverage_notes}" for bl in lines],
                   "hiring_frozen_until": str(plan.frozen_until) if frozen else None}))
    return out


BASIS = {
    "orphaned_owner": ["EU law: GDPR Art. 5(2) accountability; DORA Art. 5",
                       "Internal policy: HR 6.2 leaver handover; Finance 3.3 ASM approval"],
    "seller_training_gap": ["Internal policy: Conduct Policy 5.3 (PCT-101 on date of sale)",
                            "EU law: GDPR Art. 39(1)(b) staff training"],
    "data_residency_breach": ["Contract: Customer Terms v2.0 clause 7.2 (UK/EEA only)",
                              "EU law: GDPR Ch. V transfers; DORA Art. 30(2)(b) processing locations"],
    "support_capacity_gap": ["Contract: Customer Terms v2.0 clause 9.1 (24x7, two agents)",
                             "EU law: Working Time Directive 2003/88/EC"],
    "version_drift": ["Internal policy: Product Change Control Policy 2",
                      "EU law: DORA Art. 9 ICT change management"],
}


RULES: dict[str, Callable[[nx.MultiDiGraph, Bundle], list[Seam]]] = {
    "orphaned_owner": orphaned_owner,
    "version_drift": version_drift,
    "seller_training_gap": seller_training_gap,
    "data_residency_breach": data_residency_breach,
    "support_capacity_gap": support_capacity_gap,
    "unvetted_vendor": unvetted_vendor,
    "training_lapse": training_lapse,
    "approval_limit_breach": approval_limit_breach,
    "unbudgeted_contract": unbudgeted_contract,
}
RULES_VERSION = "rules-2026.11.18-b"


def detect(g: nx.MultiDiGraph, b: Bundle, scope: set[str] | None = None) -> list[Seam]:
    """Run every rule. With `scope`, keep only seams touching those nodes (selective re-check)."""
    seams = [s for rule in RULES.values() for s in rule(g, b)]
    for s in seams:
        s.basis = s.basis or BASIS.get(s.type, [])
    if scope is not None:
        seams = [s for s in seams if scope & set(s.nodes)]
    return seams

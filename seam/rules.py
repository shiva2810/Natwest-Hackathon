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


def _product(bundle: Bundle):
    return next(p for p in bundle.entities.products if p.id == bundle.scenario.product_id)


# ---------- the five seam types ----------

def orphaned_owner(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """Legal/Finance name an owner whom HR shows inactive or leaving before launch."""
    launch = _product(b).launch_date
    out = []
    for pid, person in nodes_of(g, "person"):
        gone = not person.active or (person.leaving_on and person.leaving_on <= launch)
        if not gone:
            continue
        owned = [(rid, r) for rid, r in neighbours(g, pid, "owned_by", incoming=True)
                 if r.department != "HR"]          # HR already sees its own roster
        if not owned:
            continue
        depts = sorted({"HR", *(r.department for _, r in owned)})
        out.append(Seam(
            id=f"orphaned_owner:{pid}", type="orphaned_owner", anchor=pid,
            title=f"{person.name} owns {len(owned)} obligation(s) but "
                  + ("is no longer active" if not person.active else f"leaves on {person.leaving_on}"),
            departments=depts, nodes=[pid, *(rid for rid, _ in owned)],
            record_ids=[rid for rid, _ in owned], effective_on=person.leaving_on,
            facts={"person": person.name, "role": person.role, "active": person.active,
                   "leaving_on": str(person.leaving_on), "launch_date": str(launch),
                   "obligations": [r.description for _, r in owned]},
        ))
    return out


def version_drift(g: nx.MultiDiGraph, b: Bundle) -> list[Seam]:
    """Legal approved one product version; the launch ships another."""
    out = []
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


RULES: dict[str, Callable[[nx.MultiDiGraph, Bundle], list[Seam]]] = {
    "orphaned_owner": orphaned_owner,
    "version_drift": version_drift,
    "unvetted_vendor": unvetted_vendor,
    "training_lapse": training_lapse,
    "approval_limit_breach": approval_limit_breach,
    "unbudgeted_contract": unbudgeted_contract,
}
RULES_VERSION = "rules-2026.11.18-a"


def detect(g: nx.MultiDiGraph, b: Bundle, scope: set[str] | None = None) -> list[Seam]:
    """Run every rule. With `scope`, keep only seams touching those nodes (selective re-check)."""
    seams = [s for rule in RULES.values() for s in rule(g, b)]
    if scope is not None:
        seams = [s for s in seams if scope & set(s.nodes)]
    return seams

"""LangGraph pipeline: the agent workflow behind every run and every event.

    START ─┬─(event?)─> apply_event ─┐
           └──────────────────────────┴─> check_departments -> build_graph -> detect_seams -> score
                                                                 -> referee -> propose_drafts -> END

check_departments runs the layer-3 checkers (each department on its own data only).
Dataset events (Person 1's event stream) are applied to raw files by the Engine, which re-extracts
and then invokes this pipeline with `changed` + `g_before` set, so the same selective re-check applies.

A full run has no event and no scope. An event run mutates the bundle, works out which graph nodes
are affected, and re-checks only those (selective re-check). The pipeline is stateless: the Engine
owns state (seams, waivers, sign-off, drafts) and merges what the pipeline returns.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Literal, Optional, TypedDict

import networkx as nx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from .checkers import run_checks
from .governance import TierPolicy
from .graph import affected_nodes, build_graph
from .referee import explain
from .rules import Seam, detect
from .schema import Bundle, Training
from .scoring import rank


class Event(BaseModel):
    type: Literal["resignation", "vendor_change", "new_product_version", "training_completed",
                  "record_update"]
    data: dict[str, Any]
    actor: str = "event-simulator"


class Draft(BaseModel):
    """An action an agent prepared but may not execute: tier 'draft' needs a human to approve."""
    id: str                                  # "<action>:<seam_id>"
    action: str
    seam_id: str
    summary: str
    params: dict[str, Any] = {}
    status: Literal["pending", "approved", "rejected", "obsolete"] = "pending"
    created_at: str | None = None
    decision: dict[str, Any] | None = None


class PipelineState(TypedDict, total=False):
    bundle: Bundle
    event: Optional[Event]
    changed: set[str]
    g_before: nx.MultiDiGraph
    graph: nx.MultiDiGraph
    scope: Optional[set[str]]
    seams: list[Seam]
    drafts: list[Draft]
    trace: list[str]                          # node names in order, for the audit log
    dept_summary: dict


# ---------- event mutations ----------

def mutate(bundle: Bundle, ev: Event) -> set[str]:
    """Apply an event to the bundle in place; return ids of the nodes it changed."""
    e, d = bundle.entities, ev.data

    def find(items, i, what):
        hit = next((x for x in items if x.id == i), None)
        if hit is None:
            raise ValueError(f"{ev.type}: unknown {what} '{i}'")
        return hit

    if ev.type == "resignation":
        p = find(e.people, d["person_id"], "person")
        p.leaving_on = date.fromisoformat(d["leaving_on"])
        p.active = not d.get("inactive", False)
        return {p.id}
    if ev.type == "vendor_change":
        v = find(e.vendors, d["vendor_id"], "vendor")
        if "due_diligence" in d:
            v.due_diligence = d["due_diligence"]
        if "dd_expires_on" in d:
            v.dd_expires_on = date.fromisoformat(d["dd_expires_on"]) if d["dd_expires_on"] else None
        changed = {v.id}
        # keep Finance's own DD record in step with the vendor master (the department re-check)
        for r in bundle.records:
            if r.kind == "vendor_due_diligence" and r.vendor_id == v.id:
                r.status = {"complete": "met", "pending": "unknown", "none": "unmet"}[v.due_diligence]
                changed.add(r.id)
        return changed
    if ev.type == "new_product_version":
        pr = find(e.products, d["product_id"], "product")
        pr.launch_version = str(d["version"])
        return {pr.id}
    if ev.type == "training_completed":
        p = find(e.people, d["person_id"], "person")
        p.trainings = [t for t in p.trainings if t.course != d["course"]] + [Training(
            course=d["course"], completed_on=date.fromisoformat(d["completed_on"]),
            expires_on=date.fromisoformat(d["expires_on"]) if d.get("expires_on") else None)]
        return {p.id}
    if ev.type == "record_update":
        r = find(bundle.records, d["record_id"], "record")
        changed = {r.id}
        if "owner_id" in d:
            if d["owner_id"] not in {p.id for p in e.people}:
                raise ValueError(f"record_update: unknown person '{d['owner_id']}'")
            if r.owner_id:
                changed.add(r.owner_id)       # the old owner's seams must be re-checked too
            r.owner_id = d["owner_id"]
        if "status" in d:
            r.status = d["status"]
        r.attributes.update(d.get("attributes", {}))
        return changed
    raise ValueError(f"unknown event type {ev.type}")


# ---------- pipeline ----------

def make_pipeline(policy: TierPolicy, llm: Callable[[str], dict] | None = None):
    def _t(state, name):
        return [*state.get("trace", []), name]

    def apply_event(state: PipelineState) -> PipelineState:
        b = state["bundle"]
        g_before = build_graph(b)
        changed = mutate(b, state["event"])
        return {"changed": changed, "g_before": g_before, "trace": _t(state, "apply_event")}

    def check_departments(state: PipelineState) -> PipelineState:
        policy.enforce("run_checks", "agent")
        return {"dept_summary": run_checks(state["bundle"]), "trace": _t(state, "check_departments")}

    def build(state: PipelineState) -> PipelineState:
        g = build_graph(state["bundle"])
        scope = None
        if state.get("changed") is not None and state.get("g_before") is not None:
            ch = state["changed"]
            scope = affected_nodes(state["g_before"], ch) | affected_nodes(g, ch)
        return {"graph": g, "scope": scope, "trace": _t(state, "build_graph")}

    def detect_seams(state: PipelineState) -> PipelineState:
        return {"seams": detect(state["graph"], state["bundle"], state.get("scope")),
                "trace": _t(state, "detect_seams")}

    def score(state: PipelineState) -> PipelineState:
        b = state["bundle"]
        launch = next(p for p in b.entities.products if p.id == b.scenario.product_id).launch_date
        return {"seams": rank(state["seams"], b.scenario.as_of, launch), "trace": _t(state, "score")}

    def referee(state: PipelineState) -> PipelineState:
        policy.enforce("explain_seam", "agent")
        seams = state["seams"]
        if llm is not None and len(seams) > 1:   # live LLM: explain seams in parallel
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(6, len(seams))) as pool:
                seams = list(pool.map(lambda s: explain(s, llm), seams))
        else:
            seams = [explain(s, llm) for s in seams]
        return {"seams": seams, "trace": _t(state, "referee")}

    def propose_drafts(state: PipelineState) -> PipelineState:
        b = state["bundle"]
        people = {p.id: p for p in b.entities.people}
        launch = next(p for p in b.entities.products if p.id == b.scenario.product_id).launch_date
        drafts = []
        for s in state["seams"]:
            owner = people.get(s.fix_owner_id or "")
            note = ""
            if owner and (not owner.active or (owner.leaving_on and owner.leaving_on <= launch)):
                manager = people.get(owner.manager_id or "")   # never route a fix to someone who is leaving
                note = f" (owner {owner.name} leaves {owner.leaving_on}; routed to their manager)"
                owner = manager
            if owner and policy.enforce("notify_owner", "agent") == "draft":
                drafts.append(Draft(
                    id=f"notify_owner:{s.id}", action="notify_owner", seam_id=s.id,
                    summary=f"Notify {owner.name} ({owner.role}): {s.title}{note}",
                    params={"to": owner.id, "message": s.explanation}))
            if s.type == "orphaned_owner" and policy.enforce("reassign_owner", "agent") == "draft":
                drafts.append(Draft(
                    id=f"reassign_owner:{s.id}", action="reassign_owner", seam_id=s.id,
                    summary=f"Reassign {len(s.record_ids)} obligation(s) from {s.facts.get('person')} "
                            "to a successor (approver names the successor)",
                    params={"record_ids": s.record_ids, "owner_id": None}))
        return {"drafts": drafts, "trace": _t(state, "propose_drafts")}

    sg = StateGraph(PipelineState)
    sg.add_node("apply_event", apply_event)
    sg.add_node("check_departments", check_departments)
    sg.add_node("build_graph", build)
    sg.add_node("detect_seams", detect_seams)
    sg.add_node("score", score)
    sg.add_node("referee", referee)
    sg.add_node("propose_drafts", propose_drafts)
    sg.add_conditional_edges(START, lambda s: "apply_event" if s.get("event") else "check_departments",
                             ["apply_event", "check_departments"])
    sg.add_edge("apply_event", "check_departments")
    sg.add_edge("check_departments", "build_graph")
    sg.add_edge("build_graph", "detect_seams")
    sg.add_edge("detect_seams", "score")
    sg.add_edge("score", "referee")
    sg.add_edge("referee", "propose_drafts")
    sg.add_edge("propose_drafts", END)
    return sg.compile()

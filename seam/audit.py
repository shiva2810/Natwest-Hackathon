"""Question-driven audit: route a question to a scope (HR / Finance / Legal, any combination), a what-if,
or a factual question answered only from the documents (seam/qa.py).

Routing: Claude first (if configured), then keywords, then a preset menu. Scoping never recomputes or
hides anything silently: a seam that needs a department outside the scope is listed as out of scope
with the departments it needs. Product is shared context and is always available.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .llm import OfflineMiss, parse_json

DOMAINS = ("HR", "Finance", "Legal")
PRESETS = [
    {"label": "Full launch audit (HR + Finance + Legal)", "domains": list(DOMAINS)},
    {"label": "HR only", "domains": ["HR"]},
    {"label": "Finance only", "domains": ["Finance"]},
    {"label": "Legal only", "domains": ["Legal"]},
]
KEYWORDS = {
    "HR": r"\b(hr|people|staff|employee|training|roster|headcount|hiring|leaver|resign|seller|course)\w*",
    "Finance": r"\b(finance|financial|budget|spend|vendor|supplier|purchase|po|approval limit|approver|cost)\w*",
    "Legal": r"\b(legal|contract|dpa|terms|obligation|regulator|approval|gdpr|policy|residency|change control)\w*",
}
AUDIT_WORDS = r"\b(compliant|compliance|ready|readiness|launch|audit|passport|pass|passed|passing|fail|failed|failing|check|go/no-go|go-no-go|safe to|ok to)\b"
QUESTION_WORDS = r"^\s*(what|who|whom|whose|when|where|which|how|why|list|show|does|do|did|is|are|was|were|can|could|has|have|will)\b|\?\s*$"
ALL_WORDS = r"\b(all|every|full|overall|whole|launch|ready|readiness|passport|go|no-go|everything|audit)\b"
WHATIF = r"^\s*(what if|what happens if|suppose|if )"

PROMPT = """Route an auditor's question for a compliance tool covering three departments: HR, Finance, Legal.
Return ONLY JSON: {{"intent": "audit" | "what_if" | "unclear", "domains": [subset of "HR","Finance","Legal"]}}
- "audit": the question asks whether something is compliant / ready / failing. Pick the departments it
  concerns; a launch-readiness or general question means all three.
- "what_if": the question describes a hypothetical change to people, suppliers, contracts, approvals, etc.
- "unclear": not about compliance.
Question: {question}"""


def _keyword_route(q: str) -> dict[str, Any]:
    low = q.lower()
    if re.search(WHATIF, low):
        return {"intent": "what_if", "domains": list(DOMAINS), "via": "keywords"}
    hits = [d for d, rx in KEYWORDS.items() if re.search(rx, low)]
    if re.search(AUDIT_WORDS, low):             # "is HR compliant?", "check Finance and Legal", "ready to launch?"
        return {"intent": "audit", "domains": hits or list(DOMAINS), "via": "keywords"}
    if re.search(QUESTION_WORDS, low):          # a lookup: "what is E008's approval limit?" -> answer from the documents
        return {"intent": "qa", "domains": [], "via": "keywords"}
    if hits:                                    # a bare topic ("contracts", "HR training") -> audit that department
        return {"intent": "audit", "domains": hits, "via": "keywords"}
    if re.search(ALL_WORDS, low):
        return {"intent": "audit", "domains": list(DOMAINS), "via": "keywords"}
    return {"intent": "unclear", "domains": [], "via": "keywords"}


def route(question: str, llm: Callable[[str], str] | None = None) -> dict[str, Any]:
    """intent: audit (scoped run), what_if (hypothetical), qa (answer from the documents), unclear (also goes to qa,
    which declines when the documents don't cover it)."""
    q = question.strip()
    if not q:
        return {"intent": "unclear", "domains": [], "via": "empty"}
    kw = _keyword_route(q)
    if llm is not None:
        try:
            out = parse_json(llm(PROMPT.format(question=q)))
            intent = out.get("intent")
            domains = [d for d in out.get("domains", []) if d in DOMAINS]
            if intent == "audit" and kw["intent"] == "qa":
                return kw                       # a factual lookup is not an audit run, whatever the model said
            if intent == "what_if" or (intent == "audit" and domains):
                return {"intent": intent, "domains": domains or list(DOMAINS), "via": "llm"}
            if intent == "unclear":
                return {"intent": "qa" if kw["intent"] == "qa" else "unclear", "domains": [], "via": "llm"}
        except Exception:                       # no cached answer, bad JSON, provider error: use the keywords
            pass
    return kw


def scoped(passport: dict[str, Any], domains: list[str]) -> dict[str, Any]:
    """Cut a passport down to the selected departments. Pure: reads the passport, changes nothing."""
    sel = [d for d in DOMAINS if d in domains] or list(DOMAINS)
    available = set(sel) | {"Product"}
    in_scope, out_scope = [], []
    for s in passport["seams"]:
        need = sorted(set(s["departments"]) - available)
        if not need:
            in_scope.append(s)
        elif set(s["departments"]) & set(sel):
            out_scope.append({"id": s["id"], "title": s["title"], "needs": need})
    depts = {d: passport["departments"][d] for d in sel if d in passport["departments"]}
    totals = {k: sum(d.get("results", {}).get(k, 0) for d in depts.values()) for k in ("passed", "failed", "needs_review")}
    blocking = [s["id"] for s in in_scope if s["status"] == "open" and (s["blocks_launch"] or s["severity"] == "critical")]
    open_in = [s for s in in_scope if s["status"] == "open"]
    status = "no_go" if blocking else "conditional" if (open_in or totals["failed"] or totals["needs_review"]) else "go"
    return {
        "domains": sel, "status": status, "totals": totals, "departments": depts,
        "seams": in_scope, "seams_needing_other_domains": out_scope,
        "as_of": passport["as_of"], "product": passport["product"], "full_overall": passport["overall"],
        "note": None if len(sel) == 3 else
        "Single- or partial-domain review: cross-department seams needing unselected domains are listed, not evaluated.",
    }


def ask(engine, question: str) -> dict[str, Any]:
    """Answer an audit question: route it, then run the scoped audit or the what-if."""
    r = route(question, engine.llm)
    out: dict[str, Any] = {"question": question, "route": r, "presets": PRESETS}
    if r["intent"] == "audit":
        out["audit"] = scoped(engine.passport(), r["domains"])
    elif r["intent"] == "what_if":
        try:
            out["simulation"] = engine.propose_what_if(question)
        except Exception as exc:
            out["route"] = {**r, "fallback": f"what-if could not be drafted: {exc}"}
    else:                                       # qa / unclear: answer from the documents or say it can't be answered
        from .qa import answer
        out["answer"] = answer(engine, question)
    log = {"question": question, "route": out["route"]}
    if "answer" in out:
        log["answerable"] = out["answer"]["answerable"]
        log["sources"] = [c["source"] for c in out["answer"]["citations"]]
    engine._log("audit_question", "auditor", log)
    return out

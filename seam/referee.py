"""Referee (component 4.4): plain-English explanation and fix options per seam.

Templates always work offline. If an `llm` callable is passed (Person 1's wrapper, X.1), it is
asked to rewrite using ONLY the seam facts; any failure or malformed output falls back to the template.
Expected llm signature: llm(prompt: str) -> dict with keys "explanation" (str) and "fix_options" (list[str]).
"""
from __future__ import annotations

import json
from typing import Callable

from .rules import Seam

TEMPLATES = {
    "orphaned_owner": (
        "{person} ({role}) is named as owner of: {obligation_list}. HR records show they leave on "
        "{leaving_on}, before the {launch_date} launch. No one else is named, so these obligations will "
        "have no accountable owner on launch day.",
        ["Name a successor owner for each obligation and record the handover",
         "Ask HR to confirm a backfill before launch",
         "Delay launch until owners are reassigned"],
    ),
    "version_drift": (
        "Legal's product approval covers {product} v{approved_version}, but the launch ships "
        "v{launch_version}. The approval does not cover what customers will receive.",
        ["Submit v{launch_version} to the product approval committee",
         "Launch v{approved_version} instead",
         "Get Legal to confirm in writing that the changes are out of scope"],
    ),
    "unvetted_vendor": (
        "The contract '{contract}' (£{value:,.0f}) is signed, but Finance shows {vendor}'s due diligence "
        "as '{due_diligence}' (expires {dd_expires_on}). Each team is acting correctly on its own data; "
        "together they put an uncleared vendor in the launch path.",
        ["Complete vendor due diligence before launch",
         "Block payments to {vendor} until due diligence completes",
         "Swap to an already-cleared vendor"],
    ),
    "training_lapse": (
        "'{requirement}' requires {person} to hold {course}. HR shows it expires {expires_on}, before the "
        "{launch_date} launch, so the requirement will be breached on launch day.",
        ["Book {person} on {course} renewal before {expires_on}",
         "Name a certified deputy for the obligation",
         "Ask Legal whether a grace period applies"],
    ),
    "approval_limit_breach": (
        "{signer} ({role}) signed '{contract}' for £{value:,.0f}, but Finance sets their approval limit at "
        "£{approval_limit:,.0f}. The contract may not be validly authorised.",
        ["Have an approver with sufficient limit ratify the contract",
         "Reduce the contract value to within the limit",
         "Raise the signer's limit through Finance governance"],
    ),
    "unbudgeted_contract": (
        "'{contract}' commits £{value:,.0f}, but Finance has only £{budgeted:,.0f} budgeted against it.",
        ["Add a budget line before spend", "Renegotiate the contract value"],
    ),
}


def _template(seam: Seam) -> tuple[str, list[str]]:
    text, fixes = TEMPLATES.get(seam.type, ("{title}", ["Review manually"]))
    facts = {**seam.facts, "title": seam.title}
    facts.setdefault("obligation_list", "; ".join(seam.facts.get("obligations", [])))

    class _Safe(dict):
        def __missing__(self, k):
            return "?"
    try:
        return text.format_map(_Safe(facts)), [f.format_map(_Safe(facts)) for f in fixes]
    except (ValueError, TypeError):
        return seam.title, fixes


def explain(seam: Seam, llm: Callable[[str], dict] | None = None) -> Seam:
    explanation, fixes = _template(seam)
    seam.facts["explained_by"] = "template"
    if llm is not None:
        prompt = (
            "You are a compliance referee. Explain this cross-department gap to a launch manager in 2-3 "
            "plain sentences and give 2-3 concrete fix options. Use ONLY these facts; do not invent any.\n"
            f"Seam type: {seam.type}\nTitle: {seam.title}\nDepartments: {', '.join(seam.departments)}\n"
            f"Facts: {json.dumps(seam.facts, default=str)}\n"
            'Return JSON: {"explanation": str, "fix_options": [str]}'
        )
        try:
            out = llm(prompt)
            if isinstance(out.get("explanation"), str) and isinstance(out.get("fix_options"), list) and out["fix_options"]:
                explanation, fixes = out["explanation"], [str(f) for f in out["fix_options"]][:3]
                seam.facts["explained_by"] = "llm"
        except Exception as exc:  # demo must never die on the LLM
            seam.facts["referee_error"] = str(exc)[:200]
    seam.explanation, seam.fix_options = explanation, fixes
    return seam

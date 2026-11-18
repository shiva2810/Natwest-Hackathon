"""Referee (component 4.4): plain-English explanation and fix options per seam.

Templates always work offline. If an `llm` callable is passed (Person 1's wrapper, X.1), it is
asked to rewrite using ONLY the seam facts; any failure or malformed output falls back to the template.
llm(prompt) may return a dict or a JSON string with keys "explanation" (str) and "fix_options" (list[str]).
"""
from __future__ import annotations

import json
from typing import Callable

from .llm import parse_json
from .rules import Seam

TEMPLATES = {
    "orphaned_owner": (
        "{person} ({role}) leaves on {leaving_on}, before the {launch_date} launch, but other departments "
        "still rely on them: {role_list}. HR sees a normal leaver; Legal and Finance each see a valid named "
        "person. On launch day these roles will have nobody behind them.",
        ["Name a successor owner for each obligation and record the handover",
         "Ask HR to confirm a backfill before launch",
         "Delay launch until owners are reassigned"],
    ),
    "version_drift": (
        "Legal's product approval covers {product} v{approved_version}, but the launch ships "
        "v{launch_version}{changes_clause}. The approval does not cover what customers will receive.",
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
    "seller_training_gap": (
        "Legal's rule says only staff with valid {course} may sell. HR's records show: {seller_list}. "
        "HR's mandatory list does not include {course}, and Legal does not hold the training records, "
        "so neither department sees it.",
        ["Book the listed sellers on {course} before their first sale",
         "Keep them off sales and onboarding until trained",
         "Add {course} to HR's mandatory list for anyone who can sell"],
    ),
    "data_residency_breach": (
        "The customer terms promise processing only in {region_list}, but {breach_list}. Finance records "
        "the region, Legal records the promise and a signed DPA - neither sees both.",
        ["Move processing to a UK/EEA region before launch",
         "Remove the supplier from the v2.0 data flows",
         "Amend the customer terms and notify customers (needs Legal sign-off)"],
    ),
    "support_capacity_gap": (
        "The terms promise {required_hours_per_week:.0f} staffed support hours a week, but {agents} agents "
        "cover {staffed_hours_per_week:.0f} ({gap_hours:.0f} short). Budget: {budget_list}. "
        "Hiring frozen until {hiring_frozen_until}.",
        ["Get a hiring-freeze exception from the COO and Head of Finance",
         "Contract an out-of-hours support provider",
         "Delay the Premium tier until support is staffed"],
    ),
    "unbudgeted_contract": (
        "'{contract}' commits £{value:,.0f}, but Finance has only £{budgeted:,.0f} budgeted against it.",
        ["Add a budget line before spend", "Renegotiate the contract value"],
    ),
}


VOLATILE = {"score_reasons", "explained_by", "referee_error"}


def _template(seam: Seam) -> tuple[str, list[str]]:
    text, fixes = TEMPLATES.get(seam.type, ("{title}", ["Review manually"]))
    facts = {**seam.facts, "title": seam.title}
    facts.setdefault("obligation_list", "; ".join(seam.facts.get("obligations", [])))
    facts.setdefault("role_list", "; ".join(seam.facts.get("roles", [])) or facts["obligation_list"])
    facts.setdefault("seller_list", "; ".join(seam.facts.get("sellers_without_valid_training", [])))
    facts.setdefault("breach_list", "; ".join(seam.facts.get("breaches", [])))
    facts.setdefault("region_list", "/".join(seam.facts.get("allowed_regions", [])))
    facts.setdefault("budget_list", "; ".join(seam.facts.get("budget_coverage", [])) or "no line found")
    mc = seam.facts.get("material_changes") or []
    facts.setdefault("changes_clause", f" with {len(mc)} material changes ({'; '.join(mc)})" if mc else "")

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
        # leave out values that change between runs (scoring, previous referee notes) so cache keys stay stable
        stable = {k: v for k, v in seam.facts.items() if k not in VOLATILE}
        prompt = (
            "You are a compliance referee. Explain this cross-department gap to a launch manager in 2-3 "
            "plain sentences and give 2-3 concrete fix options. Use ONLY these facts; do not invent any.\n"
            f"Seam type: {seam.type}\nTitle: {seam.title}\nDepartments: {', '.join(seam.departments)}\n"
            f"Facts: {json.dumps(stable, sort_keys=True, default=str)}\n"
            'Return JSON: {"explanation": str, "fix_options": [str]}'
        )
        try:
            out = parse_json(llm(prompt))
            if isinstance(out.get("explanation"), str) and isinstance(out.get("fix_options"), list) and out["fix_options"]:
                explanation, fixes = out["explanation"], [str(f) for f in out["fix_options"]][:3]
                seam.facts["explained_by"] = "llm"
        except Exception as exc:  # demo must never die on the LLM
            seam.facts["referee_error"] = str(exc)[:200]
    seam.explanation, seam.fix_options = explanation, fixes
    return seam

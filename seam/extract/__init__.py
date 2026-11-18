"""Extraction layer (2): data/ -> Bundle (records.json) plus an extraction report.

    from seam.extract import build_bundle
    bundle, report = build_bundle(load_dataset())                 # deterministic, offline
    bundle, report = build_bundle(ds, llm=CachedLLM(provider))    # LLM for policy text, rule fallback

The LLM path is per document: if the model is unavailable (offline cache miss) or errors, that
document falls back to the deterministic clause extractor and the report says so.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from ..llm import OfflineMiss
from ..schema import Bundle, Scenario
from ..sources import Dataset
from .clauses import extract_policy_text, link_register_quotes
from .llm_extract import llm_extract
from .tables import PRODUCT_ID, ExtractionError, extract_entities, extract_legal_register

COMPANY = "Aldermere Pay Ltd (fictional)"
TEXT_DEPTS = ("hr", "finance")


def build_bundle(ds: Dataset, llm: Callable[[str], str] | None = None) -> tuple[Bundle, dict[str, Any]]:
    entities = extract_entities(ds)
    register = extract_legal_register(ds)
    link = link_register_quotes(ds, register)
    rule_records, text_report = extract_policy_text(ds, TEXT_DEPTS)

    text_records = rule_records
    llm_report: dict[str, Any] = {"used": False}
    if llm is not None:
        text_records, llm_report = _with_llm(ds, llm, rule_records)

    records = [*text_records, *register]
    bundle = Bundle(scenario=Scenario(company=COMPANY, as_of=date.fromisoformat(ds.as_of), product_id=PRODUCT_ID),
                    entities=entities, records=records)
    counts: dict[str, int] = {}
    for r in records:
        counts[r.department] = counts.get(r.department, 0) + 1
    report = {
        "as_of": ds.as_of, "events_applied": list(ds.applied),
        "records_by_department": counts, "records_total": len(records),
        "entities": {k: len(v) for k, v in entities.model_dump().items()},
        "policy_text": text_report, "legal_register": link, "llm": llm_report,
        "quote_check": _quote_check(ds, records),
    }
    return bundle, report


def _with_llm(ds: Dataset, llm, rule_records):
    by_file: dict[str, list] = {}
    for r in rule_records:
        by_file.setdefault(r.source_ref.split("#")[0], []).append(r)
    out, rep = [], {"used": True, "files": {}, "rejected": []}
    for file, text in sorted(ds.texts.items()):
        if file.split("/")[0] not in TEXT_DEPTS:
            continue
        try:
            recs, rejected = llm_extract(file, text, llm)
        except OfflineMiss:
            out += by_file.get(file, [])
            rep["files"][file] = "fallback: offline and not cached"
            continue
        except Exception as exc:  # provider error: never lose the document
            out += by_file.get(file, [])
            rep["files"][file] = f"fallback: {type(exc).__name__}: {str(exc)[:120]}"
            continue
        rule_ids = {r.id for r in by_file.get(file, [])}
        llm_ids = {r.id for r in recs}
        rep["files"][file] = {"llm_records": len(recs), "rejected": len(rejected),
                              "only_llm": sorted(llm_ids - rule_ids), "only_rule": sorted(rule_ids - llm_ids)}
        rep["rejected"] += rejected
        out += recs
    return out, rep


def _quote_check(ds: Dataset, records) -> dict[str, Any]:
    """Every text-sourced quote must appear verbatim in the file it cites."""
    from .llm_extract import quote_ok
    checked, failed = 0, []
    for r in records:
        for ev in r.evidence:
            if ev.quote:
                checked += 1
                if not quote_ok(ev.quote, ds.texts.get(ev.source, "")):
                    failed.append({"record": r.id, "source": ev.source})
    return {"checked": checked, "failed": failed}


__all__ = ["build_bundle", "ExtractionError"]

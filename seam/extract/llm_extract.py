"""LLM extractor for policy and contract text (component 2.3), with a quote check.

The model reads one document and returns obligations as JSON. Each one is accepted only if:
  - its clause number exists in the document,
  - its quote appears verbatim in the document (whitespace/case/markdown-insensitive),
  - its kind is one we have a checker for.
Anything else is rejected and reported with the reason. Nothing reaches the store unquoted.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from ..llm import OfflineMiss, parse_json
from ..schema import KINDS, Evidence, ObligationRecord
from .clauses import DEPT_OF_FILE, PREFIX, KIND_RULES, parse_clauses

TEXT_KINDS = [k for k, *_ in KIND_RULES]

PROMPT = """You extract compliance obligations from a company policy document.

Return ONLY a JSON array. One element per clause that imposes a duty (must / shall / requires /
is responsible for). Skip permissions ("may ...") and statements of fact. Skip duties that do not
fit any kind below.

Each element: {{"clause": "<clause number as printed, e.g. 4.1>",
               "quote": "<the exact words of the clause, copied verbatim>",
               "kind": "<one of the kinds below>",
               "parameters": {{<course, validity_months, department, until, threshold_gbp, when stated>}}}}

Kinds:
{kinds}

Document ({file}):
<<<
{text}
>>>"""


def normalise(s: str) -> str:
    s = s.replace("**", "").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_ok(quote: str, source: str) -> bool:
    q = normalise(quote)
    return len(q) >= 12 and q in normalise(source)


def llm_extract(file: str, text: str, llm: Callable[[str], str]) -> tuple[list[ObligationRecord], list[dict]]:
    dept = DEPT_OF_FILE[file.split("/")[0]]
    kinds = "\n".join(f"- {k}: {KINDS[k]}" for k in TEXT_KINDS)
    raw = llm(PROMPT.format(kinds=kinds, file=file, text=text))   # OfflineMiss propagates to the caller
    try:
        items = parse_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return [], [{"file": file, "why": f"unparseable LLM output: {exc}"}]
    if not isinstance(items, list):
        return [], [{"file": file, "why": "LLM output is not a JSON array"}]

    clauses = {c.number: c for c in parse_clauses(file, text)}
    records, rejected, seen = [], [], set()
    for it in items:
        num, quote, kind = str(it.get("clause", "")), str(it.get("quote", "")), it.get("kind")
        why = None
        if num not in clauses:
            why = f"clause '{num}' does not exist in {file}"
        elif not quote_ok(quote, text):
            why = "quote is not verbatim in the source"
        elif kind not in TEXT_KINDS:
            why = f"unknown kind '{kind}'"
        elif num in seen:
            why = "duplicate clause"
        if why:
            rejected.append({"file": file, "clause": num, "quote": quote[:200], "kind": kind, "why": why})
            continue
        seen.add(num)
        c = clauses[num]
        params = it.get("parameters") if isinstance(it.get("parameters"), dict) else {}
        records.append(ObligationRecord(
            id=f"{PREFIX[dept]}-{num}", department=dept, kind=kind, description=c.text, status="unknown",
            source_ref=c.ref, evidence=[Evidence(source=file, quote=quote)],
            attributes={**params, "source_doc": c.doc, "clause": num, "doc_version": c.doc_version},
            extracted_by="llm"))
    return records, rejected


__all__ = ["llm_extract", "quote_ok", "normalise", "OfflineMiss"]

"""Live what-if checks: turn a question into a validated, previewable file-change event.

Two ways in, same output (an event in the event-stream format):
  - `propose(question, ds, llm)`  Claude drafts the changes from plain English (draft tier: a human
                                  must confirm before anything is applied)
  - `field_change(...)`           a structured edit from a form (works offline, no model)

`validate` dry-runs the event on a copy and returns a human-readable before -> after preview; it
rejects unknown files, rows that don't match, and columns that don't exist, so a model can never
invent data structure. Nothing here changes engine state.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Callable

from .llm import parse_json
from .sources import Dataset, EventError, apply_event

PK = {  # primary key column(s) per table, for previews and the form editor
    "hr/roster.csv": ["employee_id"], "hr/training_records.csv": ["employee_id", "course_code"],
    "hr/product_staffing.csv": ["employee_id", "product"], "hr/headcount_plan.csv": ["department"],
    "finance/budget.csv": ["line_id"], "finance/vendors.csv": ["vendor_id"],
    "finance/approval_limits.csv": ["approver_id"], "finance/purchase_orders.csv": ["po_id"],
    "legal/obligations_register.csv": ["obligation_id"], "legal/contracts_register.csv": ["contract_id"],
}


class WhatIfError(ValueError):
    pass


def _row_key(table: str, row: dict[str, str]) -> str:
    return "/".join(row.get(k, "?") for k in PK.get(table, list(row)[:1]))


def validate(ds: Dataset, event: dict[str, Any]) -> list[dict[str, Any]]:
    """Check every change against the live dataset and describe it. Raises WhatIfError if invalid."""
    if not isinstance(event.get("changes"), list) or not event["changes"]:
        raise WhatIfError("the event has no changes")
    preview: list[dict[str, Any]] = []
    for i, ch in enumerate(event["changes"]):
        f, op = ch.get("file"), ch.get("op")
        if op in ("insert", "update"):
            if f not in ds.tables:
                raise WhatIfError(f"change {i + 1}: unknown table '{f}'")
            cols = list(ds.tables[f][0]) if ds.tables[f] else []
            if op == "insert":
                row = ch.get("row") or {}
                missing, extra = set(cols) - set(row), set(row) - set(cols)
                if extra:
                    raise WhatIfError(f"change {i + 1}: {f} has no column(s) {sorted(extra)}")
                if missing:
                    raise WhatIfError(f"change {i + 1}: insert into {f} is missing column(s) {sorted(missing)}")
                preview.append({"file": f, "op": "insert", "target": _row_key(f, row), "field": "(new row)",
                                "before": "", "after": ", ".join(f"{k}={v}" for k, v in row.items() if v)})
            else:
                match, sets = ch.get("match") or {}, ch.get("set") or {}
                bad = (set(match) | set(sets)) - set(cols)
                if bad:
                    raise WhatIfError(f"change {i + 1}: {f} has no column(s) {sorted(bad)}")
                hits = [r for r in ds.tables[f] if all(r.get(k) == str(v) for k, v in match.items())]
                if not hits:
                    raise WhatIfError(f"change {i + 1}: no row in {f} matches {match}")
                for r in hits:
                    for k, v in sets.items():
                        preview.append({"file": f, "op": "update", "target": _row_key(f, r), "field": k,
                                        "before": r.get(k, ""), "after": str(v)})
        elif op in ("set", "append"):
            if f not in ds.docs:
                raise WhatIfError(f"change {i + 1}: unknown document '{f}'")
            path = ch.get("path")
            if op == "set" and path not in ds.docs[f]:
                raise WhatIfError(f"change {i + 1}: {f} has no field '{path}'")
            if op == "append" and not isinstance(ds.docs[f].get(path), list):
                raise WhatIfError(f"change {i + 1}: {f}.{path} is not a list")
            preview.append({"file": f, "op": op, "target": path, "field": path,
                            "before": "" if op == "append" else json.dumps(ds.docs[f].get(path)),
                            "after": json.dumps(ch.get("value"))})
        else:
            raise WhatIfError(f"change {i + 1}: op must be insert, update, set or append (got '{op}')")
    try:
        apply_event(ds.copy(), event)            # final dry run with the real applier
    except EventError as exc:
        raise WhatIfError(str(exc)) from exc
    return preview


def field_change(ds: Dataset, file: str, key: dict[str, str], field: str, value: Any,
                 description: str = "") -> dict[str, Any]:
    """Build a one-field what-if from the form editor."""
    if file in ds.tables:
        ch = {"file": file, "op": "update", "match": key, "set": {field: str(value)}}
    elif file in ds.docs:
        ch = {"file": file, "op": "set", "path": field, "value": value}
    else:
        raise WhatIfError(f"unknown file '{file}'")
    return {"event_id": "LIVE", "date": ds.as_of,
            "description": description or f"Live edit: {file} {key or ''} {field} -> {value}", "changes": [ch]}


def editable(ds: Dataset) -> dict[str, Any]:
    """What the form editor can offer: tables with key columns, rows and columns; docs with fields."""
    return {
        "tables": {f: {"key": PK.get(f, list(rows[0])[:1]), "columns": list(rows[0]),
                       "rows": [{k: r[k] for k in PK.get(f, list(r)[:1])} | {"_label": _row_key(f, r)} for r in rows]}
                   for f, rows in ds.tables.items() if rows},
        "docs": {f: [k for k, v in d.items() if isinstance(v, (str, int, float, bool))] for f, d in ds.docs.items()},
    }


# ---------- plain English -> event, via the LLM ----------

PROMPT = """You turn a what-if question about a company's compliance data into a precise data change.

Company data (CSV tables and JSON documents) as of {as_of}:
{data}

Allowed change operations (same format as the company's event stream):
  {{"file": "<table.csv>", "op": "update", "match": {{<key column>: <value>, ...}}, "set": {{<column>: <new value>}}}}
  {{"file": "<table.csv>", "op": "insert", "row": {{<every column of that table>: <value>}}}}
  {{"file": "<doc.json>", "op": "set", "path": "<top-level field>", "value": <new value>}}
  {{"file": "<doc.json>", "op": "append", "path": "<top-level list field>", "value": <item>}}
Rules: use only files, columns and ids that exist above; all CSV values are strings; dates are YYYY-MM-DD;
make the smallest set of changes that answers the question; a new person also needs roster and training rows.

Example of a valid event:
{example}

Question: {question}

Return ONLY JSON: {{"description": "<one sentence>", "changes": [...]}}
If the question cannot be expressed as a data change, return {{"description": "<why not>", "changes": []}}."""


def _dump(ds: Dataset) -> str:
    parts = []
    for f, rows in sorted(ds.tables.items()):
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        parts.append(f"### {f}\n{buf.getvalue()}")
    for f, d in sorted(ds.docs.items()):
        parts.append(f"### {f}\n{json.dumps(d, indent=1)}")
    return "\n".join(parts)


def propose(question: str, ds: Dataset, llm: Callable[[str], str]) -> dict[str, Any]:
    if not question.strip():
        raise WhatIfError("ask a question first")
    example = json.dumps(ds.events[0], indent=1) if ds.events else "{}"
    raw = llm(PROMPT.format(as_of=ds.as_of, data=_dump(ds), example=example, question=question.strip()))
    try:
        out = parse_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise WhatIfError(f"the model did not return valid JSON: {exc}") from exc
    if not isinstance(out, dict) or not out.get("changes"):
        raise WhatIfError(f"no data change for that question: {out.get('description') if isinstance(out, dict) else out}")
    return {"event_id": "LIVE", "date": ds.as_of, "description": out.get("description") or question.strip(),
            "question": question.strip(), "changes": out["changes"]}

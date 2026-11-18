"""Deterministic extractor for policy and contract text.

1. `parse_clauses` splits a markdown document into numbered clauses (`**4.1** text`), remembering
   the document name and section.
2. `is_binding` keeps clauses that impose a duty (must / shall / requires / responsible for).
   Permissions ("may work remotely") and statements of fact are not obligations.
3. `classify` maps a binding clause to an obligation kind we have a checker for, and pulls out
   parameters (course codes, months, dates, GBP amounts, departments) with general patterns.
   A binding clause with no matching kind is reported as "unmapped" for a human to review,
   never silently dropped.

Every record's evidence quote is the clause text itself, so it is verbatim by construction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from ..schema import Evidence, ObligationRecord
from ..sources import Dataset

CLAUSE_RE = re.compile(r"^\*\*(?P<num>[\d.]+)\*\*\s+(?P<text>.+)$")
HEADING_RE = re.compile(r"^##\s+(?P<h>.+)$")
TITLE_RE = re.compile(r"^#\s+(?P<t>.+?)(?:\s*\(excerpt\))?(?:\s+-\s+.*)?$")
VERSION_RE = re.compile(r"version\s+(?P<v>[\w.]+)", re.I)
BINDING_RE = re.compile(r"\b(must|shall|requires?|required|(?:are|is) responsible for)\b", re.I)

DEPT_OF_FILE = {"hr": "HR", "finance": "Finance", "legal": "Legal"}
PREFIX = {"HR": "HR", "Finance": "FIN", "Legal": "LEG"}


@dataclass
class Clause:
    file: str              # "hr/hr_policy_excerpt.md"
    doc: str               # "HR Policy", "Customer Terms v2.0", "Conduct Policy"
    section: str
    number: str            # "4.1"
    text: str
    doc_version: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.file}#{self.number}"


def parse_clauses(file: str, text: str) -> list[Clause]:
    lines = text.splitlines()
    title_m = TITLE_RE.match(lines[0]) if lines else None
    title = title_m.group("t").strip() if title_m else file
    ver_m = VERSION_RE.search(lines[0]) if lines else None
    out, section = [], ""
    for line in lines[1:]:
        if h := HEADING_RE.match(line):
            section = h.group("h").strip()
        elif c := CLAUSE_RE.match(line.strip()):
            # numbered sections ("## 3. Headcount") belong to the titled doc; named ones are their own policy
            doc = title if re.match(r"^\d", section) or not section else section
            out.append(Clause(file=file, doc=doc, section=section, number=c.group("num"),
                              text=c.group("text").strip(), doc_version=ver_m.group("v") if ver_m else None))
    return out


def is_binding(c: Clause) -> bool:
    return bool(BINDING_RE.search(c.text))


# ---------- classification ----------

def _all(*words: str) -> Callable[[str], bool]:
    return lambda t: all(re.search(w, t, re.I) for w in words)


def _course(t: str) -> dict[str, Any]:
    p: dict[str, Any] = {}
    if m := re.search(r"\b([A-Z]{2,4}-\d{3})\b", t):
        p["course"] = m.group(1)
    if m := re.search(r"every (\d+) months", t):
        p["validity_months"] = int(m.group(1))
    return p


def _freeze(t: str) -> dict[str, Any]:
    p: dict[str, Any] = {}
    if m := re.search(r"The (\w+) department", t):
        p["department"] = m.group(1)
    if m := re.search(r"until (\d{4}-\d{2}-\d{2})", t):
        p["until"] = m.group(1)
    return p


def _gbp(t: str) -> dict[str, Any]:
    m = re.search(r"([\d,]+)\s*GBP", t)
    return {"threshold_gbp": int(m.group(1).replace(",", ""))} if m else {}


# (kind, matcher, parameter extractor). First match wins; order specific -> general.
KIND_RULES: list[tuple[str, Callable[[str], bool], Callable[[str], dict[str, Any]]]] = [
    ("mandatory_training", _all(r"\b[A-Z]{2,4}-\d{3}\b", r"all employees"), _course),
    ("hiring_freeze", _all(r"hiring freeze"), _freeze),
    ("headcount_cap", _all(r"headcount", r"not exceed"), lambda t: {}),
    ("leaver_handover", _all(r"leaver|resign", r"reassign"), lambda t: {}),
    ("asm_spend_approval", _all(r"accountable senior manager", r"GBP"), _gbp),
    ("supplier_dd_before_po", _all(r"due diligence", r"purchase order"), lambda t: {}),
    ("po_approval_limit", _all(r"purchase order", r"limit"), lambda t: {}),
    ("budget_cap", _all(r"committed spend", r"approved amount|budget"), lambda t: {}),
]


def classify(c: Clause) -> tuple[str, dict[str, Any]] | None:
    for kind, match, params in KIND_RULES:
        if match(c.text):
            return kind, params(c.text)
    return None


# ---------- extraction ----------

def extract_policy_text(ds: Dataset, dept_dirs: tuple[str, ...] = ("hr", "finance")) -> tuple[list[ObligationRecord], dict]:
    """HR and Finance obligations come from their policy text (they have no register)."""
    records, report = [], {"binding": 0, "skipped_non_binding": [], "unmapped": []}
    for file, text in sorted(ds.texts.items()):
        dept_dir = file.split("/")[0]
        if dept_dir not in dept_dirs:
            continue
        dept = DEPT_OF_FILE[dept_dir]
        for c in parse_clauses(file, text):
            if not is_binding(c):
                report["skipped_non_binding"].append({"ref": c.ref, "text": c.text})
                continue
            report["binding"] += 1
            hit = classify(c)
            if hit is None:
                report["unmapped"].append({"ref": c.ref, "text": c.text,
                                           "why": "binding, but no checker for this kind of duty"})
                continue
            kind, params = hit
            records.append(ObligationRecord(
                id=f"{PREFIX[dept]}-{c.number}", department=dept, kind=kind, description=c.text,
                status="unknown", source_ref=c.ref,
                evidence=[Evidence(source=c.file, quote=c.text)],
                attributes={**params, "source_doc": c.doc, "clause": c.number, "doc_version": c.doc_version},
                extracted_by="rule"))
    return records, report


def link_register_quotes(ds: Dataset, register: list[ObligationRecord]) -> dict:
    """Attach the verbatim source clause to each Legal register row (register says doc + clause number)."""
    clauses = {(c.doc, c.number): c for f, t in ds.texts.items() if f.startswith("legal/")
               for c in parse_clauses(f, t)}
    linked, missing = [], []
    for r in register:
        c = clauses.get((r.attributes.get("source_doc"), r.attributes.get("clause")))
        if c is None:
            missing.append(r.id)
            continue
        r.evidence.insert(0, Evidence(source=c.file, quote=c.text))
        r.source_ref = c.ref
        linked.append(r.id)
    registered = {(r.attributes.get("source_doc"), r.attributes.get("clause")) for r in register}
    unregistered = [{"ref": c.ref, "text": c.text} for k, c in clauses.items()
                    if k not in registered and is_binding(c)]
    return {"linked": linked, "register_rows_without_source_text": missing,
            "binding_legal_clauses_not_in_register": unregistered}

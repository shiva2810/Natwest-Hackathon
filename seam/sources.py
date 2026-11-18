"""Raw department data (layer 1) and event replay.

`Dataset` holds every file under data/ as plain values: CSV -> list of row dicts (all strings),
JSON -> parsed object, markdown -> text. Events in data/events/event_stream.json are file-level
changes (insert / update / set / append); `apply_event` replays them onto a Dataset, after which
the extractors run again. Department isolation: each extractor reads only its own folder.
"""
from __future__ import annotations

import copy
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"
DEPT_DIRS = ("hr", "finance", "legal", "product")


@dataclass
class Dataset:
    root: Path
    tables: dict[str, list[dict[str, str]]] = field(default_factory=dict)   # "hr/roster.csv" -> rows
    docs: dict[str, Any] = field(default_factory=dict)                      # "legal/product_approval.json" -> obj
    texts: dict[str, str] = field(default_factory=dict)                     # "hr/hr_policy_excerpt.md" -> text
    events: list[dict[str, Any]] = field(default_factory=list)
    as_of: str = "2026-11-18"
    applied: list[str] = field(default_factory=list)                        # event ids replayed so far

    def copy(self) -> "Dataset":
        return copy.deepcopy(self)


def load_dataset(root: Path = DATA) -> Dataset:
    root = Path(root)
    ds = Dataset(root=root)
    for d in DEPT_DIRS:
        for p in sorted((root / d).glob("*")):
            key = f"{d}/{p.name}"
            if p.suffix == ".csv":
                with p.open(newline="") as f:
                    ds.tables[key] = [dict(r) for r in csv.DictReader(f)]
            elif p.suffix == ".json":
                ds.docs[key] = json.loads(p.read_text())
            elif p.suffix == ".md":
                ds.texts[key] = p.read_text()
    ev = root / "events" / "event_stream.json"
    if ev.exists():
        stream = json.loads(ev.read_text())
        ds.events = stream.get("events", [])
        ds.as_of = stream.get("as_of_start", ds.as_of)
    return ds


class EventError(ValueError):
    pass


def _matches(row: dict[str, str], match: dict[str, str]) -> bool:
    return all(row.get(k) == v for k, v in match.items())


def apply_change(ds: Dataset, ch: dict[str, Any]) -> list[str]:
    """Apply one change in place. Returns the primary-key-ish ids it touched (for selective re-check)."""
    f, op = ch["file"], ch["op"]
    if op in ("insert", "update"):
        if f not in ds.tables:
            raise EventError(f"unknown table {f}")
        rows = ds.tables[f]
        if op == "insert":
            rows.append({k: str(v) for k, v in ch["row"].items()})
            return [next(iter(ch["row"].values()))]
        hits = [r for r in rows if _matches(r, ch["match"])]
        if not hits:
            raise EventError(f"update matched no row in {f}: {ch['match']}")
        for r in hits:
            r.update({k: str(v) for k, v in ch["set"].items()})
        return [str(v) for v in ch["match"].values()]
    if op in ("set", "append"):
        if f not in ds.docs:
            raise EventError(f"unknown document {f}")
        doc, path = ds.docs[f], ch["path"]
        if op == "set":
            doc[path] = ch["value"]
        else:
            doc.setdefault(path, []).append(ch["value"])
        return [path]
    raise EventError(f"unknown op {op}")


def apply_event(ds: Dataset, event: dict[str, Any]) -> list[str]:
    """Apply all changes of one event atomically; moves as_of to the event date."""
    work = ds.copy()
    touched: list[str] = []
    for ch in event["changes"]:
        touched += apply_change(work, ch)
    ds.tables, ds.docs = work.tables, work.docs
    ds.as_of = max(ds.as_of, event.get("date") or ds.as_of)   # time only moves forward
    ds.applied.append(event.get("event_id", "?"))
    return touched

"""Obligation store (component 2.4): records.json on disk, queried in memory.

The data is a few hundred rows, so a JSON file plus filters is the right size (see README).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import Bundle, ObligationRecord


def save(bundle: Bundle, path: Path, report: dict[str, Any] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(bundle.model_dump_json(indent=1))
    tmp.replace(path)
    if report is not None:
        path.with_name(path.stem + ".report.json").write_text(json.dumps(report, indent=1, default=str))
    return path


def load(path: Path) -> Bundle:
    return Bundle.model_validate_json(Path(path).read_text())


def query(bundle: Bundle, **where: Any) -> list[ObligationRecord]:
    """query(b, department="Legal", status="unknown"); attribute filters use attr__name=value."""
    out = []
    for r in bundle.records:
        ok = True
        for k, v in where.items():
            have = r.attributes.get(k[6:]) if k.startswith("attr__") else getattr(r, k, None)
            if have != v:
                ok = False
                break
        if ok:
            out.append(r)
    return out

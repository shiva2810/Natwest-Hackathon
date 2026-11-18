"""Build records.json from data/.

    .venv/bin/python -m scripts.extract                     # -> runs/records.json (+ records.report.json)
    .venv/bin/python -m scripts.extract --events EV-01,EV-02 # replay events first
    .venv/bin/python -m scripts.extract --all-events
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from seam import store
from seam.extract import build_bundle
from seam.sources import DATA, apply_event, load_dataset

ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=str(DATA))
ap.add_argument("--out", default=str(ROOT / "runs" / "records.json"))
ap.add_argument("--events", default="", help="comma-separated event ids to replay, in stream order")
ap.add_argument("--all-events", action="store_true")
ap.add_argument("--llm", action="store_true", help="use Claude for policy text (cached; offline uses cache)")
args = ap.parse_args()

ds = load_dataset(Path(args.data))
wanted = {e.strip() for e in args.events.split(",") if e.strip()}
for ev in ds.events:
    if args.all_events or ev["event_id"] in wanted:
        apply_event(ds, ev)

llm = None
if args.llm:
    from seam.providers import default_llm
    llm = default_llm()
    print(f"LLM: {'live model + cache' if llm.provider else 'offline (cache only)'}")
bundle, report = build_bundle(ds, llm=llm)
path = store.save(bundle, Path(args.out), report)
print(f"wrote {path}")
print(json.dumps({k: report[k] for k in ("as_of", "events_applied", "records_by_department", "records_total",
                                          "entities")}, indent=1))
print(f"quote check: {report['quote_check']['checked']} checked, {len(report['quote_check']['failed'])} failed")
print(f"unmapped binding clauses: {[u['ref'] for u in report['policy_text']['unmapped']]}")
if llm:
    print(f"LLM files: {json.dumps(report['llm']['files'], indent=1)}")
    print(f"LLM rejected: {report['llm']['rejected']}  cache hits={llm.hits} calls={llm.misses}")
print(f"legal register rows without source text: {report['legal_register']['register_rows_without_source_text']}")

"""Run the whole flow once through Claude and fill cache/llm/, so the demo is fast and works offline.

    .venv/bin/python -m scripts.warm_llm

Needs ANTHROPIC_API_KEY in .env. Uses Claude for policy-text extraction (with the quote check) and
for the referee, over the baseline, all six stream events and every what-if scenario.
Commit cache/llm/ afterwards: with no key or no network, the same answers are replayed.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from seam.claude_provider import MODEL, default_llm, has_key
from seam.engine import Engine

ROOT = Path(__file__).resolve().parent.parent

if not has_key():
    sys.exit("No ANTHROPIC_API_KEY in .env (still the placeholder?). Paste the key, save the file, re-run.")

llm = default_llm()
tmp = Path(tempfile.mkdtemp())
t0 = time.time()
e = Engine(ROOT / "data", tmp / "a.jsonl", tmp / "s.json", llm=llm, extract_llm=llm)
p = e.run()
rep = e.extraction_report
print(f"model {MODEL}: baseline in {time.time() - t0:.0f}s")
print(f"  extraction via LLM: {rep['llm'].get('files')}")
print(f"  LLM quotes rejected by the quote check: {len(rep['llm'].get('rejected', []))}")
for r in rep["llm"].get("rejected", []):
    print(f"    - {r}")
print(f"  records: {rep['records_by_department']}  quote check failures: {len(rep['quote_check']['failed'])}")
print(f"  seams explained by: {[s['facts'].get('explained_by') for s in p['seams']]}")

for ev in e.stream():
    t = time.time()
    e.apply_stream_event(ev["event_id"])
    print(f"  {ev['event_id']} in {time.time() - t:.0f}s")
for sc in e.scenarios():
    t = time.time()
    e.apply_scenario(sc["name"])
    print(f"  scenario {sc['name']} in {time.time() - t:.0f}s")

from ui.live_check import EXAMPLES   # pre-ask the live-check examples so the first live answers are instant
e.run()
for q in EXAMPLES:
    t = time.time()
    try:
        sim = e.propose_what_if(q)
        print(f"  live: {q!r} -> {[x['field'] + '=' + x['after'] for x in sim['preview']]} "
              f"opens {sim['opened']} closes {sim['closed']} ({time.time() - t:.0f}s)")
    except Exception as exc:
        print(f"  live: {q!r} -> {exc}")

print(f"done in {time.time() - t0:.0f}s: {llm.misses} live calls, {llm.hits} cache hits -> cache/llm/")

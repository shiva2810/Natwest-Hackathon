"""Eval harness (X.3): score the engine against data/answer_key, baseline plus every event.

    .venv/bin/python -m scripts.eval_dataset
Prints obligations, department checks, seams per step, and false positives. Exit 1 on any mismatch.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

from seam.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT / "data" / "answer_key"
NAME = {"orphaned_owner": "S1", "seller_training_gap": "S2", "data_residency_breach": "S3",
        "support_capacity_gap": "S4", "version_drift": "S5"}
CHECK_MAP = {"HR-C1": "HR-4.1", "HR-C2": "HR-4.2", "HR-C3": "HR-6.2", "HR-C4": "HR-3.1", "HR-C5": "HR-7.1",
             "FIN-C1": "FIN-2.1", "FIN-C2": "FIN-3.2", "FIN-C3": "FIN-3.3", "FIN-C4": "FIN-4.1",
             "LEG-C1": "OBL-L-001", "LEG-C3": "OBL-L-008", "LEG-C4": "OBL-L-010", "LEG-C5": "OBL-L-006"}
fails: list[str] = []


def check(ok: bool, label: str):
    print(f"  {'✓' if ok else '✗'} {label}")
    if not ok:
        fails.append(label)


tmp = Path(tempfile.mkdtemp())
e = Engine(ROOT / "data", tmp / "a.jsonl", tmp / "s.json")
p = e.run()
rec = {r.id: r for r in e.bundle.records}

print("Obligations (extraction)")
exp_obl = list(csv.DictReader((KEY / "expected_obligations.csv").open()))
got = {(r.department, r.attributes.get("clause")) for r in e.bundle.records}
want = {(r["department"], r["clause"]) for r in exp_obl}
check(got == want, f"{len(got & want)}/{len(want)} matched, {len(got - want)} extra")

print("Department checks")
for row in csv.DictReader((KEY / "expected_department_checks.csv").open()):
    rid = CHECK_MAP.get(row["check_id"])
    if rid is None:
        print(f"  - {row['check_id']} not modelled as a separate check: {row['check']}")
        continue
    check(rec[rid].status == row["expected_status"], f"{row['check_id']} -> {rid}: {rec[rid].status} (expected {row['expected_status']})")

print("Seams")
exp_seams = json.loads((KEY / "expected_seams.json").read_text())
exp_seams = exp_seams["seams"] if isinstance(exp_seams, dict) else exp_seams
by_type = {NAME.get(s["type"], s["type"]): s for s in p["seams"]}
for es in exp_seams:
    s = by_type.get(es["seam_id"])
    check(s is not None, f"{es['seam_id']} {es['title']} found")
    if s:
        check(s["severity"] == es["severity"], f"{es['seam_id']} severity {s['severity']} (expected {es['severity']})")
        check(s["blocks_launch"] == es["blocks_launch"], f"{es['seam_id']} blocks_launch {s['blocks_launch']}")
        check(set(s["departments"]) >= set(es["departments"]), f"{es['seam_id']} departments {s['departments']}")
extra = sorted(set(by_type) - {s["seam_id"] for s in exp_seams})
check(not extra, f"false positives: {extra or 'none'}")

print("Events")
eff = json.loads((KEY / "expected_event_effects.json").read_text())
for ev in eff["events"]:
    r = e.apply_stream_event(ev["event_id"])
    opened = sorted(NAME.get(s["type"], s["type"]) for s in r["passport"]["seams"] if s["status"] == "open")
    check(opened == ev["open_seams"] and r["diff"]["selective_matches_full"],
          f"{ev['event_id']}: open {opened}, overall {r['passport']['overall']} - {ev['narrative']}")

print(f"\n{'PASS' if not fails else 'FAIL'}: {len(fails)} mismatch(es)")
sys.exit(1 if fails else 0)

"""The demo story on the real dataset (Aldermere Pay, QuickPay v2.0). Same client as the UI.

    .venv/bin/python -m scripts.demo_story            run every beat
    .venv/bin/python -m scripts.demo_story --pause    wait for Enter between beats (rehearsal / backup)

Exits non-zero if any beat does not behave as expected, so it doubles as a pre-demo smoke test.
"""
from __future__ import annotations

import sys

from seam.client import SeamClient, SeamError

PAUSE = "--pause" in sys.argv
COO = dict(signer_name="Helena Brandt", signer_role="Chief Operating Officer")
ICON = {"go": "🟢 GO", "conditional": "🟡 CONDITIONAL", "no_go": "🔴 NO-GO"}
SHORT = {"orphaned_owner": "S1", "seller_training_gap": "S2", "data_residency_breach": "S3",
         "support_capacity_gap": "S4", "version_drift": "S5"}


def beat(title: str):
    print(f"\n━━ {title}")
    if PAUSE:
        input("   (Enter) ")


def show(p: dict, seams: bool = True):
    print(f"   {p['product']['name']} v{p['product']['version']} as of {p['as_of']}: "
          f"{ICON[p['overall']]}   sign-off: {p['signoff']['state']}")
    for name, d in p["departments"].items():
        print(f"     {name:8} alone {ICON[d['own_view']]:15} with seams {ICON[d['status']]}")
    if seams:
        for s in p["seams"]:
            tag = "waived" if s["status"] == "waived" else s["severity"]
            print(f"     [{SHORT.get(s['type'], '??')} {tag:8}] {s['title']}")


def diff(r: dict):
    d = r["diff"]
    bits = [f"{k}: {d[k]}" for k in ("opened", "closed", "changed") if d[k]]
    print(f"   {d['event'].get('id')}: {d['event'].get('description')}")
    print(f"   re-checked {len(d['rechecked_nodes'])} nodes (matches full re-check: {d['selective_matches_full']}); "
          + ("; ".join(bits) or "no seam changes") + f"; overall {d['status_before']} -> {d['status_after']}")


def check(cond: bool, msg: str):
    if not cond:
        print(f"   ✗ UNEXPECTED: {msg}")
        sys.exit(1)


c = SeamClient()
print(f"backend: {c.mode}")

beat("1. Reset: QuickPay v2.0 launches 2026-12-01. Each department reviews its own data")
p = c.reset()
show(p)
check(len(p["seams"]) == 5 and p["overall"] == "no_go", "expected 5 seams and no-go")

beat("2. Alone, each department sees only small in-house findings")
for name in ("HR", "Finance", "Legal"):
    for f in p["departments"][name]["findings"]:
        print(f"   {name:8} {f['record']:10} {f['status']:8} {f['finding']}")
print(f"   Legal self-attests (cannot verify alone): {p['departments']['Legal']['self_attested']}")

beat("3. The seam detector reads across departments")
top = p["seams"][0]
print(f"   Top seam: {top['title']}")
print(f"   Why: {top['explanation']}")
print(f"   Basis: {' | '.join(top['basis'])}")
print(f"   Fix options: {' / '.join(top['fix_options'])}")

beat("4. Governance: an agent cannot sign; a human cannot sign GO over blocking seams")
try:
    c.agent_attempt("go_no_go"); check(False, "agent was allowed to sign")
except SeamError as e:
    print(f"   agent blocked: {e}")
try:
    c.sign("go", reason="we are on schedule", **COO); check(False, "go was allowed")
except SeamError as e:
    print(f"   GO refused: {str(e)[:120]}...")
print(f"   Agent drafts awaiting a human: {len(p['drafts'])} (e.g. {p['drafts'][0]['summary'][:80]})")

beat("5. The living passport: Person 1's event stream")
for ev in ("EV-01", "EV-02", "EV-03"):
    diff(c.apply_stream(ev))

beat("6. S1: Legal reassigns Meera's duties (EV-04), she leaves (EV-05), Finance catches up (EV-06)")
for ev in ("EV-04", "EV-05"):
    diff(c.apply_stream(ev))
s1 = next(s for s in c.passport()["seams"] if s["type"] == "orphaned_owner")
print(f"   S1 still open on the Finance side: {s1['facts']['roles']}")
r = c.apply_stream("EV-06"); diff(r)
check("orphaned_owner:E004" in r["diff"]["closed"], "S1 did not close after EV-06")

beat("7. What-if: the teams fix S5, S4 and S2")
for sc in ("fix_change_control", "fix_support_capacity", "fix_seller_training"):
    diff(c.scenario(sc))
r = c.scenario("fix_data_residency"); diff(r)
s3 = next(s for s in r["passport"]["seams"] if s["type"] == "data_residency_breach")
print(f"   S3 narrows but stays open: {s3['facts']['breaches']}")

beat("8. The COO waives the last seam with a named reason, then signs GO")
c.sign("waive", seam_id=s3["id"], reason="VerifyPoint EU migration contracted for 2026-12-15; customers notified", **COO)
p = c.sign("go", reason="all launch-blocking seams fixed or waived with owners", **COO)
show(p)
check(p["signoff"]["state"] == "go", "GO was not recorded")

beat("9. After sign-off: the General Counsel resigns -> new seam, GO invalidated automatically")
r = c.scenario("general_counsel_resigns"); diff(r)
check(r["passport"]["signoff"]["state"] == "pending", "sign-off was not invalidated")

beat("10. Audit: every step above is hash-chained")
a = c.audit()
print(f"   {a['verify']['entries']} entries, chain intact: {a['verify']['ok']}")
check(a["verify"]["ok"], "audit chain broken")
print("\n✓ demo story ran end to end")

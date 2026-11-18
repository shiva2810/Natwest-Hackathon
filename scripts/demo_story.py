"""The demo story, scripted. Uses the same client as the UI (API if up, else in-process).

    .venv/bin/python -m scripts.demo_story            run every beat
    .venv/bin/python -m scripts.demo_story --pause    wait for Enter between beats (rehearsal / backup)

Exits non-zero if any beat does not behave as expected, so it doubles as a pre-demo smoke test.
"""
from __future__ import annotations

import sys

from seam.client import SeamClient, SeamError

PAUSE = "--pause" in sys.argv
MAYA = dict(signer_name="Maya Lin", signer_role="Launch Director")
ICON = {"go": "🟢 GO", "conditional": "🟡 CONDITIONAL", "no_go": "🔴 NO-GO"}


def beat(title: str):
    print(f"\n━━ {title}")
    if PAUSE:
        input("   (Enter) ")


def show(p: dict):
    print(f"   Overall: {ICON[p['overall']]}   sign-off: {p['signoff']['state']}")
    for name, d in p["departments"].items():
        print(f"     {name:8} own view {ICON[d['own_view']]:15} combined {ICON[d['status']]}")
    for s in p["seams"]:
        tag = "waived" if s["status"] == "waived" else s["severity"]
        print(f"     [{tag:8}] {s['title']}")


def check(cond: bool, msg: str):
    if not cond:
        print(f"   ✗ UNEXPECTED: {msg}")
        sys.exit(1)


c = SeamClient()
print(f"mode: {c.mode}")

beat("1. Reset to the planted scenario")
p = c.reset()
show(p)
check(len(p["seams"]) == 5 and p["overall"] == "no_go", "expected 5 seams and no-go")

beat("2. Every department says it is fine on its own; the seams say otherwise")
legal = p["departments"]["Legal"]
print(f"   Legal alone: {legal['own_view']}   Legal with seams: {legal['status']}")
print(f"   Top seam explained: {p['seams'][0]['explanation']}")

beat("3. An agent tries to sign the launch off itself")
try:
    c.agent_attempt("go_no_go"); check(False, "agent was allowed to sign")
except SeamError as e:
    print(f"   blocked: {e}")

beat("4. A human tries to sign GO with open seams")
try:
    c.sign("go", reason="we are on schedule", **MAYA); check(False, "go was allowed")
except SeamError as e:
    print(f"   refused: {str(e)[:110]}...")

beat("5. Event: product team ships v1.4 instead of v2.0 (selective re-check)")
r = c.event("new_product_version", product_id="prod-swiftsave", version="1.4")
print(f"   re-checked {len(r['diff']['rechecked_nodes'])} nodes; closed {r['diff']['closed']}")
check(r["diff"]["closed"] == ["version_drift:leg-approval-swiftsave"], "version seam did not close")

beat("6. Agent drafted a reassignment; a human approves it, naming the successor")
r = c.decide_draft("reassign_owner:orphaned_owner:p-priya", True, reason="James covers until backfill",
                   owner_id="p-james", **MAYA)
print(f"   draft {r['draft']['status']}; closed {r['diff']['closed']}")

beat("7. Event: PayFlow passes due diligence; Ana renews GDPR Advanced")
c.event("vendor_change", vendor_id="v-payflow", due_diligence="complete", dd_expires_on="2027-11-30")
c.event("training_completed", person_id="p-ana", course="GDPR Advanced",
        completed_on="2026-11-25", expires_on="2027-11-25")
show(c.passport())

beat("8. One seam remains: the director waives it with a reason, then signs GO")
for s in c.passport()["seams"]:
    if s["status"] == "open":
        c.sign("waive", seam_id=s["id"], reason="Finance Director ratified the contract on 18 Nov", **MAYA)
p = c.sign("go", reason="all seams fixed or waived with named owners", **MAYA)
show(p)
check(p["signoff"]["state"] == "go", "go was not recorded")

beat("9. Event after sign-off: Ana resigns -> GO is invalidated automatically")
r = c.event("resignation", person_id="p-ana", leaving_on="2026-12-05")
print(f"   opened {r['diff']['opened']}; sign-off now: {r['passport']['signoff']['state']}")
check(r["passport"]["signoff"]["state"] == "pending", "sign-off was not invalidated")

beat("10. Audit log: every step above is hash-chained")
a = c.audit()
print(f"   {a['verify']['entries']} entries, chain intact: {a['verify']['ok']}")
check(a["verify"]["ok"], "audit chain broken")
print("\n✓ demo story ran end to end")

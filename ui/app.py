"""PLACEHOLDER passport UI so the demo runs end to end. Person 3 owns the real UI (6.1-6.4):
replace freely, but keep using SeamClient. Everything here is driven by the passport JSON.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import streamlit.components.v1 as components

from seam.client import SeamClient, SeamError
from ui.audit_chat import render as audit_chat
from seam.report import render_report
from ui.live_check import render as live_check

st.set_page_config(page_title="Compliance passport", layout="wide")
ICON = {"go": "🟢 GO", "conditional": "🟡 CONDITIONAL", "no_go": "🔴 NO-GO"}


@st.cache_resource
def client():
    return SeamClient()


def act(fn, *a, **k):
    try:
        out = fn(*a, **k)
        if isinstance(out, dict) and "diff" in out:
            st.session_state["last_diff"] = out["diff"]
        st.rerun()
    except SeamError as e:
        st.error(str(e))


c = client()
p = c.passport()
report_html = render_report(p, c.audit())   # built from the same passport as the screen

st.title(f"{p['product']['name']} v{p['product']['version']} · launch {p['product']['launch_date']}")
st.caption(f"{p['company']} · as of {p['as_of']} · last verified {p['last_verified']} · rules "
           f"{p['policy_versions']['rules']} · backend: {c.mode} · {p['disclaimer']}")
audit_chat(c)
st.divider()

left, right = st.columns([3, 1])
left.header(ICON[p["overall"]])
right.metric("Sign-off", p["signoff"]["state"].upper(), p["signoff"].get("by") or p["signoff"].get("reason", ""),
             delta_color="off")
right.download_button("⬇ Download audit report", report_html, "compliance-audit-report.html", "text/html",
                      use_container_width=True, help="One self-contained HTML file that opens offline.")

cols = st.columns(len(p["departments"]))
for col, (name, d) in zip(cols, p["departments"].items()):
    col.metric(name, ICON[d["status"]], f"alone: {ICON[d['own_view']]}", delta_color="off")
    r = d.get("results", {})
    col.caption(f"✅ {r.get('passed', 0)} passed · ❌ {r.get('failed', 0)} failed · ❔ {r.get('needs_review', 0)} needs review")
    for f in d["findings"]:
        label = {"failed": "❌ FAILED", "needs_review": "❔ NEEDS REVIEW"}.get(f.get("result"), "📝 SELF-ATTESTED")
        col.caption(f"{label} {f['record']}: {f['finding']}")

if "last_diff" in st.session_state:
    d = st.session_state["last_diff"]
    st.info(f"**{d['event'].get('id') or d['event'].get('type')}** {d['event'].get('description', '')} — "
            f"opened {d['opened'] or '-'}, closed {d['closed'] or '-'}, changed {d['changed'] or '-'}; "
            f"{d['status_before']} → {d['status_after']}; re-checked {len(d['rechecked_nodes'])} nodes "
            f"(matches full: {d['selective_matches_full']})")

live_check(c)

st.subheader("Seams")
for s in p["seams"]:
    tag = "WAIVED" if s["status"] == "waived" else s["severity"].upper()
    block = "" if s["blocks_launch"] else " · does not block launch"
    with st.expander(f"[{tag}] {s['title']}{block}"):
        st.write(s["explanation"])
        st.write("**Fix options:** " + " · ".join(s["fix_options"]))
        st.caption("Basis: " + " | ".join(s["basis"]))
        st.caption(f"Departments: {', '.join(s['departments'])} · fix owner: {s['fix_owner']} · score {s['score']} "
                   f"· explained by {s['facts'].get('explained_by')}")
        if s["waiver"]:
            st.info(f"Waived by {s['waiver']['by']} ({s['waiver']['role']}): {s['waiver']['reason']}")

ev_col, sc_col = st.columns(2)
with ev_col:
    st.subheader("Event stream")
    for e in p["events"]:
        if st.button(f"{'✅' if e['applied'] else '▶️'} {e['event_id']} ({e['date']}): {e['description'][:70]}",
                     key=e["event_id"], disabled=e["applied"]):
            act(c.apply_stream, e["event_id"])
with sc_col:
    st.subheader("What-if scenarios")
    for s in p.get("scenarios", []):
        if st.button(f"{'✅' if s['applied'] else '🧪'} {s['name']}: {s['description'][:70]}",
                     key=s["name"], disabled=s["applied"]):
            act(c.scenario, s["name"])

st.subheader("Agent drafts (need a human)")
people = {x["id"]: f"{x['name']} ({x['role']})" for x in p["people"]}
for d in p["drafts"]:
    with st.expander(d["summary"]):
        with st.form(f"draft-{d['id']}"):
            n, r = st.text_input("Your name"), st.text_input("Your role")
            why = st.text_input("Reason")
            owner = (st.selectbox("Successor", list(people), format_func=people.get)
                     if d["action"] == "reassign_owner" else None)
            a, b = st.columns(2)
            if a.form_submit_button("Approve"):
                act(c.decide_draft, d["id"], True, n, r, why, **({"owner_id": owner} if owner else {}))
            if b.form_submit_button("Reject"):
                act(c.decide_draft, d["id"], False, n, r, why)

st.subheader("Sign-off")
with st.form("sign"):
    name, role = st.text_input("Your name"), st.text_input("Your role")
    decision = st.selectbox("Decision", ["go", "no_go", "waive"])
    seam_id = st.selectbox("Seam (for waive)", [None] + [s["id"] for s in p["seams"] if s["status"] == "open"])
    reason = st.text_area("Reason")
    if st.form_submit_button("Sign"):
        act(c.sign, decision, name, role, reason, seam_id)

if st.button("Reset demo"):
    st.session_state.pop("last_diff", None)
    act(c.reset)
with st.expander("Evidence expiring soon"):
    st.table(p["evidence_expiring"])

st.subheader("Audit report")
with st.expander("Preview the report the user receives"):
    if hasattr(st, "iframe"):   # report HTML is fully escaped by seam/report.py
        st.iframe(report_html, height=900)
    else:
        components.html(report_html, height=900, scrolling=True)

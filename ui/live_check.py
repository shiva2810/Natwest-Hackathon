"""Live what-if panel. Drop-in for any Streamlit page (Person 3's UI too):

    from ui.live_check import render
    render(client)            # client = seam.client.SeamClient()

Flow: ask in plain English (Claude drafts the change) or edit one record in a form (offline)
  -> preview every before/after -> predicted effect -> a named person applies it, or discards it.
Nothing changes until "Apply" is pressed.
"""
from __future__ import annotations

import streamlit as st

from seam.client import SeamClient, SeamError

ICON = {"go": "🟢 GO", "conditional": "🟡 CONDITIONAL", "no_go": "🔴 NO-GO"}
EXAMPLES = [
    "What if StreamLedger moves its processing to Frankfurt?",
    "What if Priya Sharma resigns with a last day of 28 November?",
    "What if Ben Foster renews PCT-101 today?",
    "What if Legal re-approves QuickPay for version 2.0?",
]
KEY = "live_sim"


def _show_simulation(c: SeamClient, sim: dict):
    st.markdown(f"**Proposed change:** {sim['event'].get('description', '')}")
    st.table([{"file": x["file"], "record": x["target"], "field": x["field"], "before": x["before"], "after": x["after"]}
              for x in sim["preview"]])
    a, b, d = st.columns(3)
    a.metric("Overall", ICON[sim["status_after"]], f"now {ICON[sim['status_before']]}", delta_color="off")
    b.metric("Seams opened / closed", f"{len(sim['opened'])} / {len(sim['closed'])}",
             f"{len(sim['changed'])} changed", delta_color="off")
    moved = {k: v for k, v in sim["departments"].items() if v["before"] != v["after"]}
    d.metric("Departments that move", len(moved), ", ".join(f"{k}: {ICON[v['after']]}" for k, v in moved.items()) or "none",
             delta_color="off")
    titles = {s["id"]: s["title"] for s in sim["seams_after"]}
    for sid in sim["opened"]:
        st.error(f"Would open: {titles.get(sid, sid)}")
    for sid in sim["closed"]:
        st.success(f"Would close: {sid}")
    for sid in sim["changed"]:
        st.warning(f"Would change: {titles.get(sid, sid)}")
    if not (sim["opened"] or sim["closed"] or sim["changed"]):
        st.info("No seam would change. Department findings may still move (see departments above).")
    if sim.get("signoff_would_reset"):
        st.warning("Applying this resets the current sign-off to pending.")

    with st.form("live_apply"):
        who = st.text_input("Confirmed by (your name)")
        why = st.text_input("Reason (optional)")
        x, y = st.columns(2)
        if x.form_submit_button("Apply for real", type="primary"):
            try:
                out = c.apply_live(sim["event"], who, why)
                st.session_state["last_diff"] = out["diff"]
                st.session_state.pop(KEY, None)
                st.rerun()
            except SeamError as e:
                st.error(str(e))
        if y.form_submit_button("Discard"):
            st.session_state.pop(KEY, None)
            st.rerun()


def render(c: SeamClient):
    st.subheader("🔎 Live check: what if…?")
    ask, edit = st.tabs(["Ask in plain English", "Edit a record"])
    with ask:
        q = st.text_input("Question", placeholder=EXAMPLES[0], key="live_q")
        st.caption("Try: " + " · ".join(EXAMPLES[1:]))
        if st.button("Check", key="live_ask"):
            with st.spinner("Claude is drafting the change and the engine is simulating it…"):
                try:
                    st.session_state[KEY] = c.what_if_question(q or EXAMPLES[0])
                except SeamError as e:
                    st.error(str(e))
    with edit:
        try:
            ed = c.editable()
        except SeamError as e:
            st.error(str(e))
            ed = None
        if ed:
            files = list(ed["tables"]) + list(ed["docs"])
            f = st.selectbox("File", files, key="live_file")
            if f in ed["tables"]:
                t = ed["tables"][f]
                row = st.selectbox("Record", t["rows"], format_func=lambda r: r["_label"], key="live_row")
                field = st.selectbox("Field", [col for col in t["columns"] if col not in t["key"]], key="live_field")
                key = {k: row[k] for k in t["key"]}
            else:
                field = st.selectbox("Field", ed["docs"][f], key="live_docfield")
                key = {}
            value = st.text_input("New value", key="live_value")
            if st.button("Simulate", key="live_sim_btn"):
                try:
                    st.session_state[KEY] = c.what_if_field(f, key, field, value)
                except SeamError as e:
                    st.error(str(e))
    if KEY in st.session_state:
        _show_simulation(c, st.session_state[KEY])

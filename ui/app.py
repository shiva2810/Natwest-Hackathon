"""PLACEHOLDER passport UI so the demo runs end to end today.
Person 3 owns the real UI (6.1-6.4): replace freely, but keep using SeamClient.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from seam.client import SeamClient, SeamError

st.set_page_config(page_title="Compliance passport", layout="wide")
ICON = {"go": "🟢 GO", "conditional": "🟡 CONDITIONAL", "no_go": "🔴 NO-GO"}


@st.cache_resource
def client():
    return SeamClient()


c = client()
p = c.passport()

st.title(f"{p['product']['name']} v{p['product']['version']} · launch {p['product']['launch_date']}")
st.caption(f"{p['company']} · last verified {p['last_verified']} · rules {p['policy_versions']['rules']} · "
           f"backend: {c.mode} · {p['disclaimer']}")
st.header(ICON[p["overall"]])

cols = st.columns(len(p["departments"]))
for col, (name, d) in zip(cols, p["departments"].items()):
    col.metric(name, ICON[d["status"]], f"alone: {d['own_view']}", delta_color="off")

st.subheader("Seams")
for s in p["seams"]:
    with st.expander(f"[{s['status'] if s['status'] == 'waived' else s['severity']}] {s['title']}"):
        st.write(s["explanation"])
        st.write("**Fix options:** " + " · ".join(s["fix_options"]))
        st.caption(f"Departments: {', '.join(s['departments'])} · fix owner: {s['fix_owner']} · score {s['score']}")
        if s["waiver"]:
            st.info(f"Waived by {s['waiver']['by']}: {s['waiver']['reason']}")

st.subheader("Sign-off")
st.write(p["signoff"])
with st.form("sign"):
    name, role = st.text_input("Your name"), st.text_input("Your role")
    decision = st.selectbox("Decision", ["go", "no_go", "waive"])
    seam_id = st.selectbox("Seam (for waive)", [None] + [s["id"] for s in p["seams"] if s["status"] == "open"])
    reason = st.text_area("Reason")
    if st.form_submit_button("Sign"):
        try:
            c.sign(decision, name, role, reason, seam_id); st.rerun()
        except SeamError as e:
            st.error(e)

st.subheader("Events")
ev = {"Ship v1.4 instead": ("new_product_version", {"product_id": "prod-swiftsave", "version": "1.4"}),
      "PayFlow passes DD": ("vendor_change", {"vendor_id": "v-payflow", "due_diligence": "complete"}),
      "Ana resigns": ("resignation", {"person_id": "p-ana", "leaving_on": "2026-12-05"})}
for col, (label, (t, data)) in zip(st.columns(len(ev) + 1), ev.items()):
    if col.button(label):
        st.session_state["last_diff"] = c.event(t, **data)["diff"]; st.rerun()
if st.button("Reset demo"):
    c.reset(); st.session_state.pop("last_diff", None); st.rerun()
if "last_diff" in st.session_state:
    st.json(st.session_state["last_diff"], expanded=False)

"""Audit chat: the auditor starts with a question. Drop-in: `from ui.audit_chat import render; render(client)`.

Question -> route (Claude, else keywords) -> scoped audit (HR / Finance / Legal, any mix) or a what-if.
If the question can't be understood, preset buttons run a predefined audit instead.
"""
from __future__ import annotations

import streamlit as st

from seam.client import SeamClient, SeamError

ICON = {"go": "🟢 GO", "conditional": "🟡 CONDITIONAL", "no_go": "🔴 NO-GO"}
PRESETS = [("Full launch audit", ["HR", "Finance", "Legal"]), ("HR only", ["HR"]),
           ("Finance only", ["Finance"]), ("Legal only", ["Legal"])]
KEY = "audit_chat"


def _audit_answer(a: dict):
    st.markdown(f"**Scope: {' + '.join(a['domains'])}** → {ICON[a['status']]}  ·  "
                f"✅ {a['totals']['passed']} passed · ❌ {a['totals']['failed']} failed · "
                f"❔ {a['totals']['needs_review']} needs review")
    for name, d in a["departments"].items():
        for f in d["findings"]:
            label = {"failed": "❌", "needs_review": "❔"}.get(f.get("result"), "📝")
            st.markdown(f"{label} **{name} {f['record']}**: {f['finding']}")
    for s in a["seams"]:
        tag = "waived" if s["status"] == "waived" else s["severity"]
        st.markdown(f"🔗 **[{tag}] {s['title']}** ({', '.join(s['departments'])})")
        st.caption(s["explanation"])
    for s in a["seams_needing_other_domains"]:
        st.markdown(f"↔️ Not evaluated in this scope: *{s['title']}*, which also needs **{', '.join(s['needs'])}**")
    if a.get("note"):
        st.caption(a["note"])


def render(c: SeamClient):
    st.subheader("💬 Ask the auditor assistant")
    hist = st.session_state.setdefault(KEY, [])
    for m in hist:
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.write(m["text"])
            elif "audit" in m:
                st.caption(f"Routed by {m['via']} to: {' + '.join(m['audit']['domains'])}")
                _audit_answer(m["audit"])
            elif "simulation" in m:
                sim = m["simulation"]
                st.caption(f"Routed by {m['via']} to: what-if (nothing applied yet; open '🧪 Live check' to apply)")
                st.markdown(f"**{sim['event'].get('description', '')}** → overall {ICON[sim['status_before']]} → "
                            f"{ICON[sim['status_after']]}; would open {sim['opened'] or '-'}, close {sim['closed'] or '-'}, "
                            f"change {sim['changed'] or '-'}")
                st.session_state["live_sim"] = sim          # Live check panel shows preview + Apply
            else:
                st.write(m["text"])

    st.caption("Try: *Is QuickPay ready to launch?* · *Is HR compliant?* · *Check Finance and Legal* · "
               "*What if StreamLedger moves its processing to Frankfurt?*")
    cols = st.columns(len(PRESETS))
    preset = None
    for col, (label, domains) in zip(cols, PRESETS):
        if col.button(label, key=f"preset-{label}"):
            preset = (label, domains)

    q = st.chat_input("Ask a compliance question, e.g. 'Is QuickPay ready to launch?'")
    try:
        if preset:
            hist.append({"role": "user", "text": f"[{preset[0]}]"})
            hist.append({"role": "assistant", "via": "preset", "audit": c.audit_scope(preset[1])})
            st.rerun()
        if q:
            hist.append({"role": "user", "text": q})
            with st.spinner("Routing the question and running the checks…"):
                out = c.ask(q)
            r = out["route"]
            if "audit" in out:
                hist.append({"role": "assistant", "via": r["via"], "audit": out["audit"]})
            elif "simulation" in out:
                hist.append({"role": "assistant", "via": r["via"], "simulation": out["simulation"]})
            else:
                why = r.get("fallback") or "I couldn't map that to a compliance check."
                hist.append({"role": "assistant", "text": f"{why} Pick a predefined audit above."})
            st.rerun()
    except SeamError as e:
        st.error(str(e))

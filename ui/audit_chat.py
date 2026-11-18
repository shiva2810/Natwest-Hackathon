"""Audit chat: the auditor starts with a question. Drop-in: `from ui.audit_chat import render; render(client)`.

Question -> route (Claude, else keywords) -> scoped audit (HR / Finance / Legal, any mix) or a what-if.
If the question can't be understood, preset buttons run a predefined audit instead.
"""
from __future__ import annotations

import os
import time

import streamlit as st

from seam.client import SeamClient, SeamError

ICON = {"go": "🟢 GO", "conditional": "🟡 CONDITIONAL", "no_go": "🔴 NO-GO"}
PRESETS = [("Full launch audit", ["HR", "Finance", "Legal"]), ("HR only", ["HR"]),
           ("Finance only", ["Finance"]), ("Legal only", ["Legal"])]
KEY = "audit_chat"
# How long the "working" bar runs before the result appears (demo pacing: 3-5 s). SEAM_RESULT_DELAY=0 turns it off.
DELAY = float(os.environ.get("SEAM_RESULT_DELAY", "4"))


def _steps(domains: list[str] | None) -> list[str]:
    load = [f"Loading {d} records…" for d in domains] if domains else ["Reading the question…", "Searching the documents and data…"]
    return load + ["Checking each department on its own…", "Reading across departments for seams…",
                   "Verifying the evidence and writing the verdict…"]


def run_with_progress(slot, fn, domains: list[str] | None = None, delay: float | None = None):
    """Show a progress bar with the current step while `fn` runs, and keep it up for `delay` seconds in total,
    so the result lands after a few seconds instead of flashing in. `slot` is an st.container / st.empty."""
    delay = DELAY if delay is None else delay
    steps = _steps(domains)
    t0 = time.time()
    with slot:
        bar = st.progress(0.03, text=steps[0])
        result = fn()                                   # the real work; usually well under a second
        left = max(delay - (time.time() - t0), 0.0)
        ticks = max(int(left / 0.1), 1) if left else 0
        for i in range(1, ticks + 1):
            frac = i / ticks
            bar.progress(min(0.03 + 0.97 * frac, 1.0), text=steps[min(int(frac * len(steps)), len(steps) - 1)])
            time.sleep(left / ticks)
        bar.empty()
    return result


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


def _answer(a: dict):
    """A question answered from the documents, or the fixed 'cannot be answered' message."""
    if not a["answerable"]:
        st.warning(a["message"], icon="🚫")
        return
    st.caption("Answered only from the provided documents and data" if a["via"] == "llm"
               else "No language model configured: showing the closest passages, not a written answer")
    st.markdown(a["answer"])
    for cite in a["citations"]:
        st.markdown(f"📄 **{cite['source']}**")
        st.caption(f"“{cite['quote']}”")


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
            elif "answer" in m:
                _answer(m["answer"])
            elif "simulation" in m:
                sim = m["simulation"]
                st.caption(f"Routed by {m['via']} to: what-if (nothing applied yet; open '🧪 Live check' to apply)")
                st.markdown(f"**{sim['event'].get('description', '')}** → overall {ICON[sim['status_before']]} → "
                            f"{ICON[sim['status_after']]}; would open {sim['opened'] or '-'}, close {sim['closed'] or '-'}, "
                            f"change {sim['changed'] or '-'}")
                st.session_state["live_sim"] = sim          # Live check panel shows preview + Apply
            else:
                st.write(m["text"])

    pending = st.container()          # the "working…" bubble appears here while an audit runs
    st.caption("Try: *Is QuickPay ready to launch?* · *Is HR compliant?* · *Check Finance and Legal* · "
               "*What if StreamLedger moves its processing to Frankfurt?* · *What is the approval limit for E008?* · "
               "*When does Meera Iyer leave?*  — questions the documents don't cover get a clear “can't be answered” reply.")
    cols = st.columns(len(PRESETS))
    preset = None
    for col, (label, domains) in zip(cols, PRESETS):
        if col.button(label, key=f"preset-{label}"):
            preset = (label, domains)

    q = st.chat_input("Ask a compliance question, e.g. 'Is QuickPay ready to launch?'")
    try:
        if preset:
            with pending:
                st.chat_message("user").write(f"[{preset[0]}]")
                with st.chat_message("assistant"):
                    box = st.container()
            audit = run_with_progress(box, lambda: c.audit_scope(preset[1]), preset[1])
            hist.append({"role": "user", "text": f"[{preset[0]}]"})
            hist.append({"role": "assistant", "via": "preset", "audit": audit})
            st.rerun()
        if q:
            with pending:
                st.chat_message("user").write(q)
                with st.chat_message("assistant"):
                    box = st.container()
            out = run_with_progress(box, lambda: c.ask(q))
            hist.append({"role": "user", "text": q})
            r = out["route"]
            if "audit" in out:
                hist.append({"role": "assistant", "via": r["via"], "audit": out["audit"]})
            elif "simulation" in out:
                hist.append({"role": "assistant", "via": r["via"], "simulation": out["simulation"]})
            elif "answer" in out:
                hist.append({"role": "assistant", "via": r["via"], "answer": out["answer"]})
            else:
                why = r.get("fallback") or "I couldn't map that to a compliance check."
                hist.append({"role": "assistant", "text": f"{why} Pick a predefined audit above."})
            st.rerun()
    except SeamError as e:
        st.error(str(e))

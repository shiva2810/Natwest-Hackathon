"""Compliance Seam Detector: the auditor-facing UI. Everything is driven by the passport JSON from the
API (via SeamClient); the UI never computes compliance itself.
"""
import html
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import streamlit.components.v1 as components

from seam.client import SeamClient, SeamError
from seam.report import render_report
from ui.audit_chat import render as audit_chat
from ui.conflicts import render as conflicts_view
from ui.data_panel import render as data_panel
from ui.live_check import render as live_check

st.set_page_config(page_title="Compliance Seam Detector", page_icon="🔗", layout="wide")

STATUS = {"go": ("GO", "go"), "conditional": ("CONDITIONAL", "cond"), "no_go": ("NO-GO", "nogo")}
SEV = {"critical": "nogo", "high": "high", "medium": "cond", "low": "go"}
e = html.escape

st.markdown("""
<style>
  #MainMenu, footer, [data-testid="stDecoration"] {visibility: hidden; height: 0}
  .block-container {padding-top: 1.2rem; max-width: 1280px}
  .brand {display:flex; align-items:center; gap:12px; background:#fff; border:1px solid #e0e8e2;
          border-radius:12px; padding:12px 18px; box-shadow:0 7px 24px #1633240a; margin-bottom:14px}
  .brand .mark {width:34px; height:34px; border-radius:9px; background:#176b4a; color:#fff;
                display:grid; place-items:center; font-weight:800; font-size:17px}
  .brand .name {font-weight:780; font-size:19px; letter-spacing:-.03em; color:#17251f}
  .brand .tag {color:#68776e; font-size:12.5px}
  .brand .meta {margin-left:auto; text-align:right; color:#68776e; font-size:11.5px; line-height:1.5}
  .hero {display:flex; align-items:center; gap:18px; margin:4px 0 12px}
  .hero h1 {font-size:26px; margin:0; letter-spacing:-.03em; color:#17251f}
  .hero .sub {color:#68776e; font-size:13px}
  .pill {display:inline-block; padding:4px 12px; border-radius:20px; font-weight:750; font-size:12px; letter-spacing:.02em}
  .pill.big {font-size:17px; padding:8px 18px}
  .go {background:#e7f3ec; color:#176b4a; border:1px solid #b9dcc7}
  .cond {background:#fbf3df; color:#8a6319; border:1px solid #ead59e}
  .nogo {background:#faecea; color:#a33b34; border:1px solid #efc2bd}
  .high {background:#fdf0e6; color:#a2531b; border:1px solid #f0cba9}
  .muted {background:#eef2ef; color:#526158; border:1px solid #dde5df}
  .cards {display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; margin:6px 0 12px}
  .card {background:#fff; border:1px solid #e0e8e2; border-radius:10px; padding:12px 14px; box-shadow:0 7px 24px #1633240a}
  .card .lbl {font-size:11px; color:#68776e; text-transform:uppercase; letter-spacing:.08em; font-weight:650}
  .card .val {font-size:24px; font-weight:760; letter-spacing:-.03em; margin-top:2px; color:#17251f}
  .card .val small {font-size:12px; color:#68776e; font-weight:500; letter-spacing:0}
  .depts {display:grid; grid-template-columns:repeat(4, 1fr); gap:10px; margin-bottom:8px}
  .dept h4 {margin:0 0 6px; font-size:14px}
  .dept .row {display:flex; align-items:center; gap:6px; font-size:12px; color:#68776e; margin:3px 0}
  .dept .counts {font-size:12px; margin-top:6px; color:#3d4b43}
  .seam {background:#fff; border:1px solid #e0e8e2; border-left:5px solid #ccc; border-radius:10px;
         padding:14px 16px; margin:10px 0; box-shadow:0 7px 24px #1633240a}
  .seam.nogo {border-left-color:#a33b34} .seam.high {border-left-color:#d07a35}
  .seam.cond {border-left-color:#c79a2c} .seam.waived {border-left-color:#8fa397; opacity:.8}
  .seam .t {font-weight:720; font-size:15px; color:#17251f; margin:6px 0}
  .seam .x {font-size:13.5px; color:#2d3a33; line-height:1.55}
  .seam .b {font-size:12px; color:#68776e; margin-top:8px}
  .chip {display:inline-block; background:#edf4f9; color:#426b91; border-radius:12px; padding:2px 9px;
         font-size:11px; margin-right:4px; font-weight:600}
  .banner {background:#edf4f9; border:1px solid #cfe0ee; border-radius:10px; padding:10px 14px; font-size:13px; margin:6px 0 10px}
  .disclaimer {color:#8a978f; font-size:11px; margin-top:24px; text-align:center}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def client():
    return SeamClient()


def act(fn, *a, **k):
    try:
        out = fn(*a, **k)
        if isinstance(out, dict) and "diff" in out:
            st.session_state["last_diff"] = out["diff"]
        st.rerun()
    except SeamError as err:
        st.error(str(err))


def pill(status: str, big: bool = False) -> str:
    label, cls = STATUS[status]
    return f'<span class="pill {cls}{" big" if big else ""}">{label}</span>'


c = client()
p = c.passport()
prod = p["product"]
blocking = p.get("blocking_seams", [])
open_seams = [s for s in p["seams"] if s["status"] == "open"]
totals = {k: sum(d.get("results", {}).get(k, 0) for d in p["departments"].values()) for k in ("passed", "failed", "needs_review")}
days = (date.fromisoformat(prod["launch_date"]) - date.fromisoformat(p["as_of"])).days
signoff = p["signoff"]

# ---------- brand bar + review header ----------
st.markdown(f"""
<div class="brand"><div class="mark">◆</div>
  <div><div class="name">Compliance Seam Detector</div>
       <div class="tag">Cross-department compliance review · HR · Finance · Legal</div></div>
  <div class="meta">Rules {e(p['policy_versions']['rules'])} · Policy {e(p['policy_versions']['tiers'])}<br>
       Last verified {e(str(p['last_verified'])[:16].replace('T', ' '))} UTC · Audit chain
       {'intact ✓' if p['audit']['ok'] else 'BROKEN ✗'}</div>
</div>
<div class="hero">
  <div><div class="sub">Review subject</div>
       <h1>{e(prod['name'])} v{e(prod['version'])} launch readiness</h1>
       <div class="sub">{e(p['company'])} · launch {e(prod['launch_date'])} · as of {e(p['as_of'])}</div></div>
  <div style="margin-left:auto">{pill(p['overall'], big=True)}</div>
</div>
<div class="cards">
  <div class="card"><div class="lbl">Checks passed</div><div class="val">{totals['passed']}
       <small>of {sum(totals.values())}</small></div></div>
  <div class="card"><div class="lbl">Failed · needs review</div><div class="val">{totals['failed']}
       <small>· {totals['needs_review']} review</small></div></div>
  <div class="card"><div class="lbl">Cross-department seams</div><div class="val">{len(open_seams)}
       <small>open · {len(blocking)} blocking</small></div></div>
  <div class="card"><div class="lbl">Sign-off</div><div class="val" style="font-size:19px">{e(signoff['state'].replace('_', '-').upper())}
       <small>{e(signoff.get('by') or '')}</small></div></div>
  <div class="card"><div class="lbl">Launch in</div><div class="val">{days} <small>days</small></div></div>
</div>
""", unsafe_allow_html=True)

dept_html = []
for name, d in p["departments"].items():
    r = d.get("results", {})
    counts = (f"✅ {r.get('passed', 0)} &nbsp; ❌ {r.get('failed', 0)} &nbsp; ❔ {r.get('needs_review', 0)}"
              if d["records"] else "shared context")
    dept_html.append(f"""<div class="card dept"><h4>{e(name)}</h4>
      <div class="row">On its own {pill(d['own_view'])}</div>
      <div class="row">With seams {pill(d['status'])}</div>
      <div class="counts">{counts} · {len(d['open_seams'])} seam(s)</div></div>""")
st.markdown(f'<div class="depts">{"".join(dept_html)}</div>', unsafe_allow_html=True)

if "last_diff" in st.session_state:
    d = st.session_state["last_diff"]
    parts = [f"{k} {', '.join(d[k])}" for k in ("opened", "closed", "changed") if d[k]]
    st.markdown(f"""<div class="banner"><b>Last change · {e(str(d['event'].get('id') or d['event'].get('type')))}</b>
      — {e(d['event'].get('description') or '')}<br>{e('; '.join(parts) or 'no seam changes')} ·
      overall {pill(d['status_before'])} → {pill(d['status_after'])} · re-checked {len(d['rechecked_nodes'])} nodes
      {'(verified against a full re-check ✓)' if d['selective_matches_full'] else ''}</div>""", unsafe_allow_html=True)

# ---------- sections (persist across reruns, unlike tabs) ----------
SECTIONS = ["⚖️ Conflicts", "💬 Ask", "🔗 Seams", "🧪 Live check", "✍️ Sign-off", "📄 Report", "🕒 Activity"]
nav = (st.segmented_control("Section", SECTIONS, default=SECTIONS[0], key="nav", label_visibility="collapsed")
       if hasattr(st, "segmented_control") else st.radio("Section", SECTIONS, horizontal=True, key="nav"))
nav = nav or SECTIONS[0]

if nav == SECTIONS[0]:
    conflicts_view(c, p, act)          # default landing view: HR passes, Legal passes, yet they conflict

elif nav == SECTIONS[1]:
    audit_chat(c)

elif nav == SECTIONS[2]:
    st.caption("Gaps that only appear when departments' data is read together. Ranked by severity and urgency.")
    for s in p["seams"]:
        cls = "waived" if s["status"] == "waived" else SEV.get(s["severity"], "cond")
        sev = f'<span class="pill {"muted" if s["status"] == "waived" else SEV.get(s["severity"], "cond")}">' \
              f'{"WAIVED" if s["status"] == "waived" else e(s["severity"].upper())}</span>'
        block = '<span class="pill nogo">BLOCKS LAUNCH</span>' if s["blocks_launch"] and s["status"] == "open" \
            else '<span class="pill muted">does not block launch</span>' if not s["blocks_launch"] else ""
        chips = "".join(f'<span class="chip">{e(x)}</span>' for x in s["departments"])
        fixes = "".join(f"<li>{e(f)}</li>" for f in s["fix_options"])
        waiver = (f'<div class="b">Waived by <b>{e(s["waiver"]["by"])}</b> ({e(s["waiver"]["role"])}): '
                  f'{e(s["waiver"]["reason"])}</div>') if s.get("waiver") else ""
        st.markdown(f"""<div class="seam {cls}">{sev} {block} {chips}
          <div class="t">{e(s['title'])}</div>
          <div class="x">{e(s['explanation'])}</div>
          <div class="x" style="margin-top:6px"><b>Fix options</b><ul style="margin:4px 0 0 18px">{fixes}</ul></div>
          <div class="b">Basis: {e(' | '.join(s['basis']))}</div>
          <div class="b">Fix owner: <b>{e(s['fix_owner'] or '—')}</b> · score {s['score']:.0f} ·
               explained by {e(str(s['facts'].get('explained_by')))}</div>{waiver}</div>""", unsafe_allow_html=True)
    if not p["seams"]:
        st.success("No cross-department seams. Every department's data agrees.")

elif nav == SECTIONS[3]:
    live_check(c)
    st.divider()
    ev_col, sc_col = st.columns(2)
    with ev_col:
        st.markdown("**Event stream** · what happened next in the business")
        for ev in p["events"]:
            if st.button(f"{'✅' if ev['applied'] else '▶️'} {ev['event_id']} · {ev['date']} · {ev['description'][:80]}",
                         key=ev["event_id"], disabled=ev["applied"], width="stretch"):
                act(c.apply_stream, ev["event_id"])
    with sc_col:
        st.markdown("**What-if scenarios** · prepared tests")
        for sc in p.get("scenarios", []):
            if st.button(f"{'✅' if sc['applied'] else '🧪'} {sc['description'][:95]}",
                         key=sc["name"], disabled=sc["applied"], width="stretch"):
                act(c.scenario, sc["name"])

elif nav == SECTIONS[4]:
    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Launch decision** · a named person signs; GO is refused while blocking seams are open")
        with st.form("sign"):
            name, role = st.text_input("Your name"), st.text_input("Your role")
            decision = st.selectbox("Decision", ["go", "no_go", "waive"],
                                    format_func={"go": "GO", "no_go": "NO-GO", "waive": "Waive a seam"}.get)
            seam_id = st.selectbox("Seam (for waive)", [None] + [s["id"] for s in open_seams],
                                   format_func=lambda x: "—" if x is None else next(s["title"] for s in p["seams"] if s["id"] == x))
            reason = st.text_area("Reason")
            if st.form_submit_button("Sign", type="primary"):
                act(c.sign, decision, name, role, reason, seam_id)
        if signoff.get("invalidated"):
            st.warning(f"Previous sign-off was reset: {signoff.get('reason')}")
    with right:
        st.markdown("**Agent drafts** · prepared by the system, need a human to approve")
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
        if not p["drafts"]:
            st.caption("No drafts waiting.")

elif nav == SECTIONS[5]:
    report_html = render_report(p, c.audit())   # built from the same passport as the screen
    st.download_button("⬇ Download audit report (HTML)", report_html, "compliance-audit-report.html", "text/html",
                       type="primary", help="One self-contained HTML file that opens offline.")
    if hasattr(st, "iframe"):   # report HTML is fully escaped by seam/report.py
        st.iframe(report_html, height=900)
    else:
        components.html(report_html, height=900, scrolling=True)

else:
    a = c.audit()
    st.markdown(f"**Audit chain** {'intact ✓' if a['verify']['ok'] else 'BROKEN ✗'} · {a['verify']['entries']} entries")
    st.dataframe([{"#": x["seq"], "when": x["at"], "what": x["kind"], "who": x["actor"]} for x in reversed(a["entries"])],
                 width="stretch", hide_index=True)
    st.markdown("**Evidence expiring soon**")
    st.dataframe(p["evidence_expiring"], width="stretch", hide_index=True)

with st.sidebar:
    data_panel(c)                      # left panel: the data and documents behind the review
    st.divider()
    st.markdown("**Demo controls**")
    if st.button("↺ Reset to start", width="stretch"):
        st.session_state.pop("last_diff", None)
        st.session_state.pop("audit_chat", None)
        st.session_state.pop("live_sim", None)
        act(c.reset)
    st.caption(f"Backend: {c.mode}")

st.markdown(f'<div class="disclaimer">{e(p["disclaimer"])}</div>', unsafe_allow_html=True)

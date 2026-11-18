"""Landing view: three cases where HR passes and Legal passes, but together they conflict."""
from __future__ import annotations

import html

import streamlit as st

from seam.client import SeamClient
from seam.conflicts import conflicts

e = html.escape
RES = {"passed": ("PASSED", "go"), "failed": ("FAILED", "nogo"), "needs_review": ("NEEDS REVIEW", "cond"),
       "missing": ("NOT FOUND", "muted")}
CSS = """
<style>
  .cx-intro {background:#fff; border:1px solid #e0e8e2; border-left:5px solid #176b4a; border-radius:10px;
             padding:12px 16px; margin:4px 0 10px; font-size:13.5px; color:#2d3a33; line-height:1.55}
  .cx {background:#fff; border:1px solid #e0e8e2; border-radius:12px; padding:14px 16px; margin:12px 0;
       box-shadow:0 7px 24px #1633240a}
  .cx .head {display:flex; align-items:center; gap:10px; margin-bottom:10px}
  .cx .num {width:26px; height:26px; border-radius:50%; background:#17251f; color:#fff; display:grid;
            place-items:center; font-weight:750; font-size:13px; flex:none}
  .cx .ttl {font-weight:740; font-size:16px; color:#17251f; letter-spacing:-.02em}
  .cx .grid {display:grid; grid-template-columns:1fr 1fr 1.35fr; gap:10px}
  .cx .box {border:1px solid #e0e8e2; border-radius:9px; padding:10px 12px; background:#fbfcfb; font-size:12.5px;
            color:#3d4b43; line-height:1.5}
  .cx .box h5 {margin:0 0 6px; font-size:11px; letter-spacing:.09em; text-transform:uppercase; color:#68776e;
               display:flex; justify-content:space-between; align-items:center}
  .cx .box.together {border-color:#efc2bd; background:#fdf5f4}
  .cx .box.ok {border-color:#b9dcc7; background:#f5fbf7}
  .cx .box .req {font-weight:620; color:#17251f; margin-bottom:4px}
  .cx .box .fnd {color:#526158}
  .cx .box .rid {font:11px ui-monospace,Consolas,monospace; color:#68776e; margin-top:4px}
  .cx .why {font-size:12.5px; color:#526158; margin-top:10px}
  .cx .fix {font-size:12px; color:#176b4a; margin-top:4px; font-weight:600}
  @media (max-width:900px) {.cx .grid {grid-template-columns:1fr}}
</style>
"""


def _pill(res: str) -> str:
    label, cls = RES[res]
    return f'<span class="pill {cls}">{label}</span>'


def _side(title: str, s: dict) -> str:
    ok = " ok" if s["result"] == "passed" else ""
    return (f'<div class="box{ok}"><h5>{title} {_pill(s["result"])}</h5>'
            f'<div class="req">{e(s["description"] or "—")}</div>'
            f'<div class="fnd">{e(s["finding"])}</div><div class="rid">{e(s["record"])}</div></div>')


def _together(c: dict) -> str:
    s, state = c["seam_data"], c["state"]
    if state == "resolved":
        return ('<div class="box ok"><h5>Together <span class="pill go">RESOLVED</span></h5>'
                '<div class="req">No conflict is open any more.</div>'
                '<div class="fnd">The records now agree when read together (for example after a fix or an event).</div></div>')
    pill = '<span class="pill muted">WAIVED</span>' if state == "waived" else '<span class="pill nogo">CONFLICT</span>'
    block = ('<span class="pill nogo">BLOCKS LAUNCH</span>' if s["blocks_launch"] and state == "conflict"
             else '<span class="pill muted">does not block launch</span>' if not s["blocks_launch"] else "")
    chips = "".join(f'<span class="chip">{e(d)}</span>' for d in s["departments"])
    return (f'<div class="box together"><h5>Together {pill}</h5><div class="req">{e(s["title"])}</div>'
            f'<div class="fnd">{e(s["explanation"])}</div><div style="margin-top:6px">{chips} {block}</div></div>')


def render(c: SeamClient, p: dict, act) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    cases = conflicts(p)
    open_n = sum(1 for x in cases if x["state"] == "conflict")
    st.markdown(
        f'<div class="cx-intro"><b>Passing on its own is not the same as being compliant.</b> In these three cases '
        f"HR's check passes and Legal's check passes, yet the two conflict once their data are read together. "
        f'<b>{open_n} of {len(cases)}</b> conflicts are open right now.</div>', unsafe_allow_html=True)
    for x in cases:
        st.markdown(
            f'<div class="cx"><div class="head"><div class="num">{x["n"]}</div><div class="ttl">{e(x["title"])}</div></div>'
            f'<div class="grid">{_side("HR", x["hr_side"])}{_side("Legal", x["legal_side"])}{_together(x)}</div>'
            f'<div class="why"><b>Why it slips through:</b> {e(x["why"])}</div>'
            f'<div class="fix">Fix: {e(x["fix_hint"])}</div></div>', unsafe_allow_html=True)
        sc = x.get("scenario_info")
        if sc and st.button(f"🧪 Show the fix for scenario {x['n']}: {sc['description'][:90]}", key=f"cx-{sc['name']}",
                            disabled=sc["applied"]):
            act(c.scenario, sc["name"])

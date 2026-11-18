"""Left panel: the data and documents the review is built from, grouped by department, with a live preview."""
from __future__ import annotations

import html

import streamlit as st

from seam.client import SeamClient, SeamError

e = html.escape
COLOR = {"HR": "#2563eb", "Finance": "#059669", "Legal": "#b45309", "Product": "#6b7280"}
ICON = {"table": "▦", "document": "📄", "record": "{ }"}
CSS = """
<style>
  .ds-label {font-size:11px; font-weight:750; letter-spacing:.1em; color:#68776e; margin:4px 0 6px}
  .ds-conn {background:#ecf8f1; border:1px solid #b9dcc7; border-radius:10px; padding:8px 12px; font-size:12px;
            color:#176b4a; line-height:1.45}
  .ds-conn b {display:block; font-size:13px}
  .ds-conn:before {content:""; display:inline-block; width:8px; height:8px; border-radius:50%; background:#059669;
                   margin-right:7px}
  .ds-dept {border-left:4px solid var(--c); padding:1px 0 1px 8px; margin:12px 0 4px; font-weight:720; font-size:13px;
            color:var(--c)}
  .ds-file {display:flex; justify-content:space-between; gap:8px; font-size:12px; padding:2px 0 2px 12px; color:#2d3a33}
  .ds-file span:first-child {font-family:ui-monospace,Consolas,monospace; overflow-wrap:anywhere}
  .ds-file span:last-child {color:#68776e; white-space:nowrap}
  .ds-scroll {max-height:280px; overflow:auto; border:1px solid #e0e8e2; border-radius:8px; background:#fff}
  .ds-table {border-collapse:collapse; font-size:10.5px; white-space:nowrap}
  .ds-table th {position:sticky; top:0; background:#f3f6f4; text-align:left; padding:4px 7px; color:#526158}
  .ds-table td {padding:3px 7px; border-top:1px solid #eef2ef; color:#2d3a33}
  .ds-note {font-size:11px; color:#8a978f; margin-top:10px; line-height:1.5}
</style>
"""


def _table(rows: list[dict]) -> str:
    if not rows:
        return "<i>empty</i>"
    cols = list(rows[0])
    head = "".join(f"<th>{e(str(k))}</th>" for k in cols)
    body = "".join("<tr>" + "".join(f"<td>{e(str(r.get(k, '')))}</td>" for k in cols) + "</tr>" for r in rows)
    return (f'<div class="ds-scroll"><table class="ds-table"><tr>{head}</tr>{body}</table></div>')


def render(c: SeamClient) -> None:
    try:
        src = c.sources()
    except SeamError as err:
        st.caption(f"Data source unavailable: {err}")
        return
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="ds-label">DATA SOURCE</div>', unsafe_allow_html=True)
    where = src["path"].replace("\\", "/").rstrip("/").split("/")[-1] or src["path"]
    ev = f" · {src['applied_events']} event(s) applied" if src["applied_events"] else ""
    st.markdown(f'<div class="ds-conn"><b>Connected · {e(where)}/</b>Read-only · as of {e(str(src["as_of"]))}{e(ev)}</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="ds-label" style="margin-top:14px">DATA &amp; DOCUMENTS</div>', unsafe_allow_html=True)
    options: dict[str, str] = {}
    for d in src["departments"]:
        rows = "".join(f'<div class="ds-file"><span>{ICON.get(f["kind"], "")} {e(f["name"])}</span>'
                       f'<span>{f["size"]} {e(f["unit"])}</span></div>' for f in d["files"])
        st.markdown(f'<div class="ds-dept" style="--c:{COLOR.get(d["name"], "#6b7280")}">{e(d["name"])}</div>{rows}',
                    unsafe_allow_html=True)
        for f in d["files"]:
            options[f"{d['name']} · {f['name']}"] = f["file"]
    if not src["departments"]:
        st.caption("Running on a records.json file: no source documents to list.")
        return

    choice = st.selectbox("Open a file", ["—", *options], key="ds_open", label_visibility="visible")
    if choice != "—":
        try:
            doc = c.source_content(options[choice])
        except SeamError as err:
            st.error(str(err))
            return
        if doc["kind"] == "table":
            st.markdown(_table(doc["rows"]), unsafe_allow_html=True)   # plain HTML: no pyarrow/numpy dependency
            if doc["total"] > len(doc["rows"]):
                st.caption(f"Showing {len(doc['rows'])} of {doc['total']} rows")
        elif doc["kind"] == "document":
            st.markdown(doc["text"])
        else:
            st.json(doc["json"], expanded=2)
    st.markdown('<div class="ds-note">Each department is checked on its own tables first. Questions that need two '
                'or more departments show up as seams.</div>', unsafe_allow_html=True)

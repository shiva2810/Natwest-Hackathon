"""Audit report: turns a passport (and optionally the audit trail) into one self-contained HTML file.

The layout follows samples/compliance-checker/sample-audit-report.html: domain filters, status filters,
findings with a four-step decision trail, and a policy-to-evidence evaluation for every finding.
The file has no external assets, so it can be saved, emailed or opened offline.

    from seam.report import render_report
    html = render_report(client.passport(), client.audit())

The engine decides every status; this module only displays what the passport says.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

DOMAIN_ORDER = ["HR", "Legal", "Finance", "Product"]
LABEL = {"fail": "FAILED", "review": "NEEDS REVIEW", "pass": "PASSED"}
OVERALL = {"no_go": ("Action required", "fail"), "conditional": ("Conditional", "review"), "go": ("Cleared", "pass")}
GO_WORD = {"go": "Go", "conditional": "Conditional", "no_go": "No-go"}

# What each seam rule checks, in plain language (the "policy requirement" column of the evaluation).
RULE_TEXT = {
    "orphaned_owner": ("Owner continuity",
                       "Every obligation owned outside HR must have an owner who is still active on the launch date."),
    "version_drift": ("Approval covers the launch version",
                      "A product approval must cover the exact version that ships."),
    "unvetted_vendor": ("Vendor due diligence",
                        "A signed contract needs a vendor whose due diligence is complete and still valid at launch."),
    "training_lapse": ("Required training valid at launch",
                       "An obligation owner must hold the required training, valid on the launch date."),
    "approval_limit_breach": ("Signing authority",
                              "A contract must be signed by someone whose approval limit covers its value."),
    "seller_training_gap": ("Seller training valid at first sale",
                            "Every seller assigned to the product must hold valid required training on their first sales date."),
    "data_residency_breach": ("Data residency",
                              "Suppliers must not process customer data outside the regions the customer terms promise."),
    "support_capacity_gap": ("Support capacity",
                             "Staffing must cover the support hours promised to customers."),
    "unbudgeted_contract": ("Budget coverage",
                            "A signed contract must be covered by approved Finance budget lines."),
}
KIND_TEXT = {
    "role_owner": "The obligation has a named, active owner.",
    "training_required": "The owner holds the required course and it has not expired.",
    "product_approval": "The product has an approval on file.",
    "vendor_due_diligence": "The vendor has passed due diligence.",
    "budget_line": "The spend is covered by a budget line.",
    "contract_term": "The required contract term is present.",
}
MONEY_KEYS = {"value", "approval_limit", "budgeted", "amount"}
HIDDEN_FACTS = {"score_reasons", "explained_by", "evidence", "quote"}


def e(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def _fmt(key: str, v: Any) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool) and key in MONEY_KEYS:
        return f"£{v:,.0f}"
    if isinstance(v, list):
        return "; ".join(str(i) for i in v)
    return "—" if v in (None, "None", "") else str(v)


def _kv(rows: list[tuple[str, Any]]) -> str:
    return "".join(f'<div class="kv"><span>{e(k)}</span><b>{e(v)}</b></div>' for k, v in rows)


def _tags(domains: list[str]) -> str:
    return "".join(f'<span class="tag">{e(d)}</span>' for d in domains)


def _sources(evidence: list[dict]) -> str:
    out = ""
    for ev in evidence:
        quote = f' — “{e(ev["quote"])}”' if ev.get("quote") else ""
        exp = f' · expires {e(ev["expires_on"])}' if ev.get("expires_on") else ""
        out += f'<p><code>{e(ev["source"])}</code>{quote}{exp}</p>'
    return out or "<p>No source document recorded for this check.</p>"


# ---------------------------------------------------------------- findings

def _build_findings(p: dict) -> list[dict]:
    records = {r["id"]: r for r in p.get("records", [])}
    in_seam: dict[str, list[str]] = {}
    for s in p["seams"]:
        for rid in s["record_ids"]:
            in_seam.setdefault(rid, []).append(s["id"])
    rules_v = p["policy_versions"]["rules"]
    out: list[dict] = []

    for s in p["seams"]:                                    # already sorted by score
        waived = s["status"] == "waived"
        status = "review" if waived or s["severity"] in ("medium", "low") else "fail"
        name, req = RULE_TEXT.get(s["type"], (s["type"].replace("_", " ").title(), "Deterministic cross-department rule."))
        facts = [(k.replace("_", " ").capitalize(), _fmt(k, v)) for k, v in s["facts"].items() if k not in HIDDEN_FACTS]
        involved = [records[r] for r in s["record_ids"] if r in records]
        evidence = list(s["facts"].get("evidence", []))
        if s["facts"].get("quote"):
            evidence.append({"source": "linked record", "quote": s["facts"]["quote"]})
        for r in involved:
            evidence += r["evidence"]
        evidence = list({(x["source"], x.get("quote")): x for x in evidence}.values())   # same source cited twice -> once
        steps = [("Rule checked", f"{name} · {rules_v}", "View rule & requirement")]
        for d in s["departments"]:
            recs = [r["description"] for r in involved if r["department"] == d]
            steps.append((f"{d} evidence evaluated", recs[0] if recs else f"{d} data joined into this check.",
                          f"Open {d} evidence"))
        steps.append(("Decision assigned", f"{s['severity'].title()} severity · score {s['score']:g}", "Inspect decision basis"))
        verdict = (f"{e(s['explanation'])} Rule reference: <code>{e(s['type'])}</code> · severity "
                   f"<b>{e(s['severity'])}</b> · score {s['score']:g}"
                   + (f" ({e('; '.join(s['facts']['score_reasons']))})" if s["facts"].get("score_reasons") else "") + ".")
        if waived:
            w = s["waiver"] or {}
            verdict += (f" <b>Waived</b> by {e(w.get('by'))} ({e(w.get('role'))}) on {e(str(w.get('at', ''))[:10])}: "
                        f"“{e(w.get('reason'))}”. A waiver accepts the risk; it does not fix it.")
        out.append({
            "status": status, "pill": "WAIVED" if waived else LABEL[status], "title": s["title"],
            "domains": s["departments"], "order": (0 if status == "fail" else 1, -s["score"]),
            "meta": f"Cross-department · {s['severity']} severity · {name}"
                    + ("" if s.get("blocks_launch", True) else " · does not block launch"),
            "result": e(s["explanation"]),
            "fixes": s["fix_options"],
            "evidence_short": _kv(facts[:4]) + (f'<div class="kv"><span>Fix owner</span><b>{e(s["fix_owner"] or "unassigned")}</b></div>'),
            "steps": steps, "heading": f"{name} · {' + '.join(s['departments'])}",
            "policy": (f"<p><b>Requirement:</b> {e(req)}</p>"
                       f"<p><b>Why it is a seam:</b> each department's own record can look fine; the gap only appears "
                       f"when {e(' and '.join(s['departments']))} data are read together.</p>"
                       f"<p><code>{e(s['id'])} · {e(rules_v)}</code></p>"),
            "evidence": _kv(facts) + (f"<p><b>Basis:</b> {e(' | '.join(s['basis']))}</p>" if s.get("basis") else "")
                        + _sources(evidence),
            "verdict": verdict, "verdict_class": status,
        })

    for r in p.get("records", []):
        st = {"met": "pass", "unmet": "fail", "unknown": "review"}[r["status"]]
        seams_here = in_seam.get(r["id"], [])
        also = (f"Passes on its own, but is part of {len(seams_here)} open cross-department finding(s): "
                f"{', '.join(seams_here)}. A pass here is not a launch approval." if seams_here and st == "pass" else "")
        attrs = r.get("attributes", {})
        check = attrs.get("check") or {}
        generic = {"pass": "The check passes on the evidence recorded.",
                   "fail": "The recorded evidence does not meet the requirement.",
                   "review": "The evidence is missing, stale or could not be confirmed. A person must look at it."}[st]
        result = check.get("finding") or generic
        if check.get("basis") == "self_attested":
            result += " (self-attested: nobody has verified this against data)"
        items = check.get("items") or []
        source_line = " · ".join(x for x in (attrs.get("source_doc"), f"clause {attrs['clause']}" if attrs.get("clause") else "",
                                              f"version {attrs['doc_version']}" if attrs.get("doc_version") else "") if x)
        meta = [("Record", r["id"]), ("Kind", r["kind"].replace("_", " ")), ("Owner", r.get("owner") or "—"),
                ("Status", r["status"]), ("Basis", check.get("basis") or "—")]
        meta += [(k.replace("_", " ").capitalize(), _fmt(k, v)) for k, v in attrs.items()
                 if k not in ("check", "source_doc", "clause", "doc_version")]
        items_html = ("<p><b>Items found:</b></p><ul>" + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>") if items else ""
        ref = f'<p><code>{e(r["source_ref"])}</code></p>' if r.get("source_ref") else ""
        out.append({
            "status": st, "pill": LABEL[st], "title": r["description"], "domains": [r["department"]],
            "order": (2 if st == "pass" else 0 if st == "fail" else 1, 0),
            "meta": f"Single-department · {r['kind'].replace('_', ' ')}" + (f" · {source_line}" if source_line else ""),
            "result": e(result + (" " + also if also else "")), "fixes": [], "evidence_short": _kv(meta[:4]),
            "steps": [("Requirement checked", source_line or KIND_TEXT.get(r["kind"], r["kind"]), "View requirement"),
                      (f"{r['department']} data evaluated", result, "Open record fields"),
                      ("Scope checked", "This record alone, not the combined view." if not seams_here else "Also joined into a cross-department finding.", "Inspect scope"),
                      ("Decision assigned", LABEL[st].title(), "Inspect decision basis")],
            "heading": f"{r['id']} · {r['department']}",
            "policy": (f"<p><b>Requirement:</b> {e(r['description'])}</p>"
                       + (f"<p><b>Source:</b> {e(source_line)}</p>" if source_line else "") + ref),
            "evidence": _kv(meta) + f"<p><b>Result:</b> {e(result)}</p>" + items_html + _sources(r["evidence"]),
            "verdict": e(result + (" " + also if also else "")) + " Single-record check; it does not imply the whole department is clear.",
            "verdict_class": st,
        })

    out.sort(key=lambda f: f["order"])
    for i, f in enumerate(out, 1):
        f["n"] = i
    return out


def _finding_html(f: dict, rid: str) -> str:
    fixes = ("<div class=\"label\" style=\"margin-top:10px\">Fix options</div><div class=\"copy\"><ul>"
             + "".join(f"<li>{e(x)}</li>" for x in f["fixes"]) + "</ul></div>") if f["fixes"] else ""
    steps = "".join(f'<button class="step" data-target="eval-{f["n"]}"><b>{i} · {e(t)}</b><span>{e(d)}</span><em>{e(a)} ↗</em></button>'
                    for i, (t, d, a) in enumerate(f["steps"], 1))
    cls = "pass" if f["status"] == "pass" else "fail" if f["status"] == "fail" else "review"
    return (f'<article class="card finding{" open" if f["n"] == 1 else ""}" data-status="{f["status"]}" data-domains="{e(",".join(f["domains"]))}">'
            f'<div class="findhead"><span class="pill {cls}">{e(f["pill"])}</span><div><div class="ftitle">{e(f["title"])}</div>'
            f'<div class="fmeta">{_tags(f["domains"])}{e(f["meta"])} · {e(rid)}-F{f["n"]:02d}</div></div><span class="chev">⌄</span></div>'
            f'<div class="finddetail"><div class="twocol"><div><div class="label">Evaluation result</div><div class="copy">{f["result"]}</div>{fixes}</div>'
            f'<div><div class="label">Evidence compared</div><div class="facts">{f["evidence_short"]}</div>'
            f'<a class="detail-link" href="#eval-{f["n"]}">Open policy-to-evidence evaluation ↓</a></div></div>'
            f'<div class="trace"><div class="trace-title">How this decision was reached · choose a step to open its evaluation detail</div>'
            f'<div class="steps">{steps}</div></div></div></article>')


def _eval_html(f: dict, rid: str) -> str:
    cls = {"pass": "pass", "fail": "fail", "review": "review"}[f["status"]]
    vstyle = {"pass": ' style="border-color:var(--green);background:#f2faf5;color:#31533e"',
              "fail": ' style="border-color:var(--red);background:#fdf3f2;color:#5e2a26"', "review": ""}[f["status"]]
    return (f'<section class="eval" id="eval-{f["n"]}"><div class="eval-head"><span class="pill {cls}">{e(f["pill"])}</span>'
            f'<h3>{e(f["heading"])}</h3><small>Finding {e(rid)}-F{f["n"]:02d}</small></div>'
            f'<div class="evalgrid"><div class="sourcebox"><h4>Policy · what was required</h4>{f["policy"]}</div>'
            f'<div class="sourcebox"><h4>Internal evidence · exact fields and sources used</h4>{f["evidence"]}</div></div>'
            f'<div class="verdict"{vstyle}><b>Decision basis:</b> {f["verdict"]}</div></section>')


# ---------------------------------------------------------------- page sections

def _signoff_html(p: dict, drafts: list[dict]) -> str:
    so = p["signoff"]
    if so.get("state") in ("go", "no_go"):
        body = (f'<b>{GO_WORD[so["state"]]}</b> signed by <b>{e(so.get("by"))}</b> ({e(so.get("role"))}) at {e(so.get("at"))}.'
                f'<br>Reason: {e(so.get("reason"))}')
    else:
        body = "No named human has signed this review yet. The checker supports the audit; the auditor owns the final judgement."
        if so.get("invalidated"):
            body += f' <b>An earlier sign-off was invalidated:</b> {e(so.get("reason"))}.'
    waivers = [s for s in p["seams"] if s["status"] == "waived"]
    wv = "".join(f'<p><b>Waived:</b> {e(s["title"])} — {e((s["waiver"] or {}).get("by"))}: “{e((s["waiver"] or {}).get("reason"))}”</p>'
                 for s in waivers)
    dr = "".join(f'<p><b>Draft ({e(d["action"])}):</b> {e(d["summary"])} <em>· prepared by the agent, needs a named human to approve</em></p>'
                 for d in drafts)
    return (f'<div class="sect"><div><div class="eyebrow">Human decision</div><h2>Sign-off and open actions</h2></div></div>'
            f'<div class="card"><div class="copy">{body}</div>{wv}{dr}</div>')


def _expiring_html(p: dict) -> str:
    if not p["evidence_expiring"]:
        return ""
    rows = "".join(f'<div class="kv"><span>{e(x["what"])}</span><b>{e(x["expires_on"])}</b></div>' for x in p["evidence_expiring"])
    return (f'<div class="sect"><div><div class="eyebrow">Watch list</div><h2>Evidence expiring within 120 days</h2></div></div>'
            f'<div class="card">{rows}</div>')


def _audit_html(audit: dict | None) -> str:
    if not audit:
        return ""
    v = audit["verify"]
    badge = ('<span class="pill pass">HASH CHAIN INTACT</span>' if v["ok"]
             else f'<span class="pill fail">CHAIN BROKEN AT #{e(v["broken_at"])}</span>')
    rows = "".join(f'<tr><td>#{e(x["seq"])}</td><td>{e(str(x["at"]).replace("T", " ")[:19])}</td><td>{e(x["kind"].replace("_", " "))}</td>'
                   f'<td>{e(x["actor"])}</td><td><code>{e(str(x.get("hash", ""))[:12])}</code></td></tr>'
                   for x in reversed(audit["entries"][-15:]))
    head = f' · head <code>{e(v["head"][:16])}</code>' if v.get("head") else ""
    return (f'<div class="sect"><div><div class="eyebrow">Audit history</div><h2>Every run, event and sign-off, with a name</h2></div>{badge}</div>'
            f'<div class="card"><div class="copy">{e(v["entries"])} entries{head}. Machine findings and human decisions are logged separately.</div>'
            f'<table class="audit"><tr><th>Seq</th><th>Time (UTC)</th><th>Kind</th><th>Actor</th><th>Hash</th></tr>{rows}</table></div>')


# ---------------------------------------------------------------- page

def render_report(p: dict, audit: dict | None = None, generated_at: str | None = None) -> str:
    """Build the complete HTML document for one passport. Pure function: same input, same output."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    head = (audit or {}).get("verify", {}).get("head") or p.get("audit", {}).get("head") or ""
    rid = f"SD-{p['as_of'].replace('-', '')}" + (f"-{head[:6].upper()}" if head else "")
    findings = _build_findings(p)
    n = {s: sum(1 for f in findings if f["status"] == s) for s in ("fail", "review", "pass")}
    total = len(findings) or 1
    word, ocls = OVERALL[p["overall"]]
    prod = p["product"]
    depts = [d for d in DOMAIN_ORDER if d in {x for f in findings for x in f["domains"]}]
    depts += sorted({x for f in findings for x in f["domains"]} - set(depts))

    own = {d: v["own_view"] for d, v in p["departments"].items() if d in ("HR", "Legal", "Finance")}
    alone = ", ".join(f"{d} {GO_WORD[v]}" for d, v in own.items())
    open_seams = [s for s in p["seams"] if s["status"] == "open"]
    crit = sum(1 for s in open_seams if s["severity"] == "critical")
    summary = (f"Each department on its own: {alone}. Read together the result is <b>{GO_WORD[p['overall']]}</b>: "
               f"{len(open_seams)} open cross-department finding(s), {crit} critical. "
               + (f"Top issue: {e(open_seams[0]['title'])}. " if open_seams else "No cross-department gaps are open. ")
               + f"{n['fail']} check(s) failed, {n['review']} need review and {n['pass']} passed. "
               "A pass means that record meets its requirement, not that the launch is approved. "
               "Missing, stale or conflicting evidence is shown as needs-review and never counted as a pass.")
    so = p["signoff"]
    state = (f"Signed {GO_WORD[so['state']]} by {so['by']}" if so.get("state") in ("go", "no_go") else "Auditor review required")

    domain_btns = '<button class="domain active" data-domain="all">All domains</button>' + "".join(
        f'<button class="domain" data-domain="{e(d)}">{e(d)}</button>' for d in depts)
    meta = "".join(f"<span>{k} <b>{e(v)}</b></span>" for k, v in [
        ("Review ID", rid), ("Client", p["company"]), ("Product", f"{prod['name']} v{prod['version']}"),
        ("Launch", prod["launch_date"]), ("As of", p["as_of"]), ("Last verified", p["last_verified"][:16].replace("T", " ") + " UTC"),
        ("Rules", p["policy_versions"]["rules"]), ("Generated", generated_at[:19].replace("T", " ") + " UTC")])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(p['company'])} · compliance audit report · {e(prod['name'])}</title>
<style>{CSS}</style></head><body>
<header class="top"><div class="mark">S</div><div class="brand">Seam Detector</div><div class="crumb">/ Internal Audit / Reviews / <b>{e(rid)}</b></div><div class="user">{e(p['company'])} · Internal auditor</div></header>
<main class="wrap">
<div class="eyebrow">Compliance audit report</div>
<div class="title-row"><div><h1>{e(prod['name'])} v{e(prod['version'])} — launch readiness</h1>
<div class="sub">{e(p['company'])} · domains: {e(', '.join(d for d in depts if d != 'Product') or 'none')}</div></div><span class="state">{e(state)}</span></div>
<div class="meta">{meta}</div>
<div class="domainbar"><strong>Domains in this review</strong>{domain_btns}<span class="scope-note">Filter findings by the department whose data contributed.</span></div>
<div class="metrics"><div class="card"><div class="mlabel">Overall assessment</div><div class="mval ov-{ocls}" style="font-size:19px">{e(word)} <small>· {e(GO_WORD[p['overall']])} when departments are combined</small></div>
<div class="meter"><span style="width:{round(100 * n['pass'] / total)}%"></span></div><div class="mlabel" style="margin-top:6px">{n['pass']} of {len(findings)} checks passed</div></div>
<div class="card"><div class="mlabel">Passed</div><div class="mval">{n['pass']}</div></div>
<div class="card"><div class="mlabel">Failed</div><div class="mval" style="color:var(--red)">{n['fail']}</div></div>
<div class="card"><div class="mlabel">Needs review</div><div class="mval" style="color:var(--amber)">{n['review']}</div></div></div>
<div class="card summary"><div class="star">✳</div><div><h2>Auditor summary</h2><p>{summary}</p></div></div>
<div class="sect"><div><div class="eyebrow">Requirement evaluations</div><h2>Findings <span style="font-size:11px;color:var(--muted);font-weight:500">({len(findings)} checks)</span></h2></div>
<div class="filters"><button class="filter active" data-filter="all">All</button><button class="filter" data-filter="fail">Failed</button><button class="filter" data-filter="review">Review</button><button class="filter" data-filter="pass">Passed</button></div></div>
<div id="findings">{''.join(_finding_html(f, rid) for f in findings)}</div>
<div class="sect"><div><div class="eyebrow">Evaluation details</div><h2>Policy and internal evidence side by side</h2></div></div>
<div id="evals">{''.join(_eval_html(f, rid) for f in findings)}</div>
{_signoff_html(p, p["drafts"])}
{_expiring_html(p)}
{_audit_html(audit)}
<div class="toolrow"><button class="btn" id="print">Print / save as PDF</button><button class="btn primary" id="export">Download this report (.html)</button></div>
<div class="fineprint">{e(p['disclaimer'])} Statuses come from the deterministic rules in {e(p['policy_versions']['rules'])} and tiers {e(p['policy_versions']['tiers'])}; the
checker supports the audit and does not replace the auditor's judgement. Every finding lists the record identifiers and source files it used so it can be reproduced.</div>
</main><div class="toast" id="toast"></div>
<script>{JS}</script></body></html>
"""


CSS = """
:root{--ink:#17251f;--muted:#68776e;--line:#e0e8e2;--bg:#f4f7f4;--green:#176b4a;--g-bg:#e7f3ec;--red:#a33b34;--r-bg:#faecea;--amber:#8a6319;--a-bg:#fbf3df;--blue:#426b91;--b-bg:#edf4f9;--shadow:0 7px 24px #1633240a}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--green);text-decoration:underline;text-underline-offset:2px}
.top{position:sticky;top:0;z-index:5;height:58px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 max(22px,calc((100vw - 1180px)/2));gap:11px}
.mark{width:25px;height:25px;border-radius:8px;display:grid;place-items:center;background:var(--green);color:#fff;font-weight:800}
.brand{font-weight:760;font-size:16px;letter-spacing:-.04em}.crumb{margin-left:13px;color:var(--muted);font-size:12px}.user{margin-left:auto;color:var(--muted);font-size:11px}
.wrap{max-width:1180px;margin:28px auto 70px;padding:0 22px}
.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:10px;color:var(--muted);font-weight:750}
.title-row{display:flex;align-items:flex-start;gap:14px}.title-row h1{font-size:29px;line-height:1.15;letter-spacing:-.045em;margin:5px 0}.sub{font-size:13px;color:var(--muted)}
.state{margin-top:8px;margin-left:auto;background:var(--a-bg);color:var(--amber);border:1px solid #ead59e;padding:5px 10px;border-radius:20px;white-space:nowrap;font-size:11px;font-weight:700}
.meta{display:flex;flex-wrap:wrap;gap:10px 21px;background:#fff;border:1px solid var(--line);border-radius:10px;padding:13px 15px;margin:18px 0 13px;box-shadow:var(--shadow);font-size:11px;color:var(--muted)}.meta b{color:var(--ink);font-weight:650}
.domainbar{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:13px 0}.domainbar strong{font-size:11px;margin-right:5px}
.domain{border:1px solid var(--line);background:#fff;color:#526158;border-radius:18px;padding:6px 12px;font-size:11px;cursor:pointer}.domain.active{background:var(--green);border-color:var(--green);color:#fff;font-weight:700}
.scope-note{margin-left:auto;color:var(--muted);font-size:10px}
.metrics{display:grid;grid-template-columns:1.65fr repeat(3,1fr);gap:11px;margin:13px 0}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px;box-shadow:var(--shadow)}
.mlabel{font-size:11px;color:var(--muted)}.mval{font-size:26px;letter-spacing:-.04em;font-weight:740;margin-top:5px}.mval small{font-size:12px;letter-spacing:0;color:var(--muted);font-weight:500}
.ov-fail{color:var(--red)}.ov-review{color:var(--amber)}.ov-pass{color:var(--green)}
.meter{height:5px;background:#ecf0ed;border-radius:8px;overflow:hidden;margin-top:10px}.meter span{display:block;background:var(--green);height:100%}
.summary{display:flex;gap:11px;align-items:flex-start}.star{background:var(--b-bg);color:var(--blue);border-radius:8px;width:28px;height:28px;display:grid;place-items:center;flex:none}
.summary h2{font-size:13px;margin:0 0 4px}.summary p{font-size:12px;color:#4c5d53;margin:0;line-height:1.65}
.sect{display:flex;align-items:end;justify-content:space-between;margin:25px 0 10px}.sect h2{font-size:18px;letter-spacing:-.03em;margin:3px 0}
.filters{display:flex;gap:6px}.filter{background:#fff;border:1px solid var(--line);border-radius:6px;padding:6px 9px;color:#5c6961;font-size:10px;cursor:pointer}.filter.active{background:var(--g-bg);border-color:#b9d7c5;color:var(--green);font-weight:700}
.finding{padding:0;overflow:hidden;margin-bottom:9px}.findhead{display:flex;align-items:flex-start;gap:10px;padding:14px 15px;cursor:pointer}
.pill{min-width:62px;border-radius:15px;text-align:center;font-size:9px;font-weight:800;padding:4px 7px;white-space:nowrap}
.pass{background:var(--g-bg);color:var(--green)}.fail{background:var(--r-bg);color:var(--red)}.review{background:var(--a-bg);color:var(--amber)}
.ftitle{font-size:12px;font-weight:700}.fmeta{color:var(--muted);font-size:10px;margin-top:3px}.tag{margin-right:5px;background:#eef2ef;border-radius:4px;padding:1px 5px;font-weight:650;color:#4b5a51}
.chev{margin-left:auto;color:#849188;font-size:17px}
.finddetail{display:none;border-top:1px solid var(--line);padding:14px 16px 16px 86px;background:#fcfdfc}.finding.open .finddetail{display:block}.finding.open .chev{transform:rotate(180deg)}
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.label{color:#829087;text-transform:uppercase;letter-spacing:.09em;font-weight:750;font-size:9px;margin-bottom:5px}
.copy{font-size:11px;color:#526057;line-height:1.65}.copy ul{margin:4px 0 0;padding-left:16px}
.kv{display:flex;justify-content:space-between;gap:12px;font-size:10px;padding:3px 0;border-bottom:1px dashed var(--line)}.kv span{color:var(--muted)}.kv b{font-weight:650;text-align:right;overflow-wrap:anywhere}
.trace{margin-top:13px;padding-top:11px;border-top:1px solid var(--line)}.trace-title{font-size:10px;font-weight:750;color:var(--muted);margin-bottom:8px}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:7px}
.step{border:1px solid var(--line);background:#fff;border-radius:7px;padding:9px;cursor:pointer;text-align:left;color:var(--ink);font:inherit;transition:.15s}
.step:hover,.step:focus{border-color:#91bba2;background:#f5fbf7;outline:none;transform:translateY(-1px)}
.step b{display:block;font-size:9px;margin-bottom:4px}.step span{display:block;color:var(--muted);font-size:9px;line-height:1.45}.step em{display:block;font-style:normal;color:var(--green);font-size:8px;margin-top:5px;font-weight:750}
.detail-link{font-size:10px;display:inline-block;margin-top:6px}
.eval{scroll-margin-top:74px;border:1px solid #dce8df;border-radius:9px;background:#fff;padding:14px;margin:14px 0}.eval h3{font-size:14px;margin:0;letter-spacing:-.02em}
.eval-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}.eval-head small{color:var(--muted);font-size:10px;margin-left:auto}
.evalgrid{display:grid;grid-template-columns:1fr 1fr;gap:11px}.sourcebox{border:1px solid var(--line);border-radius:7px;padding:10px;background:#fbfcfb}.sourcebox h4{font-size:10px;margin:0 0 5px}
.sourcebox p{font-size:10px;color:#546158;line-height:1.6;margin:5px 0}.sourcebox code,.verdict code,.audit code{font:9px ui-monospace,Consolas,monospace;background:#f0f3f1;border-radius:4px;padding:2px 4px;color:#56645b}
.verdict{border-left:3px solid var(--amber);padding:8px 10px;background:#fffaf0;color:#5d4a22;border-radius:0 6px 6px 0;font-size:10px;line-height:1.6;margin-top:10px}
.audit{width:100%;border-collapse:collapse;font-size:10px;margin-top:10px}.audit th{text-align:left;color:var(--muted);font-weight:700;padding:4px 6px;border-bottom:1px solid var(--line)}.audit td{padding:4px 6px;border-bottom:1px dashed var(--line)}
.toolrow{display:flex;justify-content:flex-end;gap:7px;margin-top:15px}.btn{border:1px solid var(--line);background:#fff;border-radius:6px;padding:7px 10px;font-size:10px;font-weight:650;cursor:pointer}.btn.primary{background:var(--green);border-color:var(--green);color:#fff}
.fineprint{font-size:9px;line-height:1.7;color:#79867e;margin-top:18px}
.toast{position:fixed;bottom:20px;right:20px;padding:9px 13px;border-radius:7px;background:#20382b;color:#fff;font-size:11px;opacity:0;transition:.2s}.toast.show{opacity:1}
@media(max-width:760px){.wrap{padding:0 13px;margin-top:18px}.top{padding:0 13px}.user{display:none}.title-row h1{font-size:24px}.metrics{grid-template-columns:1fr 1fr}.metrics .card:first-child{grid-column:1/-1}
.sect{align-items:flex-start;flex-direction:column;gap:8px}.finddetail{padding:13px}.twocol,.evalgrid{grid-template-columns:1fr}.scope-note{width:100%;margin:3px 0 0}}
@media print{.top,.domainbar,.filters,.toolrow,.toast{display:none}.finddetail{display:block!important}.finding{display:block!important;break-inside:avoid}body{background:#fff}}
"""

JS = """
const cards=[...document.querySelectorAll('.finding')];
const evals=[...document.querySelectorAll('.eval')];
cards.forEach(c=>c.querySelector('.findhead').addEventListener('click',()=>c.classList.toggle('open')));
document.querySelectorAll('.step').forEach(b=>b.addEventListener('click',()=>{
  const t=document.getElementById(b.dataset.target);t.scrollIntoView({behavior:'smooth',block:'start'});
  t.style.boxShadow='0 0 0 3px #c8e3d1';setTimeout(()=>t.style.boxShadow='',1100)}));
let filter='all',domain='all';
function apply(){cards.forEach((c,i)=>{
  const ok=(filter==='all'||c.dataset.status===filter)&&(domain==='all'||c.dataset.domains.split(',').includes(domain));
  c.style.display=ok?'':'none';evals[i].style.display=ok?'':'none'})}
function pick(sel,attr,set){document.querySelectorAll(sel).forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll(sel).forEach(x=>x.classList.remove('active'));b.classList.add('active');set(b.dataset[attr]);apply()}))}
pick('.filter','filter',v=>filter=v);pick('.domain','domain',v=>domain=v);
function toast(s){const t=document.getElementById('toast');t.textContent=s;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200)}
document.getElementById('print').onclick=()=>window.print();
document.getElementById('export').onclick=()=>{
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob(['<!doctype html>'+document.documentElement.outerHTML],{type:'text/html'}));
  a.download='compliance-audit-report.html';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('Report downloaded')};
"""

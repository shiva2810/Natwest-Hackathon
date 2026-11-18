"""Self-check for the compliance seam detector dataset (stdlib only).

This is NOT the product. It independently recomputes the department checks and the five
seams from the raw files and compares them with answer_key/. If this passes, the dataset
and its answer key agree with each other.

Run from the dataset folder:  python tools/validate_dataset.py
"""
import copy
import csv
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = dt.date(2026, 11, 18)
LAUNCH = dt.date(2026, 12, 1)

FAILS = []
PASSES = []


def check(name, cond, detail=""):
    (PASSES if cond else FAILS).append(name if cond else f"{name} :: {detail}")


def d(s):
    return dt.date.fromisoformat(s)


def read_csv(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def read_json(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


CSV_FILES = [
    "hr/roster.csv", "hr/training_records.csv", "hr/product_staffing.csv", "hr/headcount_plan.csv",
    "finance/budget.csv", "finance/vendors.csv", "finance/approval_limits.csv", "finance/purchase_orders.csv",
    "legal/obligations_register.csv", "legal/contracts_register.csv",
]
JSON_FILES = ["legal/product_approval.json", "product/product_record.json"]


def load_world():
    w = {"headers": {}, "csv": {}, "json": {}}
    for rel in CSV_FILES:
        h, rows = read_csv(rel)
        w["headers"][rel] = h
        w["csv"][rel] = rows
    for rel in JSON_FILES:
        w["json"][rel] = read_json(rel)
    return w


def params(s):
    out = {}
    for part in (s or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------------------
# Seam computations (deterministic, from raw files only)
# ---------------------------------------------------------------------------
def inactive_at_launch(w):
    out = set()
    for r in w["csv"]["hr/roster.csv"]:
        if r["status"] == "left":
            out.add(r["employee_id"])
        elif r["status"] == "serving_notice" and r["last_working_day"] and d(r["last_working_day"]) < LAUNCH:
            out.add(r["employee_id"])
    return out


def seam_s1(w):
    gone = inactive_at_launch(w)
    legal = []
    asm = w["json"]["legal/product_approval.json"]["accountable_senior_manager"]
    if asm in gone:
        legal.append(f"ASM:{asm}")
    for o in w["csv"]["legal/obligations_register.csv"]:
        if o["owner_id"] in gone:
            legal.append(o["obligation_id"])
    # Finance: scopes where every approver valid at launch is gone
    scopes = {}
    for a in w["csv"]["finance/approval_limits.csv"]:
        if d(a["valid_from"]) <= LAUNCH <= d(a["valid_to"]):
            scopes.setdefault(a["scope"], []).append(a)
    fin = []
    for scope, rows in scopes.items():
        def covered(a):
            return a["approver_id"] not in gone or (a["delegate_id"] and a["delegate_id"] not in gone)
        if not any(covered(a) for a in rows):
            fin.append(f"SCOPE:{scope}")
    for po in w["csv"]["finance/purchase_orders.csv"]:
        if po["status"] == "pending_approval" and po["approver"] in gone:
            fin.append(po["po_id"])
    return {"legal": sorted(legal), "finance": sorted(fin), "open": bool(legal or fin)}


def seam_s2(w):
    course = params([o for o in w["csv"]["legal/obligations_register.csv"] if o["obligation_id"] == "OBL-L-002"][0]["parameters"])["course"]
    gone = {r["employee_id"] for r in w["csv"]["hr/roster.csv"] if r["status"] == "left"}
    bad = []
    for s in w["csv"]["hr/product_staffing.csv"]:
        if s["can_sell_or_onboard"] != "Y" or s["employee_id"] in gone:
            continue
        on = d(s["selling_from"])
        recs = [t for t in w["csv"]["hr/training_records.csv"]
                if t["employee_id"] == s["employee_id"] and t["course_code"] == course]
        ok = any(t["status"] == "valid" and t["expiry_date"] and d(t["expiry_date"]) >= on for t in recs)
        if not ok:
            bad.append(s["employee_id"])
    return sorted(bad)


def is_allowed_region(region):
    return region.startswith(("UK", "EU", "EEA"))


def seam_s3(w):
    vendors = {v["vendor_id"]: v for v in w["csv"]["finance/vendors.csv"]}
    bad = []
    for flow in w["json"]["product/product_record.json"]["data_flows"]:
        v = vendors[flow["processor_vendor_id"]]
        if v["handles_customer_data"] == "Y" and not is_allowed_region(v["data_processing_region"]):
            bad.append(v["vendor_id"])
    return sorted(set(bad))


def seam_s4(w):
    obl = [o for o in w["csv"]["legal/obligations_register.csv"] if o["obligation_id"] == "OBL-L-005"][0]
    need = int(params(obl["parameters"])["min_hours_per_week"])
    hc = {h["department"]: h for h in w["csv"]["hr/headcount_plan.csv"]}["Support"]
    gone = {r["employee_id"] for r in w["csv"]["hr/roster.csv"] if r["status"] == "left"}
    agents = [s for s in w["csv"]["hr/product_staffing.csv"]
              if s["role_on_product"] == "Support Agent" and s["employee_id"] not in gone]
    have = len(agents) * int(hc["weekly_contract_hours_per_head"])
    frozen = hc["hiring_status"] == "frozen" and d(hc["frozen_until"]) >= LAUNCH
    funded_24x7 = not any("business hours" in b["coverage_notes"].lower()
                          for b in w["csv"]["finance/budget.csv"] if b["line_id"] == "B-001")
    return {"need": need, "have": have, "shortfall": max(0, need - have), "frozen": frozen,
            "funded_24x7": funded_24x7, "open": need > have and frozen and not funded_24x7}


def seam_s5(w):
    appr = w["json"]["legal/product_approval.json"]
    prod = w["json"]["product/product_record.json"]
    material = [c["id"] for c in prod["changes"] if c["material"]]
    open_ = (appr["approved_version"] != prod["release_candidate"] and bool(material)
             and not prod["change_control_request_filed"])
    return {"material": material, "open": open_}


def open_seams(w):
    out = []
    if seam_s1(w)["open"]:
        out.append("S1")
    if seam_s2(w):
        out.append("S2")
    if seam_s3(w):
        out.append("S3")
    if seam_s4(w)["open"]:
        out.append("S4")
    if seam_s5(w)["open"]:
        out.append("S5")
    return out


# ---------------------------------------------------------------------------
# Department checks (each department sees only its own folder)
# ---------------------------------------------------------------------------
def dept_checks(w, as_of):
    res = {}
    train = w["csv"]["hr/training_records.csv"]
    roster = w["csv"]["hr/roster.csv"]
    active = [r["employee_id"] for r in roster if r["status"] != "left"]

    def invalid(course):
        bad = []
        for e in active:
            recs = [t for t in train if t["employee_id"] == e and t["course_code"] == course]
            if not any(t["expiry_date"] and d(t["expiry_date"]) >= as_of for t in recs):
                bad.append(e)
        return bad

    res["HR-C1"] = invalid("COC-100")
    res["HR-C2"] = invalid("DPA-110")
    res["HR-C3"] = [r["employee_id"] for r in roster
                    if r["status"] == "serving_notice" and r["leaver_checklist"] not in ("initiated", "complete")]
    hc = w["csv"]["hr/headcount_plan.csv"]
    res["HR-C4"] = [h["department"] for h in hc if int(h["filled_heads"]) > int(h["approved_heads"])]
    res["HR-C5"] = [h["department"] for h in hc
                    if h["hiring_status"] == "frozen" and d(h["frozen_until"]) >= as_of and int(h["open_reqs"]) > 0]

    res["FIN-C1"] = [b["line_id"] for b in w["csv"]["finance/budget.csv"]
                     if int(b["committed_gbp"]) > int(b["approved_budget_gbp"])]
    limits = {}
    for a in w["csv"]["finance/approval_limits.csv"]:
        limits.setdefault(a["approver_id"], []).append(a)
    approved = [p for p in w["csv"]["finance/purchase_orders.csv"] if p["status"] == "approved"]

    def limit_of(eid):
        return max((int(a["limit_gbp"]) for a in limits.get(eid, [])), default=0)

    res["FIN-C2"] = [p["po_id"] for p in approved if limit_of(p["approver"]) < int(p["amount_gbp"])]
    asm_ids = {a["approver_id"] for rows in limits.values() for a in rows
               if "accountable senior manager" in a["role_title"].lower() and "QuickPay" in a["scope"]}
    res["FIN-C3"] = [p["po_id"] for p in approved
                     if p["product"] == "QuickPay" and int(p["amount_gbp"]) > 40000 and p["approver"] not in asm_ids]
    vend = {v["vendor_id"]: v for v in w["csv"]["finance/vendors.csv"]}
    c4 = []
    for vid, v in vend.items():
        pos = sorted(d(p["approval_date"]) for p in approved if p["vendor_id"] == vid)
        if pos and not (v["dd_status"] == "completed" and d(v["dd_completed_date"]) <= pos[0]):
            c4.append(vid)
    res["FIN-C4"] = c4

    appr = w["json"]["legal/product_approval.json"]
    res["LEG-C1"] = [] if d(appr["approved_on"]) <= as_of <= d(appr["valid_until"]) else [appr["approval_id"]]
    obls = w["csv"]["legal/obligations_register.csv"]
    res["LEG-C2"] = [o["obligation_id"] for o in obls
                     if not o["owner_id"] or not o["last_reviewed"] or (as_of - d(o["last_reviewed"])).days > 365]
    res["LEG-C3"] = [c["contract_id"] for c in w["csv"]["legal/contracts_register.csv"] if d(c["end_date"]) < as_of]
    res["LEG-C4"] = [c["contract_id"] for c in w["csv"]["legal/contracts_register.csv"]
                     if c["dpa_required"] == "Y" and c["dpa_signed"] != "Y"]
    missing = [o for o in obls if o["evidence_status"] == "not_found"]
    res["LEG-C5"] = [o["obligation_id"] for o in missing]
    overdue = [o["obligation_id"] for o in missing
               if params(o["parameters"]).get("due_date") and d(params(o["parameters"])["due_date"]) < as_of]
    return res, overdue


def status_of(check_id, exceptions, overdue):
    if check_id == "LEG-C5":
        if not exceptions:
            return "met"
        return "unmet" if overdue else "unknown"
    return "met" if not exceptions else "unmet"


# ---------------------------------------------------------------------------
# Event application
# ---------------------------------------------------------------------------
def apply_change(w, ch):
    f, op = ch["file"], ch["op"]
    if f in w["csv"]:
        rows = w["csv"][f]
        if op == "insert":
            assert set(ch["row"].keys()) == set(w["headers"][f]), f"insert columns mismatch for {f}"
            rows.append({k: str(v) for k, v in ch["row"].items()})
        elif op == "update":
            hit = [r for r in rows if all(r[k] == v for k, v in ch["match"].items())]
            assert len(hit) == 1, f"update on {f} matched {len(hit)} rows: {ch['match']}"
            for k, v in ch["set"].items():
                assert k in hit[0], f"unknown column {k} in {f}"
                hit[0][k] = str(v)
        else:
            raise AssertionError(f"bad op {op} for csv")
    else:
        doc = w["json"][f]
        if op == "set":
            assert ch["path"] in doc
            doc[ch["path"]] = ch["value"]
        elif op == "append":
            doc[ch["path"]].append(ch["value"])
        else:
            raise AssertionError(f"bad op {op} for json")


# ---------------------------------------------------------------------------
def main():
    base = load_world()
    roster = {r["employee_id"]: r for r in base["csv"]["hr/roster.csv"]}
    vendors = {v["vendor_id"]: v for v in base["csv"]["finance/vendors.csv"]}

    # ---- 1. Referential integrity ----
    emp_refs = []
    for r in base["csv"]["hr/roster.csv"]:
        if r["manager_id"]:
            emp_refs.append(("roster.manager_id", r["manager_id"]))
    for t in base["csv"]["hr/training_records.csv"]:
        emp_refs.append(("training.employee_id", t["employee_id"]))
    for s in base["csv"]["hr/product_staffing.csv"]:
        emp_refs.append(("staffing.employee_id", s["employee_id"]))
    for a in base["csv"]["finance/approval_limits.csv"]:
        emp_refs += [("limits.approver_id", a["approver_id"])] + ([("limits.delegate_id", a["delegate_id"])] if a["delegate_id"] else [])
    for p in base["csv"]["finance/purchase_orders.csv"]:
        emp_refs += [("po.requested_by", p["requested_by"])] + ([("po.approver", p["approver"])] if p["approver"] else [])
    for b in base["csv"]["finance/budget.csv"]:
        emp_refs.append(("budget.owner_id", b["owner_id"]))
    for v in base["csv"]["finance/vendors.csv"]:
        emp_refs.append(("vendors.business_owner_id", v["business_owner_id"]))
    for o in base["csv"]["legal/obligations_register.csv"]:
        emp_refs.append(("obligations.owner_id", o["owner_id"]))
    for c in base["csv"]["legal/contracts_register.csv"]:
        emp_refs.append(("contracts.legal_owner_id", c["legal_owner_id"]))
    pa = base["json"]["legal/product_approval.json"]
    emp_refs += [("approval.asm", pa["accountable_senior_manager"])] + [("approval.approved_by", e) for e in pa["approved_by"]]
    emp_refs += [("product.owner", base["json"]["product/product_record.json"]["product_owner"]),
                 ("product.eng_lead", base["json"]["product/product_record.json"]["engineering_lead"])]
    bad = [(k, e) for k, e in emp_refs if e not in roster]
    check("integrity: every employee id exists in roster", not bad, str(bad))

    ven_refs = [("po", p["vendor_id"]) for p in base["csv"]["finance/purchase_orders.csv"]]
    ven_refs += [("contract", c["vendor_id"]) for c in base["csv"]["legal/contracts_register.csv"]]
    ven_refs += [("flow", f["processor_vendor_id"]) for f in base["json"]["product/product_record.json"]["data_flows"]]
    bad = [(k, v) for k, v in ven_refs if v not in vendors]
    check("integrity: every vendor id exists in vendors.csv", not bad, str(bad))

    contracts = {c["contract_id"]: c for c in base["csv"]["legal/contracts_register.csv"]}
    bad = [v["vendor_id"] for v in vendors.values()
           if v["contract_ref"] not in contracts or contracts[v["contract_ref"]]["vendor_id"] != v["vendor_id"]]
    check("integrity: vendor.contract_ref points to a contract for the same vendor", not bad, str(bad))

    # E028 (decoy leaver) must appear nowhere except the roster, docs and answer key
    hits = []
    for rel in CSV_FILES + JSON_FILES:
        if rel == "hr/roster.csv":
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            if "E028" in f.read():
                hits.append(rel)
    check("decoy: E028 appears only in roster", not hits, str(hits))

    # ---- 2. Dates ----
    date_cols = re.compile(r"(date|_from|_to|expiry|last_reviewed|last_working_day|frozen_until|valid_|start|end)", re.I)
    badd = []
    for rel, rows in base["csv"].items():
        for i, r in enumerate(rows, 2):
            for k, v in r.items():
                if v and date_cols.search(k) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                    try:
                        d(v)
                    except ValueError:
                        badd.append((rel, i, k, v))
    check("dates: all ISO date cells parse", not badd, str(badd))
    order = [(c["contract_id"]) for c in contracts.values() if d(c["end_date"]) < d(c["start_date"])]
    order += [t["employee_id"] for t in base["csv"]["hr/training_records.csv"]
              if t["completed_date"] and d(t["expiry_date"]) <= d(t["completed_date"])]
    check("dates: end after start, expiry after completion", not order, str(order))
    check("dates: approval window sane", d(pa["approved_on"]) < d(pa["valid_until"]))

    # ---- 3. Reconciliations ----
    active_by_dept = {}
    for r in roster.values():
        if r["status"] != "left":
            active_by_dept[r["department"]] = active_by_dept.get(r["department"], 0) + 1
    bad = [(h["department"], h["filled_heads"], active_by_dept.get(h["department"], 0))
           for h in base["csv"]["hr/headcount_plan.csv"] if int(h["filled_heads"]) != active_by_dept.get(h["department"], 0)]
    check("reconcile: headcount filled == active roster per department", not bad, str(bad))
    bad = [r["employee_id"] for r in roster.values()
           if (r["status"] == "serving_notice" and r["leaver_checklist"] != "initiated")
           or (r["status"] == "left" and r["leaver_checklist"] != "complete")
           or (r["status"] == "active" and r["leaver_checklist"] != "NA")]
    check("reconcile: leaver_checklist consistent with status", not bad, str(bad))
    need = [e for e, r in roster.items() if r["status"] != "left"]
    missing = [(e, c) for e in need for c in ("COC-100", "DPA-110")
               if not any(t["employee_id"] == e and t["course_code"] == c for t in base["csv"]["hr/training_records.csv"])]
    check("reconcile: every active employee has COC-100 and DPA-110 rows", not missing, str(missing))
    bad = [b["line_id"] for b in base["csv"]["finance/budget.csv"]
           if int(b["spent_ytd_gbp"]) > int(b["committed_gbp"])]
    check("reconcile: spent <= committed on every budget line", not bad, str(bad))
    bad = []
    for p in base["csv"]["finance/purchase_orders.csv"]:
        if not any(b["cost_center"] == p["cost_center"] and b["committed_gbp"] == p["amount_gbp"]
                   for b in base["csv"]["finance/budget.csv"]):
            bad.append(p["po_id"])
    check("reconcile: every PO matches a budget line (cost centre and committed amount)", not bad, str(bad))
    bad = [v["vendor_id"] for v in vendors.values()
           if sum(int(p["amount_gbp"]) for p in base["csv"]["finance/purchase_orders.csv"] if p["vendor_id"] == v["vendor_id"])
           != int(v["annual_value_gbp"])]
    check("reconcile: vendor annual value == sum of its POs", not bad, str(bad))
    ak_ids = {r["obligation_id"] for r in read_csv("answer_key/expected_obligations.csv")[1]}
    reg_ids = {o["obligation_id"] for o in base["csv"]["legal/obligations_register.csv"]}
    check("answer key: Legal obligations match the register", {i for i in ak_ids if i.startswith("OBL-L")} == reg_ids)

    # ---- 4. Department checks at the baseline ----
    res, overdue = dept_checks(base, AS_OF)
    expected = {r["check_id"]: r for r in read_csv("answer_key/expected_department_checks.csv")[1]}
    for cid, row in expected.items():
        got_ex = res[cid]
        want_ex = sorted(x.strip() for x in row["exceptions"].split(";") if x.strip())
        check(f"dept check {cid} exceptions", sorted(got_ex) == want_ex, f"got {sorted(got_ex)} want {want_ex}")
        check(f"dept check {cid} status", status_of(cid, got_ex, overdue) == row["expected_status"],
              f"got {status_of(cid, got_ex, overdue)} want {row['expected_status']}")
    check("dept checks: every computed check is in the answer key", set(res) == set(expected))

    # ---- 5. Seams at the baseline ----
    key = read_json("answer_key/expected_seams.json")
    seams = {s["seam_id"]: s for s in key["seams"]}
    s1 = seam_s1(base)
    check("S1 legal references", s1["legal"] == sorted(seams["S1"]["validation"]["legal_references"]), str(s1["legal"]))
    check("S1 finance references", s1["finance"] == sorted(seams["S1"]["validation"]["finance_references"]), str(s1["finance"]))
    check("S2 untrained at launch", seam_s2(base) == sorted(seams["S2"]["validation"]["untrained_at_launch"]), str(seam_s2(base)))
    check("S3 non-EEA processors", seam_s3(base) == sorted(seams["S3"]["validation"]["non_eea_processors"]), str(seam_s3(base)))
    naive = sorted(v["vendor_id"] for v in vendors.values() if v["country"] == "United States")
    check("S3 decoy: naive 'US vendor' rule differs from the correct result", naive != seam_s3(base), str(naive))
    naive_gone = sorted(e for e, r in roster.items() if r["status"] == "left")
    check("S1 decoy: naive 'left employee' rule would flag someone the correct rule does not",
          bool(set(naive_gone) - {x.split(":")[1] for x in s1["legal"] if x.startswith("ASM:")}))
    s4 = seam_s4(base)
    v4 = seams["S4"]["validation"]
    check("S4 numbers", (s4["need"], s4["have"], s4["shortfall"]) ==
          (v4["required_hours_per_week"], v4["available_hours_per_week"], v4["shortfall_hours_per_week"]), str(s4))
    check("S4 open (frozen past launch, budget business hours only)", s4["open"], str(s4))
    s5 = seam_s5(base)
    check("S5 material changes", s5["material"] == seams["S5"]["validation"]["material_changes"] and s5["open"], str(s5))
    check("baseline open seams == S1..S5", open_seams(base) == ["S1", "S2", "S3", "S4", "S5"], str(open_seams(base)))

    # ---- 6. Event stream ----
    ev_doc = read_json("events/event_stream.json")
    eff = {e["event_id"]: e for e in read_json("answer_key/expected_event_effects.json")["events"]}
    check("events: same ids in stream and answer key", [e["event_id"] for e in ev_doc["events"]] == list(eff))
    w = copy.deepcopy(base)
    last = None
    for ev in ev_doc["events"]:
        eid = ev["event_id"]
        check(f"{eid} date order", last is None or d(ev["date"]) >= last)
        last = d(ev["date"])
        try:
            for ch in ev["changes"]:
                apply_change(w, ch)
        except AssertionError as e:
            check(f"{eid} applies cleanly", False, str(e))
            continue
        check(f"{eid} applies cleanly", True)
        exp = eff[eid]
        ex = exp["expect"]
        check(f"{eid} open seams", open_seams(w) == exp["open_seams"], f"got {open_seams(w)} want {exp['open_seams']}")
        if "s2_untrained" in ex:
            check(f"{eid} S2 set", seam_s2(w) == sorted(ex["s2_untrained"]), str(seam_s2(w)))
        if "s3_non_eea_processors" in ex:
            check(f"{eid} S3 set", seam_s3(w) == sorted(ex["s3_non_eea_processors"]), str(seam_s3(w)))
        if "leg_c5_exceptions" in ex:
            r2, _ = dept_checks(w, d(ev["date"]))
            check(f"{eid} LEG-C5 exceptions", sorted(r2["LEG-C5"]) == sorted(ex["leg_c5_exceptions"]), str(r2["LEG-C5"]))
        if "s1_legal_references" in ex:
            s = seam_s1(w)
            check(f"{eid} S1 legal refs", s["legal"] == sorted(ex["s1_legal_references"]), str(s["legal"]))
            check(f"{eid} S1 finance refs", s["finance"] == sorted(ex["s1_finance_references"]), str(s["finance"]))
            gone_now = {r["employee_id"] for r in w["csv"]["hr/roster.csv"] if r["status"] == "left"}
            blocked = sorted(p["po_id"] for p in w["csv"]["finance/purchase_orders.csv"]
                             if p["status"] == "pending_approval" and p["approver"] in gone_now)
            check(f"{eid} S1 blocked pending POs", blocked == sorted(ex["s1_blocked_pending_pos"]), str(blocked))

    # ---- Summary ----
    total = len(PASSES) + len(FAILS)
    print(f"\nDataset self-check: {len(PASSES)}/{total} passed")
    for f in FAILS:
        print("  FAIL:", f)
    if not FAILS:
        print("  All department checks, seams and events agree with the answer key.")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

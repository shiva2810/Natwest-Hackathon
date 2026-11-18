"""Rule-based extractor for CSV and JSON (component 2.2).

Turns department tables into entities, and Legal's obligations register into obligation records.
Status is left "unknown": deciding met/unmet is the checkers' job (layer 3). Legal's
self-attested status is kept as an attribute because it is the owner's opinion, not evidence.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ..schema import (ApprovalLimit, BudgetLine, Contract, DataFlow, Entities, HeadcountPlan,
                      ObligationRecord, Person, Product, ProductApproval, ProductChange, PurchaseOrder,
                      Staffing, Training, Vendor)
from ..sources import Dataset

PRODUCT_ID = "prod-quickpay"
DD_MAP = {"completed": "complete", "complete": "complete", "in_progress": "pending", "pending": "pending"}


class ExtractionError(ValueError):
    pass


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def _f(v: str | None) -> float:
    return float(v) if v not in (None, "") else 0.0


def _yn(v: str | None) -> bool:
    return (v or "").strip().upper() == "Y"


def _opt(v: str | None) -> str | None:
    return v.strip() if v and v.strip() else None


def _table(ds: Dataset, key: str) -> list[dict[str, str]]:
    if key not in ds.tables:
        raise ExtractionError(f"missing required file data/{key}")
    return ds.tables[key]


def parse_parameters(raw: str) -> dict[str, Any]:
    """'course=PCT-101; validity_months=12' -> {'course': 'PCT-101', 'validity_months': 12}.
    Comma-separated values become lists: 'allowed_regions=UK,EEA' -> ['UK', 'EEA']."""
    out: dict[str, Any] = {}
    for part in (raw or "").split(";"):
        if "=" not in part:
            continue
        k, v = (s.strip() for s in part.split("=", 1))
        if "," in v:
            out[k] = [s.strip() for s in v.split(",") if s.strip()]
        elif v.isdigit():
            out[k] = int(v)
        else:
            out[k] = v
    return out


# ---------- entities ----------

def extract_entities(ds: Dataset) -> Entities:
    trainings: dict[str, list[Training]] = {}
    for r in _table(ds, "hr/training_records.csv"):
        trainings.setdefault(r["employee_id"], []).append(Training(
            course=r["course_code"], status=r["status"],
            completed_on=_d(r["completed_date"]), expires_on=_d(r["expiry_date"])))

    limits = [ApprovalLimit(
        id=f"AL-{r['approver_id']}", approver_id=r["approver_id"], role_title=r["role_title"],
        scope=r["scope"], limit=_f(r["limit_gbp"]), delegate_id=_opt(r["delegate_id"]),
        valid_from=_d(r["valid_from"]), valid_to=_d(r["valid_to"]))
        for r in _table(ds, "finance/approval_limits.csv")]
    top_limit: dict[str, float] = {}
    for al in limits:
        top_limit[al.approver_id] = max(top_limit.get(al.approver_id, 0.0), al.limit)

    people = [Person(
        id=r["employee_id"], name=r["full_name"], role=r["job_title"], department=r["department"],
        status=r["status"], active=r["status"] != "left",
        leaving_on=_d(r["last_working_day"]) if r["status"] in ("serving_notice", "left") else None,
        manager_id=_opt(r["manager_id"]), location=_opt(r["location"]),
        approval_limit=top_limit.get(r["employee_id"], 0.0),
        trainings=trainings.get(r["employee_id"], []))
        for r in _table(ds, "hr/roster.csv")]

    vendors = [Vendor(
        id=r["vendor_id"], name=r["vendor_name"], service=r["service_description"], country=r["country"],
        handles_customer_data=_yn(r["handles_customer_data"]), processing_region=_opt(r["data_processing_region"]),
        due_diligence=DD_MAP.get(r["dd_status"], "none"), dd_completed_on=_d(r["dd_completed_date"]),
        annual_value=_f(r["annual_value_gbp"]), contract_ref=_opt(r["contract_ref"]),
        business_owner_id=_opt(r["business_owner_id"]), status=r["status"])
        for r in _table(ds, "finance/vendors.csv")]

    contracts = [Contract(
        id=r["contract_id"], title=f"{r['counterparty']}: {r['contract_type']}", vendor_id=r["vendor_id"],
        start_date=_d(r["start_date"]), end_date=_d(r["end_date"]), auto_renew=_yn(r["auto_renew"]),
        dpa_required=_yn(r["dpa_required"]), dpa_signed=_yn(r["dpa_signed"]),
        legal_owner_id=_opt(r["legal_owner_id"]), notes=_opt(r["notes"]))
        for r in _table(ds, "legal/contracts_register.csv")]

    staffing = [Staffing(
        person_id=r["employee_id"], product=r["product"], role=r["role_on_product"],
        allocation_pct=_f(r["allocation_pct"]), can_sell=_yn(r["can_sell_or_onboard"]),
        selling_from=_d(r["selling_from"]))
        for r in _table(ds, "hr/product_staffing.csv")]

    pos = [PurchaseOrder(
        id=r["po_id"], vendor_id=r["vendor_id"], description=r["description"], amount=_f(r["amount_gbp"]),
        product=_opt(r["product"]), requested_by=_opt(r["requested_by"]), approver_id=_opt(r["approver"]),
        approved_on=_d(r["approval_date"]), status=r["status"])
        for r in _table(ds, "finance/purchase_orders.csv")]

    budget = [BudgetLine(
        id=r["line_id"], product=_opt(r["product"]), line_item=r["line_item"], category=r["category"],
        approved=_f(r["approved_budget_gbp"]), committed=_f(r["committed_gbp"]), spent_ytd=_f(r["spent_ytd_gbp"]),
        owner_id=_opt(r["owner_id"]), coverage_notes=_opt(r["coverage_notes"]))
        for r in _table(ds, "finance/budget.csv")]

    headcount = [HeadcountPlan(
        department=r["department"], approved_heads=int(r["approved_heads"]), filled_heads=int(r["filled_heads"]),
        open_reqs=int(r["open_reqs"] or 0), weekly_hours_per_head=_f(r["weekly_contract_hours_per_head"]),
        hiring_status=r["hiring_status"], frozen_until=_d(r["frozen_until"]), notes=_opt(r["notes"]))
        for r in _table(ds, "hr/headcount_plan.csv")]

    return Entities(people=people, vendors=vendors, contracts=contracts, products=[extract_product(ds)],
                    staffing=staffing, approval_limits=limits, purchase_orders=pos, budget_lines=budget,
                    headcount=headcount)


def extract_product(ds: Dataset) -> Product:
    pr = ds.docs.get("product/product_record.json")
    ap = ds.docs.get("legal/product_approval.json")
    if pr is None:
        raise ExtractionError("missing required file data/product/product_record.json")
    approval = None
    if ap is not None:
        if ap.get("product") != pr.get("product"):
            raise ExtractionError(f"approval is for '{ap.get('product')}', product record is '{pr.get('product')}'")
        approval = ProductApproval(
            id=ap["approval_id"], approved_version=str(ap["approved_version"]), approved_on=_d(ap.get("approved_on")),
            valid_until=_d(ap.get("valid_until")), scope=ap.get("scope"),
            accountable_senior_manager_id=ap.get("accountable_senior_manager"),
            approved_by=ap.get("approved_by", []), conditions=ap.get("conditions", []))
    return Product(
        id=PRODUCT_ID, name=pr["product"], launch_version=str(pr["release_candidate"]),
        launch_date=_d(pr["launch_date"]), live_version=str(pr.get("live_version") or "") or None,
        owner_id=pr.get("product_owner"), change_control_filed=pr.get("change_control_request_filed"),
        changes=[ProductChange(id=c["id"], description=c["description"], change_type=c["change_type"],
                               material=bool(c["material"]), vendor_id=c.get("vendor_id"))
                 for c in pr.get("changes", [])],
        data_flows=[DataFlow(vendor_id=f["processor_vendor_id"], data_category=f["data_category"],
                             purpose=f["purpose"]) for f in pr.get("data_flows", [])],
        premium_support=bool((pr.get("premium_support_tier") or {}).get("enabled")),
        first_sales_date=_d((pr.get("sales_enablement") or {}).get("first_sales_date")),
        approval=approval)


# ---------- Legal obligations register ----------

# Register obligations that concern the product (others are company-wide).
PRODUCT_SCOPED = {"approval", "training", "data_residency", "service_level", "regulatory_notification",
                  "change_control", "accountability"}


def extract_legal_register(ds: Dataset) -> list[ObligationRecord]:
    out = []
    for r in _table(ds, "legal/obligations_register.csv"):
        kind = r["obligation_type"]
        out.append(ObligationRecord(
            id=r["obligation_id"], department="Legal", kind=kind, description=r["statement"],
            owner_id=_opt(r["owner_id"]), product_id=PRODUCT_ID if kind in PRODUCT_SCOPED else None,
            status="unknown", applies_from=_d(r["applies_from"]),
            source_ref=f"{r['source_doc']}#{r['clause']}",
            attributes={
                **parse_parameters(r["parameters"]),
                "source_doc": r["source_doc"], "clause": r["clause"],
                "self_attested": r["self_attested_status"], "last_reviewed": r["last_reviewed"],
                "evidence_required": r["evidence_required"],
                "evidence_location": _opt(r["evidence_location"]),
                "evidence_status": r["evidence_status"],
            },
            extracted_by="rule"))
    return out

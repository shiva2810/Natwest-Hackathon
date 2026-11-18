"""Shared data contract (component 2.1).

The handoff file records.json is a `Bundle`: the scenario, the entities named in the
department files, and the obligation records the extractors and checkers emit.

v2: extended for the real dataset (data/). Every new field has a default, so the older
fixtures/records.json still loads.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Department = Literal["HR", "Finance", "Legal"]
Status = Literal["met", "unmet", "unknown"]


# ---------- entities (the nodes the graph is built from) ----------

class Training(BaseModel):
    course: str
    status: str = "valid"                   # valid / expired / not_started
    completed_on: date | None = None
    expires_on: date | None = None


class Staffing(BaseModel):
    """hr/product_staffing.csv: who works on a product and whether they sell."""
    person_id: str
    product: str
    role: str
    allocation_pct: float = 100
    can_sell: bool = False
    selling_from: date | None = None


class Person(BaseModel):
    id: str
    name: str
    role: str                               # job title
    department: str
    active: bool = True                     # False once status is "left"
    status: str = "active"                  # active / serving_notice / left
    leaving_on: date | None = None          # last working day, if any
    manager_id: str | None = None
    location: str | None = None
    approval_limit: float = 0.0             # GBP; highest limit in the approval table, 0 = cannot approve
    trainings: list[Training] = Field(default_factory=list)


class Vendor(BaseModel):
    id: str
    name: str
    due_diligence: Literal["complete", "pending", "none"] = "none"
    dd_expires_on: date | None = None
    dd_completed_on: date | None = None
    service: str | None = None
    country: str | None = None
    handles_customer_data: bool = False
    processing_region: str | None = None    # e.g. "US-East", "EU-Frankfurt", "UK-London"
    annual_value: float = 0.0
    contract_ref: str | None = None
    business_owner_id: str | None = None
    status: str = "active"


class Contract(BaseModel):
    id: str
    title: str
    vendor_id: str
    value: float = 0.0                      # GBP (not in the real contracts register)
    signed_by: str | None = None            # person id
    product_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    auto_renew: bool = False
    dpa_required: bool = False
    dpa_signed: bool = False
    legal_owner_id: str | None = None
    notes: str | None = None


class ApprovalLimit(BaseModel):
    """finance/approval_limits.csv: delegation of authority."""
    id: str                                 # "AL-<approver_id>"
    approver_id: str
    role_title: str
    scope: str
    limit: float
    delegate_id: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class PurchaseOrder(BaseModel):
    id: str
    vendor_id: str
    description: str
    amount: float
    product: str | None = None
    requested_by: str | None = None
    approver_id: str | None = None
    approved_on: date | None = None
    status: str = "approved"                # approved / pending_approval


class BudgetLine(BaseModel):
    id: str
    product: str | None
    line_item: str
    category: str
    approved: float
    committed: float
    spent_ytd: float = 0.0
    owner_id: str | None = None
    coverage_notes: str | None = None


class HeadcountPlan(BaseModel):
    department: str
    approved_heads: int
    filled_heads: int
    open_reqs: int = 0
    weekly_hours_per_head: float = 40
    hiring_status: str = "open"             # open / frozen
    frozen_until: date | None = None
    notes: str | None = None


class ProductChange(BaseModel):
    id: str
    description: str
    change_type: str
    material: bool
    vendor_id: str | None = None


class DataFlow(BaseModel):
    vendor_id: str
    data_category: str
    purpose: str


class ProductApproval(BaseModel):
    id: str
    approved_version: str
    approved_on: date | None = None
    valid_until: date | None = None
    scope: str | None = None
    accountable_senior_manager_id: str | None = None
    approved_by: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class Product(BaseModel):
    id: str
    name: str
    launch_version: str
    launch_date: date
    live_version: str | None = None
    owner_id: str | None = None
    change_control_filed: bool | None = None
    changes: list[ProductChange] = Field(default_factory=list)
    data_flows: list[DataFlow] = Field(default_factory=list)
    premium_support: bool = False
    first_sales_date: date | None = None
    approval: ProductApproval | None = None


class Entities(BaseModel):
    people: list[Person] = Field(default_factory=list)
    vendors: list[Vendor] = Field(default_factory=list)
    contracts: list[Contract] = Field(default_factory=list)
    products: list[Product] = Field(default_factory=list)
    staffing: list[Staffing] = Field(default_factory=list)
    approval_limits: list[ApprovalLimit] = Field(default_factory=list)
    purchase_orders: list[PurchaseOrder] = Field(default_factory=list)
    budget_lines: list[BudgetLine] = Field(default_factory=list)
    headcount: list[HeadcountPlan] = Field(default_factory=list)


# ---------- obligation records ----------

class Evidence(BaseModel):
    source: str                             # file name, e.g. "legal/legal_policies_excerpt.md"
    quote: str | None = None                # verbatim text; required for text-extracted records
    expires_on: date | None = None


class ObligationRecord(BaseModel):
    id: str
    department: Department
    kind: str                               # see KINDS below
    description: str
    owner_id: str | None = None             # person accountable
    product_id: str | None = None
    vendor_id: str | None = None
    contract_id: str | None = None
    status: Status = "unknown"              # set by the department checkers, not the extractors
    evidence: list[Evidence] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    extracted_by: Literal["rule", "llm", "fixture"] = "rule"
    source_ref: str | None = None           # "<file>#<clause>", e.g. "hr/hr_policy_excerpt.md#4.1"
    applies_from: date | None = None


# Known `kind` values and what goes in `attributes`.
KINDS = {
    # HR policy
    "headcount_cap": "department must not exceed approved headcount",
    "mandatory_training": "all employees hold a course; {course, validity_months}",
    "leaver_handover": "line managers reassign a leaver's duties and approvals in other systems",
    "hiring_freeze": "no hiring in a department; {department, until}",
    # Finance policy
    "budget_cap": "committed spend must not exceed approved budget per line",
    "po_approval_limit": "PO approver's limit must cover the PO amount",
    "asm_spend_approval": "product spend above a threshold needs the product ASM's approval; {threshold_gbp}",
    "supplier_dd_before_po": "supplier due diligence complete before first PO approval",
    # Legal register (obligation_type column)
    "approval": "product holds a current Legal approval",
    "training": "sellers hold a course on the date of sale; {course, validity_months}",
    "data_residency": "customer data processed only in allowed regions; {allowed_regions}",
    "policy_review": "a procedure is reviewed every N months",
    "service_level": "a support commitment is staffed and funded",
    "regulatory_notification": "regulator notified before launch; {due_date}",
    "change_control": "material changes re-approved before release",
    "contract_validity": "active contracts are not past their end date",
    "accountability": "a named, available accountable senior manager",
    "dpa": "a DPA is signed before a supplier processes customer data",
    # fixtures (older rules)
    "role_owner": "someone must own this obligation",
    "training_required": "owner must hold a course; {course}",
    "product_approval": "approval for a product; {approved_version}",
    "vendor_due_diligence": "vendor must pass DD",
    "budget_line": "spend must be budgeted; {amount}",
    "contract_term": "free-text term from a contract; {term}",
}


class Scenario(BaseModel):
    company: str
    as_of: date                             # "today" for the demo; moves forward as events replay
    product_id: str


class Bundle(BaseModel):
    scenario: Scenario
    entities: Entities
    records: list[ObligationRecord]

    @model_validator(mode="after")
    def _consistent(self) -> "Bundle":
        e = self.entities
        if self.scenario.product_id not in {p.id for p in e.products}:
            raise ValueError(f"scenario.product_id '{self.scenario.product_id}' is not in entities.products")
        groups = (e.people, e.vendors, e.contracts, e.products, e.approval_limits, e.purchase_orders,
                  e.budget_lines, self.records)
        ids = [x.id for group in groups for x in group]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:  # every id becomes a graph node, so ids must be unique across ALL kinds
            raise ValueError(f"duplicate ids across entities/records: {dupes}")
        return self

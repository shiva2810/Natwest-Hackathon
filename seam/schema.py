"""Shared data contract (component 2.1).

DRAFT until the 0:25 freeze. Person 1 leads; changes after the freeze need all three to agree.

The handoff file records.json is a `Bundle`: the scenario, the entities named in the
department files, and the obligation records the extractors and checkers emit.
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
    completed_on: date | None = None
    expires_on: date | None = None


class Person(BaseModel):
    id: str
    name: str
    role: str
    department: str
    active: bool = True
    leaving_on: date | None = None          # resignation notice, if any
    approval_limit: float = 0.0             # GBP; 0 means cannot approve spend
    trainings: list[Training] = Field(default_factory=list)


class Vendor(BaseModel):
    id: str
    name: str
    due_diligence: Literal["complete", "pending", "none"] = "none"
    dd_expires_on: date | None = None


class Contract(BaseModel):
    id: str
    title: str
    vendor_id: str
    value: float                            # GBP
    signed_by: str | None = None            # person id
    product_id: str | None = None


class Product(BaseModel):
    id: str
    name: str
    launch_version: str
    launch_date: date


class Entities(BaseModel):
    people: list[Person] = Field(default_factory=list)
    vendors: list[Vendor] = Field(default_factory=list)
    contracts: list[Contract] = Field(default_factory=list)
    products: list[Product] = Field(default_factory=list)


# ---------- obligation records ----------

class Evidence(BaseModel):
    source: str                             # file name, e.g. "legal/contract_cloudnest.txt"
    quote: str | None = None                # required for LLM-extracted records
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
    status: Status = "unknown"
    evidence: list[Evidence] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    extracted_by: Literal["rule", "llm", "fixture"] = "rule"


# Known `kind` values and the attributes each one uses.
KINDS = {
    "role_owner": "someone must own this obligation; attributes: {}",
    "training_required": "owner must hold a course; attributes: {course}",
    "product_approval": "approval for a product; attributes: {approved_version}",
    "vendor_due_diligence": "vendor must pass DD; attributes: {}",
    "budget_line": "spend must be budgeted; attributes: {amount}",
    "contract_term": "free-text term from a contract; attributes: {term}",
}


class Scenario(BaseModel):
    company: str
    as_of: date                             # "today" for the demo
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
        ids = [x.id for group in (e.people, e.vendors, e.contracts, e.products, self.records) for x in group]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:  # every id becomes a graph node, so ids must be unique across ALL kinds
            raise ValueError(f"duplicate ids across entities/records: {dupes}")
        return self

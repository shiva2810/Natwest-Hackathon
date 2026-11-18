# Compliance Seam Detector - synthetic dataset

Synthetic data for the NatWest hackathon project. **Everything here is fictional**: Aldermere Pay Ltd, its people and its suppliers do not exist.

The point of the dataset: **each department, looked at alone, looks mostly fine. Five problems appear only when the departments are put together.** A good system finds those five, ignores the decoys, and says "unknown" where evidence is missing.

## How to use it
1. Read `SCENARIO.md` (the story, no spoilers).
2. Build the system against `hr/`, `finance/`, `legal/`, `product/` and `events/`.
3. Compare its output with `answer_key/` only when it is done.
4. Run `python tools/validate_dataset.py` any time to confirm the dataset and its answer key still agree (Python 3 standard library only).
5. To get this dataset reviewed in ChatGPT, follow `CHATGPT_REVIEW_PROMPT.md`. `_COMBINED_FOR_REVIEW.md` has every file in one document.

## Folder map
```
README.md                      this file
SCENARIO.md                    the story (safe to read)
CHATGPT_REVIEW_PROMPT.md       prompt for an independent review
_COMBINED_FOR_REVIEW.md        everything in one file, for pasting or uploading
hr/                            roster, training, staffing, headcount, HR policy
finance/                       budget, vendors, approval limits, purchase orders, finance policy
legal/                         product approval, obligations register, contracts, customer terms, legal policies
product/product_record.json    shared context from Product
events/event_stream.json       6 events for the living passport
answer_key/                    what is planted (do not feed to the system under test)
tools/validate_dataset.py      self-check for this dataset (not the product)
```

## Department-isolation rule
A department checker may read **only its own folder** and its own policy text. Anything that needs two folders is, by design, a seam. `product/` is shared context, not a fourth checker.

Legal's register holds **self-attested** status. That is the realistic blind spot: Legal's own view says "compliant" because Legal cannot see HR, Finance or Product data.

## What is planted
| Item | Count | Where |
|---|---|---|
| Cross-department seams | 5 (S1 to S5) | `answer_key/expected_seams.json` |
| In-department findings | 4 (HR 1, Finance 1, Legal 1, plus one Legal "unknown") | `answer_key/expected_department_checks.csv` |
| Department checks | 14 (HR 5, Finance 4, Legal 5) | same file |
| Decoys and noise clauses | 7 decoys, 5 noise clauses | `answer_key/decoys_and_noise.csv` |
| Events | 6 (S1 shrinks then resolves, S2 shrinks, S3 grows, one unknown resolves) | `events/event_stream.json`, `answer_key/expected_event_effects.json` |
| Obligations to extract from text | 19 (HR 5, Finance 4, Legal 10) | `answer_key/expected_obligations.csv` |

Seams in one line each:
- **S1** The accountable senior manager (and sole QuickPay approver) leaves before launch. HR, Legal and Finance each hold one piece.
- **S2** Three sellers will not hold valid Payments Conduct Training on the first sales date. HR holds the records, Legal holds the rule.
- **S3** A US supplier receives customer data although the customer terms promise UK/EEA-only processing. Finance holds the region, Legal holds the promise.
- **S4** The terms promise 24x7 support with two agents; staffing and budget cover 240 of 336 weekly hours and hiring is frozen.
- **S5** Legal's approval covers v1.4; v2.0 has three material changes and no change control request.

## Files
| File | Rows | What it is |
|---|---|---|
| `hr/roster.csv` | 28 | One row per person. status is active / serving_notice / left. leaver_checklist covers HR-owned systems only. Columns: employee_id, full_name, department, job_title, manager_id, status, last_working_day, leaver_checklist, location |
| `hr/training_records.csv` | 64 | One row per person per course. COC-100 and DPA-110 are HR-mandated; PCT-101 (Payments Conduct Training) is required by Legal for sellers but is not on HR's mandatory list. Columns: employee_id, course_code, status, completed_date, expiry_date |
| `hr/product_staffing.csv` | 18 | Who works on QuickPay. can_sell_or_onboard = Y means the person sells from selling_from. Columns: employee_id, product, role_on_product, allocation_pct, can_sell_or_onboard, selling_from |
| `hr/headcount_plan.csv` | 9 | Approved and filled heads, hiring status, weekly contract hours per head. Columns: department, approved_heads, filled_heads, open_reqs, weekly_contract_hours_per_head, hiring_status, frozen_until, notes |
| `finance/budget.csv` | 10 | FY2026 budget lines. committed_gbp includes purchase orders still pending approval. coverage_notes states what the line actually funds. Columns: line_id, fiscal_year, cost_center, product, line_item, category, approved_budget_gbp, committed_gbp, spent_ytd_gbp, owner_id, coverage_notes |
| `finance/vendors.csv` | 7 | Supplier master data with due-diligence status and where customer data is processed. V007 is deliberately absent (introduced by an event). Columns: vendor_id, vendor_name, service_description, country, handles_customer_data, data_processing_region, dd_status, dd_completed_date, dd_scope, annual_value_gbp, contract_ref, business_owner_id, status |
| `finance/approval_limits.csv` | 5 | Delegation of authority. delegate_id blank means no delegate. Columns: approver_id, role_title, scope, limit_gbp, delegate_id, valid_from, valid_to |
| `finance/purchase_orders.csv` | 7 | Purchase orders with approver. status is approved or pending_approval. Columns: po_id, vendor_id, description, amount_gbp, cost_center, product, requested_by, approver, approval_date, status |
| `legal/obligations_register.csv` | 10 | Legal's register. self_attested_status is the owner's own opinion, not primary evidence. evidence_status is provided / held_by_other_dept / not_found. Columns: obligation_id, source_doc, clause, statement, obligation_type, owner_id, applies_from, self_attested_status, last_reviewed, evidence_required, evidence_location, evidence_status, parameters |
| `legal/contracts_register.csv` | 8 | Supplier contracts. It has no data-processing-location column (Legal cannot see where data is processed). Columns: contract_id, counterparty, vendor_id, contract_type, start_date, end_date, auto_renew, dpa_required, dpa_signed, legal_owner_id, notes |
| `legal/product_approval.json` | - | The Legal approval for QuickPay (covers v1.4 only). |
| `product/product_record.json` | - | Shared context from Product: what v2.0 contains, which suppliers receive customer data, whether change control was filed. |
| `events/event_stream.json` | - | Six dated events with machine-readable changes (insert / update / set / append) for replaying the living passport. |

Policy and contract text (for the extraction step): `hr/hr_policy_excerpt.md`, `finance/finance_policy_excerpt.md`, `legal/customer_terms_v2.0_excerpt.md`, `legal/legal_policies_excerpt.md`.

## Dates
Review ("as of") date 2026-11-18. Launch 2026-12-01. Currency GBP.

## Known simplifications
- Documents are short excerpts, not full policies. Real extraction would face longer text.
- The roster is a modelled slice of the company (28 rows), not every employee.
- "Business days" in the regulator-notification rule are not modelled beyond the stated due date.
- `committed_gbp` includes a purchase order that is still pending approval (PO-2026-0450).
- Support agents are counted at 40 contract hours a week; holiday and sickness cover are ignored.
- The validator recomputes seams with simple rules. It proves the dataset is internally consistent, not that the rules are the only valid ones.

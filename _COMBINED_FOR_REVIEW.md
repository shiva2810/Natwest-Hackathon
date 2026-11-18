# Compliance Seam Detector - all dataset files in one document

Each file is shown under its path in a fenced block (fences use `~~~~`). Everything is synthetic. Start with README.md and SCENARIO.md.

Contents: `README.md`, `SCENARIO.md`, `CHATGPT_REVIEW_PROMPT.md`, `hr/roster.csv`, `hr/training_records.csv`, `hr/product_staffing.csv`, `hr/headcount_plan.csv`, `hr/hr_policy_excerpt.md`, `finance/budget.csv`, `finance/vendors.csv`, `finance/approval_limits.csv`, `finance/purchase_orders.csv`, `finance/finance_policy_excerpt.md`, `legal/product_approval.json`, `legal/obligations_register.csv`, `legal/contracts_register.csv`, `legal/customer_terms_v2.0_excerpt.md`, `legal/legal_policies_excerpt.md`, `product/product_record.json`, `events/event_stream.json`, `answer_key/expected_obligations.csv`, `answer_key/expected_department_checks.csv`, `answer_key/expected_seams.json`, `answer_key/expected_event_effects.json`, `answer_key/decoys_and_noise.csv`, `tools/validate_dataset.py`


## FILE: README.md

~~~~markdown
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
~~~~


## FILE: SCENARIO.md

~~~~markdown
# Scenario: Aldermere Pay Ltd launches QuickPay v2.0

All people, companies and figures are fictional and synthetic.

## The company and the product
Aldermere Pay Ltd is a UK payments company. Its product QuickPay is an instant payments service for small businesses. Version 1.4 is live. Version 2.0 is due to launch on **2026-12-01**.

Version 2.0 adds:
- Cross-border payments to EU beneficiaries
- Transaction analytics and fraud scoring from a third-party supplier, StreamLedger Inc
- A Premium support tier with 24x7 support
- A refreshed payment history screen

## Dates that matter
| Date | What |
|---|---|
| 2026-11-18 | Review date ("as of" date) |
| 2026-11-24 | Regulator notification due (5 business days before launch) |
| 2026-11-27 | Last working day of the QuickPay accountable senior manager |
| 2026-12-01 | Launch of v2.0 |
| 2027-03-31 | End of the Support hiring freeze |

## The review
The COO has asked each department to confirm that QuickPay v2.0 is ready. Each department reviews its own records against its own policies.

- **HR** owns the roster, training records, staffing assignments, headcount plan and HR policy.
- **Finance** owns the budget, supplier list, approval table, purchase orders and finance policy.
- **Legal** owns the product approval, obligations register, contracts register, customer terms and legal policies.
- **Product** supplies the product record (a shared context file) describing what v2.0 contains and which suppliers touch customer data.

## Key people
| ID | Name | Role |
|---|---|---|
| E001 | Helena Brandt | Chief Operating Officer |
| E002 | Arjun Rao | Head of Finance |
| E003 | Sofia Marchetti | General Counsel |
| E004 | Meera Iyer | Head of Payments Product, QuickPay accountable senior manager |
| E005 | Tom Alder | Head of HR |
| E006 | Neha Kapoor | Head of SME Sales |
| E007 | Liam O'Connor | Head of Customer Support |
| E008 | Yusuf Demir | Procurement Manager |
| E009 | Grace Kim | Legal Counsel |
| E010 | Priya Sharma | Engineering Lead |

## The brief for the system
Build a compliance checker that reads each department's records, checks them against the written policies, and then looks across departments for problems that no single department can see.

The answer key is in `answer_key/`. Do not read it until your system has produced its own output.
~~~~


## FILE: CHATGPT_REVIEW_PROMPT.md

~~~~markdown
# Prompt to paste into ChatGPT (with the files from this folder)

Attach `_COMBINED_FOR_REVIEW.md` (all files in one document), or attach the files individually. Then paste:

---

You are a senior compliance analyst and data-quality reviewer. I have built a **synthetic dataset** for a hackathon project: a compliance tool that checks a product launch against HR, Finance and Legal data, then detects **"seams"** - problems that exist only in the gaps between departments.

The dataset describes a fictional company (Aldermere Pay Ltd) launching QuickPay v2.0 on 2026-12-01, with review date 2026-11-18. The folder `answer_key/` states what is intentionally planted (5 seams, 4 in-department findings, decoys, 6 events).

Please review it and answer in this order:

1. **Internal consistency.** List any broken IDs, mismatched dates, headcount or budget numbers that do not reconcile, or file contradictions. Cite file and row.
2. **Are the five seams real and truly cross-department?** For each seam S1 to S5, say whether it genuinely needs data from two or more departments, and whether any single department's files alone would reveal it. Name any seam that is too easy to spot or not convincing.
3. **Unplanned issues.** Find any problems in the data that are NOT in the answer key (accidental extra seams or violations). These would unfairly count as false positives.
4. **Decoys and noise.** Are the decoys fair tests? Suggest two more decoys.
5. **Realism.** Would a compliance or HR/finance professional find this plausible? List anything that would look artificial.
6. **Event stream.** Check that each event's changes would produce the effects in `answer_key/expected_event_effects.json`.
7. **Top five improvements**, ranked by value, with a concrete edit for each.

Be specific and skeptical. Do not praise. If something is fine, say so briefly and move on.

---
~~~~


## FILE: hr/roster.csv

~~~~csv
employee_id,full_name,department,job_title,manager_id,status,last_working_day,leaver_checklist,location
E001,Helena Brandt,Operations,Chief Operating Officer,,active,,NA,London
E002,Arjun Rao,Finance,Head of Finance,E001,active,,NA,London
E003,Sofia Marchetti,Legal,General Counsel,E001,active,,NA,London
E004,Meera Iyer,Product,Head of Payments Product,E001,serving_notice,2026-11-27,initiated,London
E005,Tom Alder,HR,Head of HR,E001,active,,NA,London
E006,Neha Kapoor,Sales,Head of SME Sales,E001,active,,NA,Manchester
E007,Liam O'Connor,Support,Head of Customer Support,E001,active,,NA,Edinburgh
E008,Yusuf Demir,Finance,Procurement Manager,E002,active,,NA,London
E009,Grace Kim,Legal,Legal Counsel,E003,active,,NA,London
E010,Priya Sharma,Engineering,Engineering Lead,E004,active,,NA,London
E011,Carlos Mendes,Sales,Sales Executive,E006,active,,NA,Manchester
E012,Aisha Khan,Sales,Sales Executive,E006,active,,NA,Manchester
E013,Ben Foster,Sales,Sales Executive,E006,active,,NA,Leeds
E014,Chloe Dubois,Sales,Sales Executive,E006,active,,NA,London
E015,Dmitri Volkov,Sales,Sales Executive,E006,active,,NA,London
E016,Eva Lindqvist,Sales,Sales Executive,E006,active,,NA,Manchester
E017,Farid Hassan,Sales,Sales Executive,E006,active,,NA,Birmingham
E018,Hannah Weiss,Sales,Sales Executive,E006,active,,NA,London
E019,Isabel Torres,Support,Support Agent,E007,active,,NA,Edinburgh
E020,Jamal Brooks,Support,Support Agent,E007,active,,NA,Edinburgh
E021,Kavya Menon,Support,Support Agent,E007,active,,NA,Edinburgh
E022,Lucas Meyer,Support,Support Agent,E007,active,,NA,Edinburgh
E023,Mina Park,Support,Support Agent,E007,active,,NA,Glasgow
E024,Noah Fischer,Support,Support Agent,E007,active,,NA,Glasgow
E025,Olivia Grant,HR,HR Business Partner,E005,active,,NA,London
E026,Pavel Novak,Finance,Finance Analyst,E002,active,,NA,London
E027,Quentin Hale,Marketing,Marketing Manager,E001,active,,NA,London
E028,Rita Alvarez,Sales,Sales Executive,E006,left,2026-09-15,complete,Manchester
~~~~


## FILE: hr/training_records.csv

~~~~csv
employee_id,course_code,status,completed_date,expiry_date
E001,COC-100,valid,2026-01-12,2027-01-12
E001,DPA-110,valid,2026-02-09,2027-02-09
E002,COC-100,valid,2026-01-21,2027-01-21
E002,DPA-110,valid,2026-02-18,2027-02-18
E003,COC-100,valid,2026-01-30,2027-01-30
E003,DPA-110,valid,2026-02-27,2027-02-27
E004,COC-100,valid,2026-02-08,2027-02-08
E004,DPA-110,valid,2026-03-08,2027-03-08
E005,COC-100,valid,2026-02-17,2027-02-17
E005,DPA-110,valid,2026-03-17,2027-03-17
E006,COC-100,valid,2026-02-26,2027-02-26
E006,DPA-110,valid,2026-03-26,2027-03-26
E007,COC-100,valid,2026-03-07,2027-03-07
E007,DPA-110,valid,2026-04-04,2027-04-04
E008,COC-100,valid,2026-03-16,2027-03-16
E008,DPA-110,valid,2026-04-13,2027-04-13
E009,COC-100,valid,2026-03-25,2027-03-25
E009,DPA-110,valid,2026-04-22,2027-04-22
E010,COC-100,valid,2026-04-03,2027-04-03
E010,DPA-110,valid,2026-05-01,2027-05-01
E011,COC-100,valid,2026-04-12,2027-04-12
E011,DPA-110,valid,2026-05-10,2027-05-10
E012,COC-100,valid,2026-04-21,2027-04-21
E012,DPA-110,valid,2026-05-19,2027-05-19
E013,COC-100,valid,2026-04-30,2027-04-30
E013,DPA-110,valid,2026-05-28,2027-05-28
E014,COC-100,valid,2026-05-09,2027-05-09
E014,DPA-110,valid,2026-06-06,2027-06-06
E015,COC-100,valid,2026-05-18,2027-05-18
E015,DPA-110,valid,2026-06-15,2027-06-15
E016,COC-100,valid,2026-05-27,2027-05-27
E016,DPA-110,valid,2026-06-24,2027-06-24
E017,COC-100,valid,2026-06-05,2027-06-05
E017,DPA-110,valid,2026-07-03,2027-07-03
E018,COC-100,valid,2026-06-14,2027-06-14
E018,DPA-110,valid,2026-07-12,2027-07-12
E019,COC-100,valid,2026-06-23,2027-06-23
E019,DPA-110,valid,2026-07-21,2027-07-21
E020,COC-100,valid,2026-07-02,2027-07-02
E020,DPA-110,valid,2026-07-30,2027-07-30
E021,COC-100,valid,2026-07-11,2027-07-11
E021,DPA-110,valid,2026-08-08,2027-08-08
E022,COC-100,valid,2026-07-20,2027-07-20
E022,DPA-110,expired,2025-10-20,2026-10-20
E023,COC-100,valid,2026-07-29,2027-07-29
E023,DPA-110,valid,2026-08-26,2027-08-26
E024,COC-100,valid,2026-08-07,2027-08-07
E024,DPA-110,valid,2026-09-04,2027-09-04
E025,COC-100,valid,2026-08-16,2027-08-16
E025,DPA-110,valid,2026-09-13,2027-09-13
E026,COC-100,valid,2026-08-25,2027-08-25
E026,DPA-110,valid,2026-09-22,2027-09-22
E027,COC-100,valid,2026-09-03,2027-09-03
E027,DPA-110,valid,2026-10-01,2027-10-01
E006,PCT-101,valid,2026-04-14,2027-04-14
E011,PCT-101,valid,2026-03-10,2027-03-10
E012,PCT-101,valid,2026-05-22,2027-05-22
E013,PCT-101,valid,2025-11-25,2026-11-25
E014,PCT-101,not_started,,
E015,PCT-101,not_started,,
E016,PCT-101,valid,2026-07-01,2027-07-01
E017,PCT-101,valid,2026-02-18,2027-02-18
E018,PCT-101,valid,2026-09-09,2027-09-09
E019,PCT-101,valid,2026-06-20,2027-06-20
~~~~


## FILE: hr/product_staffing.csv

~~~~csv
employee_id,product,role_on_product,allocation_pct,can_sell_or_onboard,selling_from
E004,QuickPay,Accountable Senior Manager,100,N,
E010,QuickPay,Engineering Lead,80,N,
E006,QuickPay,Sales Lead,20,N,
E007,QuickPay,Support Lead,20,N,
E011,QuickPay,Sales Executive,100,Y,2026-12-01
E012,QuickPay,Sales Executive,100,Y,2026-12-01
E013,QuickPay,Sales Executive,100,Y,2026-12-01
E014,QuickPay,Sales Executive,100,Y,2026-12-01
E015,QuickPay,Sales Executive,100,Y,2026-12-01
E016,QuickPay,Sales Executive,100,Y,2026-12-01
E017,QuickPay,Sales Executive,100,Y,2026-12-01
E018,QuickPay,Sales Executive,100,Y,2026-12-01
E019,QuickPay,Support Agent,100,N,
E020,QuickPay,Support Agent,100,N,
E021,QuickPay,Support Agent,100,N,
E022,QuickPay,Support Agent,100,N,
E023,QuickPay,Support Agent,100,N,
E024,QuickPay,Support Agent,100,N,
~~~~


## FILE: hr/headcount_plan.csv

~~~~csv
department,approved_heads,filled_heads,open_reqs,weekly_contract_hours_per_head,hiring_status,frozen_until,notes
Operations,1,1,0,40,open,,
Finance,3,3,0,40,open,,
Legal,2,2,0,40,open,,
Product,2,1,1,40,open,,One open requisition for a product analyst
HR,2,2,0,40,open,,
Sales,10,9,1,40,open,,Head of sales plus 8 sales executives on QuickPay
Support,7,7,0,40,frozen,2027-03-31,Head of support plus 6 queue agents. Company-wide cost freeze; exceptions need COO and Head of Finance approval
Engineering,2,1,1,40,open,,Modelled slice of the engineering team
Marketing,1,1,0,40,open,,
~~~~


## FILE: hr/hr_policy_excerpt.md

~~~~markdown
# HR Policy (excerpt) - Aldermere Pay Ltd - version 2026.2

Synthetic document. Clause numbers are used by the answer key.

## 3. Headcount
**3.1** A department must not exceed its approved headcount.

## 4. Mandatory training
**4.1** All employees must complete Code of Conduct training (course COC-100) at least every 12 months.

**4.2** All employees must complete Data Protection Essentials training (course DPA-110) at least every 12 months.

## 5. Working arrangements
**5.1** Employees may work remotely for up to three days a week with their line manager's agreement.

## 6. Leavers
**6.1** An employee serving notice remains employed, and keeps their duties, until their last working day.

**6.2** When an employee resigns, HR starts the leaver checklist, which covers system access, equipment return, payroll and benefits. The checklist covers HR-owned systems only. Line managers are responsible for reassigning duties and approvals that the leaver holds in other departments' systems.

## 7. Hiring
**7.1** The Support department is under a hiring freeze until 2027-03-31. Exceptions require the written approval of the COO and the Head of Finance.
~~~~


## FILE: finance/budget.csv

~~~~csv
line_id,fiscal_year,cost_center,product,line_item,category,approved_budget_gbp,committed_gbp,spent_ytd_gbp,owner_id,coverage_notes
B-001,2026,CC-4100,QuickPay,Support staff (6 FTE),people,420000,420000,310000,E007,Business hours Mon-Fri 08:00-18:00; no out-of-hours line
B-002,2026,CC-4100,QuickPay,Support tooling,tools,60000,52000,41000,E007,
B-003,2026,CC-4200,QuickPay,Cloud hosting (EuroCloud),vendor,240000,240000,160000,E010,
B-004,2026,CC-4200,QuickPay,Payment analytics (StreamLedger),vendor,180000,180000,45000,E010,
B-005,2026,CC-4200,QuickPay,Open banking connectivity (Banc Link),vendor,150000,150000,95000,E010,
B-006,2026,CC-4300,QuickPay,Launch campaign agency (BrightMark),marketing,90000,62000,0,E027,
B-007,2026,CC-4400,QuickPay,Sales team (8 FTE),people,640000,640000,480000,E006,
B-008,2026,CC-4500,Corporate,External counsel (LexAdvisory),vendor,60000,38000,20000,E003,
B-009,2026,CC-4600,Corporate,Office productivity (Harbor Analytics),vendor,30000,24000,24000,E008,
B-010,2026,CC-4700,QuickPay,Launch monitoring tooling (PulseWatch),vendor,50000,45000,0,E010,
~~~~


## FILE: finance/vendors.csv

~~~~csv
vendor_id,vendor_name,service_description,country,handles_customer_data,data_processing_region,dd_status,dd_completed_date,dd_scope,annual_value_gbp,contract_ref,business_owner_id,status
V001,EuroCloud Hosting GmbH,Cloud hosting for the QuickPay platform,Germany,Y,EU-Frankfurt,completed,2025-02-20,financial; sanctions; adverse media,240000,C-2025-011,E010,active
V002,StreamLedger Inc,Payment analytics and fraud scoring,United States,Y,US-East,completed,2026-09-22,financial; sanctions; adverse media,180000,C-2026-031,E010,active
V003,Harbor Analytics Inc,Office productivity suite (internal use only),United States,N,US-East,completed,2025-06-12,financial; sanctions; adverse media,24000,C-2025-020,E008,active
V004,Banc Link Ltd,Open banking connectivity,United Kingdom,Y,UK-London,completed,2025-05-10,financial; sanctions; adverse media,150000,C-2025-014,E010,active
V005,LexAdvisory LLP,External legal counsel,United Kingdom,N,UK-London,completed,2026-01-15,financial; sanctions; adverse media,38000,C-2026-007,E003,active
V006,BrightMark Agency Ltd,Launch marketing campaign,United Kingdom,N,UK-London,completed,2026-09-30,financial; sanctions; adverse media,62000,C-2026-012,E027,active
V008,PulseWatch Ltd,Monitoring and on-call tooling,United Kingdom,N,UK-London,completed,2026-11-03,financial; sanctions; adverse media,45000,C-2026-040,E010,active
~~~~


## FILE: finance/approval_limits.csv

~~~~csv
approver_id,role_title,scope,limit_gbp,delegate_id,valid_from,valid_to
E001,Chief Operating Officer,All spend,1000000,,2026-01-01,2026-12-31
E002,Head of Finance,All spend,500000,E001,2026-01-01,2026-12-31
E004,QuickPay Accountable Senior Manager,QuickPay product spend,250000,,2026-01-01,2026-12-31
E008,Procurement Manager,All procurement,50000,E002,2026-01-01,2026-12-31
E027,Marketing Manager,Marketing spend,25000,E001,2026-01-01,2026-12-31
~~~~


## FILE: finance/purchase_orders.csv

~~~~csv
po_id,vendor_id,description,amount_gbp,cost_center,product,requested_by,approver,approval_date,status
PO-2026-0398,V001,Annual cloud hosting,240000,CC-4200,QuickPay,E010,E004,2026-09-14,approved
PO-2026-0405,V002,Payment analytics and fraud scoring,180000,CC-4200,QuickPay,E010,E004,2026-10-05,approved
PO-2026-0412,V006,QuickPay launch campaign,62000,CC-4300,QuickPay,E027,E008,2026-10-12,approved
PO-2026-0420,V004,Open banking connectivity,150000,CC-4200,QuickPay,E010,E004,2026-09-28,approved
PO-2026-0431,V003,Office productivity licences,24000,CC-4600,Corporate,E026,E008,2026-07-02,approved
PO-2026-0436,V005,External counsel retainer,38000,CC-4500,Corporate,E009,E008,2026-02-12,approved
PO-2026-0450,V008,Launch monitoring and on-call tooling,45000,CC-4700,QuickPay,E010,E004,,pending_approval
~~~~


## FILE: finance/finance_policy_excerpt.md

~~~~markdown
# Finance Policy (excerpt) - Aldermere Pay Ltd - version 2026.1

Synthetic document. Clause numbers are used by the answer key.

## 2. Budgets
**2.1** Committed spend on a budget line must not exceed the approved amount for that line.

## 3. Purchase orders and approvals
**3.1** Approval limits are set out in the delegation-of-authority table (approval_limits.csv).

**3.2** A purchase order must be approved by an approver whose limit is at least the purchase order amount.

**3.3** Spend on a product above 40,000 GBP also requires approval by that product's accountable senior manager, as named in the delegation-of-authority table.

## 4. Suppliers
**4.1** Supplier due diligence (financial, sanctions and adverse media screening) must be completed before the first purchase order for that supplier is approved.

## 5. Expenses
**5.1** Employee expense claims must be submitted within 30 days with receipts attached.
~~~~


## FILE: legal/product_approval.json

~~~~json
{
  "product": "QuickPay",
  "approval_id": "APR-2026-014",
  "approved_version": "1.4",
  "approved_on": "2026-06-12",
  "valid_until": "2027-06-12",
  "scope": "UK domestic instant payments between small-business accounts",
  "accountable_senior_manager": "E004",
  "approved_by": [
    "E003"
  ],
  "conditions": [
    "Customer payment data is processed and stored only in the United Kingdom or the European Economic Area.",
    "Staff who sell or onboard customers hold valid Payments Conduct Training (PCT-101).",
    "Material changes require re-approval under the Product Change Control Policy before release."
  ],
  "legal_register_status": "approved"
}
~~~~


## FILE: legal/obligations_register.csv

~~~~csv
obligation_id,source_doc,clause,statement,obligation_type,owner_id,applies_from,self_attested_status,last_reviewed,evidence_required,evidence_location,evidence_status,parameters
OBL-L-001,Product Approval Policy,1,"Each payments product must hold a current, unexpired Legal approval.",approval,E004,2026-06-12,compliant,2026-08-14,Approval record,legal/product_approval.json,provided,valid_until=2027-06-12
OBL-L-002,Conduct Policy,5.3,"Only employees holding valid Payments Conduct Training (PCT-101, 12 months) may sell or onboard customers to a payments product.",training,E006,2026-06-12,compliant,2026-08-14,Training records for everyone who sells or onboards,hr/training_records.csv; hr/product_staffing.csv,held_by_other_dept,course=PCT-101; validity_months=12; assessed_on=date_of_sale
OBL-L-003,Customer Terms v2.0,7.2,"Customer payment data is processed and stored only within the UK or EEA, including by sub-processors.",data_residency,E004,2026-06-12,compliant,2026-08-14,Register of suppliers that process customer data and where,finance/vendors.csv; product/product_record.json,held_by_other_dept,"allowed_regions=UK,EEA"
OBL-L-004,Customer Terms v2.0,8.4,The customer complaints procedure is documented and reviewed annually.,policy_review,E007,2026-03-01,compliant,2026-03-01,Complaints procedure with review date,legal/obligations_register.csv (review recorded 2026-03-01),provided,review_frequency_months=12
OBL-L-005,Customer Terms v2.0,9.1,"Premium customers receive 24x7 support, with at least two agents staffed at all times and a first response within 15 minutes for payment failures.",service_level,E007,2026-12-01,compliant,2026-08-14,Staffing and funding that cover the committed hours,finance/budget.csv; hr/headcount_plan.csv; hr/product_staffing.csv,held_by_other_dept,coverage=24x7; min_concurrent_agents=2; min_hours_per_week=336; first_response_minutes=15
OBL-L-006,Conduct Policy,5.4,The regulator is notified at least five business days before launching a new payments feature.,regulatory_notification,E004,2026-12-01,pending,2026-11-10,Copy of the regulator notification,,not_found,business_days_before_launch=5; due_date=2026-11-24
OBL-L-007,Product Change Control Policy,2,"Any material change to an approved product (new feature, new third-party processor of customer data, new service commitment) requires Legal re-approval before release.",change_control,E003,2026-06-12,compliant,2026-08-14,Change control request and re-approval for the release version,legal/product_approval.json; product/product_record.json,held_by_other_dept,"material_change_triggers=new_feature,new_third_party_processor,new_service_commitment"
OBL-L-008,Contract Policy,4.1,Active supplier contracts must not be past their end date.,contract_validity,E009,2026-01-01,compliant,2026-08-14,Contract register,legal/contracts_register.csv,provided,
OBL-L-009,Customer Terms v2.0,10.1,"Each product has a named accountable senior manager who is available to approve actions, respond to regulators and sign off material changes.",accountability,E003,2026-06-12,compliant,2026-08-14,Named accountable senior manager and their availability,legal/product_approval.json; hr/roster.csv,held_by_other_dept,
OBL-L-010,Contract Policy,4.2,A data processing agreement must be signed before a supplier processes customer data.,dpa,E009,2026-01-01,compliant,2026-08-14,Contract register with DPA status,legal/contracts_register.csv,provided,
~~~~


## FILE: legal/contracts_register.csv

~~~~csv
contract_id,counterparty,vendor_id,contract_type,start_date,end_date,auto_renew,dpa_required,dpa_signed,legal_owner_id,notes
C-2025-011,EuroCloud Hosting GmbH,V001,Master services agreement,2025-03-01,2027-02-28,N,Y,Y,E009,
C-2025-011-A,EuroCloud Hosting GmbH,V001,Capacity add-on addendum,2025-11-01,2026-10-31,N,Y,Y,E009,Renewal not actioned
C-2026-031,StreamLedger Inc,V002,SaaS agreement with DPA,2026-10-01,2027-09-30,Y,Y,Y,E009,
C-2025-014,Banc Link Ltd,V004,Services agreement,2025-06-01,2028-05-31,N,Y,Y,E009,
C-2025-020,Harbor Analytics Inc,V003,Subscription,2025-07-01,2026-12-31,Y,N,N,E009,No customer data involved
C-2026-007,LexAdvisory LLP,V005,Engagement letter,2026-02-01,2027-01-31,N,N,N,E003,
C-2026-012,BrightMark Agency Ltd,V006,Services agreement,2026-10-01,2026-12-31,N,N,N,E009,
C-2026-040,PulseWatch Ltd,V008,Subscription,2026-12-01,2027-11-30,Y,N,N,E009,Starts on launch day
~~~~


## FILE: legal/customer_terms_v2.0_excerpt.md

~~~~markdown
# Customer Terms v2.0 (excerpt) - Aldermere Pay Ltd

Synthetic document. Applies to QuickPay customers from the v2.0 launch.

## 7. Data protection
**7.1** Aldermere processes customer payment data only to provide and improve the service.

**7.2** Aldermere shall ensure that customer payment data is processed and stored only within the United Kingdom or the European Economic Area, including by any sub-processor.

## 8. Complaints
**8.4** Aldermere maintains a documented complaints procedure and reviews it at least once every 12 months.

## 9. Premium support
**9.1** Customers on the Premium tier are entitled to support 24 hours a day, 7 days a week, with at least two support agents staffed at all times and a first response within 15 minutes for payment failures.

## 10. Governance
**10.1** Each product shall have a named accountable senior manager who is available to approve actions, respond to regulators and sign off material changes.

## 11. Governing law
**11.1** These terms are governed by the laws of England and Wales.
~~~~


## FILE: legal/legal_policies_excerpt.md

~~~~markdown
# Legal Policies (excerpt) - Aldermere Pay Ltd

Synthetic document. Clause numbers are used by the answer key.

## Product Approval Policy
**1** Each payments product must hold a current, unexpired Legal approval.

## Conduct Policy
**5.3** Only employees who hold valid Payments Conduct Training (PCT-101, valid for 12 months) may sell or onboard customers to a payments product. Validity is assessed on the date of the sale or onboarding.

**5.4** Aldermere must notify the regulator at least five business days before launching a new payments feature.

## Product Change Control Policy
**2** Any material change to an approved product requires re-approval by Legal before release. Material changes include a new feature, a new third-party processor of customer data, and a new service commitment. Product teams must file a change control request.

## Contract Policy
**4.1** Active supplier contracts must not be past their end date.

**4.2** A data processing agreement must be signed before a supplier processes customer data.

## Records
**6.1** Legal records are retained for seven years.
~~~~


## FILE: product/product_record.json

~~~~json
{
  "product": "QuickPay",
  "description": "Instant payments service for small businesses",
  "live_version": "1.4",
  "release_candidate": "2.0",
  "launch_date": "2026-12-01",
  "product_owner": "E004",
  "engineering_lead": "E010",
  "change_control_request_filed": false,
  "changes": [
    {
      "id": "CHG-01",
      "description": "Cross-border payments to EU beneficiaries",
      "change_type": "new_feature",
      "material": true
    },
    {
      "id": "CHG-02",
      "description": "Transaction analytics and fraud scoring via StreamLedger",
      "change_type": "new_third_party_processor",
      "material": true,
      "vendor_id": "V002"
    },
    {
      "id": "CHG-03",
      "description": "Premium support tier with 24x7 support",
      "change_type": "new_service_commitment",
      "material": true
    },
    {
      "id": "CHG-04",
      "description": "Refreshed payment history screen",
      "change_type": "cosmetic",
      "material": false
    }
  ],
  "data_flows": [
    {
      "processor_vendor_id": "V001",
      "data_category": "customer payment data",
      "purpose": "hosting"
    },
    {
      "processor_vendor_id": "V004",
      "data_category": "customer payment data",
      "purpose": "open banking connectivity"
    },
    {
      "processor_vendor_id": "V002",
      "data_category": "customer payment data",
      "purpose": "analytics and fraud scoring"
    }
  ],
  "premium_support_tier": {
    "enabled": true,
    "launch_date": "2026-12-01"
  },
  "sales_enablement": {
    "assigned_sellers": 8,
    "first_sales_date": "2026-12-01"
  }
}
~~~~


## FILE: events/event_stream.json

~~~~json
{
  "as_of_start": "2026-11-18",
  "launch_date": "2026-12-01",
  "events": [
    {
      "event_id": "EV-01",
      "date": "2026-11-19",
      "description": "Chloe Dubois (E014) completes Payments Conduct Training (PCT-101).",
      "changes": [
        {
          "file": "hr/training_records.csv",
          "op": "update",
          "match": {
            "employee_id": "E014",
            "course_code": "PCT-101"
          },
          "set": {
            "status": "valid",
            "completed_date": "2026-11-19",
            "expiry_date": "2027-11-19"
          }
        }
      ]
    },
    {
      "event_id": "EV-02",
      "date": "2026-11-20",
      "description": "Regulator notification for the v2.0 launch is filed and the copy is stored.",
      "changes": [
        {
          "file": "legal/obligations_register.csv",
          "op": "update",
          "match": {
            "obligation_id": "OBL-L-006"
          },
          "set": {
            "evidence_location": "REG-NOTIF-2026-118 (filed 2026-11-20)",
            "evidence_status": "provided",
            "self_attested_status": "compliant",
            "last_reviewed": "2026-11-20"
          }
        }
      ]
    },
    {
      "event_id": "EV-03",
      "date": "2026-11-23",
      "description": "New identity-verification supplier VerifyPoint Inc (US) is onboarded and added to the QuickPay data flows. Finance and Legal paperwork is complete.",
      "changes": [
        {
          "file": "finance/vendors.csv",
          "op": "insert",
          "row": {
            "vendor_id": "V007",
            "vendor_name": "VerifyPoint Inc",
            "service_description": "Identity verification for new customers",
            "country": "United States",
            "handles_customer_data": "Y",
            "data_processing_region": "US-East",
            "dd_status": "completed",
            "dd_completed_date": "2026-11-20",
            "dd_scope": "financial; sanctions; adverse media",
            "annual_value_gbp": "28000",
            "contract_ref": "C-2026-045",
            "business_owner_id": "E010",
            "status": "active"
          }
        },
        {
          "file": "finance/budget.csv",
          "op": "insert",
          "row": {
            "line_id": "B-011",
            "fiscal_year": "2026",
            "cost_center": "CC-4800",
            "product": "QuickPay",
            "line_item": "Identity verification (VerifyPoint)",
            "category": "vendor",
            "approved_budget_gbp": "30000",
            "committed_gbp": "28000",
            "spent_ytd_gbp": "0",
            "owner_id": "E010",
            "coverage_notes": ""
          }
        },
        {
          "file": "finance/purchase_orders.csv",
          "op": "insert",
          "row": {
            "po_id": "PO-2026-0462",
            "vendor_id": "V007",
            "description": "Identity verification service",
            "amount_gbp": "28000",
            "cost_center": "CC-4800",
            "product": "QuickPay",
            "requested_by": "E010",
            "approver": "E008",
            "approval_date": "2026-11-23",
            "status": "approved"
          }
        },
        {
          "file": "legal/contracts_register.csv",
          "op": "insert",
          "row": {
            "contract_id": "C-2026-045",
            "counterparty": "VerifyPoint Inc",
            "vendor_id": "V007",
            "contract_type": "SaaS agreement with DPA",
            "start_date": "2026-11-23",
            "end_date": "2027-11-22",
            "auto_renew": "Y",
            "dpa_required": "Y",
            "dpa_signed": "Y",
            "legal_owner_id": "E009",
            "notes": ""
          }
        },
        {
          "file": "product/product_record.json",
          "op": "append",
          "path": "data_flows",
          "value": {
            "processor_vendor_id": "V007",
            "data_category": "customer identity data",
            "purpose": "identity verification"
          }
        }
      ]
    },
    {
      "event_id": "EV-04",
      "date": "2026-11-25",
      "description": "Legal names Priya Sharma (E010) as the new accountable senior manager and reassigns E004's obligations. HR updates the staffing sheet. Finance's approval table is not updated.",
      "changes": [
        {
          "file": "hr/product_staffing.csv",
          "op": "update",
          "match": {
            "employee_id": "E010",
            "product": "QuickPay"
          },
          "set": {
            "role_on_product": "Engineering Lead and Accountable Senior Manager"
          }
        },
        {
          "file": "legal/product_approval.json",
          "op": "set",
          "path": "accountable_senior_manager",
          "value": "E010"
        },
        {
          "file": "product/product_record.json",
          "op": "set",
          "path": "product_owner",
          "value": "E010"
        },
        {
          "file": "legal/obligations_register.csv",
          "op": "update",
          "match": {
            "obligation_id": "OBL-L-001"
          },
          "set": {
            "owner_id": "E010"
          }
        },
        {
          "file": "legal/obligations_register.csv",
          "op": "update",
          "match": {
            "obligation_id": "OBL-L-003"
          },
          "set": {
            "owner_id": "E010"
          }
        },
        {
          "file": "legal/obligations_register.csv",
          "op": "update",
          "match": {
            "obligation_id": "OBL-L-006"
          },
          "set": {
            "owner_id": "E010"
          }
        }
      ]
    },
    {
      "event_id": "EV-05",
      "date": "2026-11-27",
      "description": "Meera Iyer (E004) works her last day. The pending monitoring purchase order is still routed to her.",
      "changes": [
        {
          "file": "hr/roster.csv",
          "op": "update",
          "match": {
            "employee_id": "E004"
          },
          "set": {
            "status": "left",
            "leaver_checklist": "complete"
          }
        },
        {
          "file": "hr/product_staffing.csv",
          "op": "update",
          "match": {
            "employee_id": "E004",
            "product": "QuickPay"
          },
          "set": {
            "allocation_pct": "0"
          }
        }
      ]
    },
    {
      "event_id": "EV-06",
      "date": "2026-11-30",
      "description": "Finance adds Priya Sharma (E010) to the approval table and reroutes the pending purchase order to her.",
      "changes": [
        {
          "file": "finance/approval_limits.csv",
          "op": "insert",
          "row": {
            "approver_id": "E010",
            "role_title": "QuickPay Accountable Senior Manager",
            "scope": "QuickPay product spend",
            "limit_gbp": "250000",
            "delegate_id": "",
            "valid_from": "2026-11-30",
            "valid_to": "2027-11-29"
          }
        },
        {
          "file": "finance/purchase_orders.csv",
          "op": "update",
          "match": {
            "po_id": "PO-2026-0450"
          },
          "set": {
            "approver": "E010"
          }
        }
      ]
    }
  ]
}
~~~~


## FILE: answer_key/expected_obligations.csv

~~~~csv
obligation_id,department,source_doc,clause,short_statement,type,key_parameters
OBL-H-001,HR,HR Policy,3.1,Department must not exceed approved headcount,headcount,
OBL-H-002,HR,HR Policy,4.1,All employees complete COC-100 every 12 months,training,course=COC-100; validity_months=12
OBL-H-003,HR,HR Policy,4.2,All employees complete DPA-110 every 12 months,training,course=DPA-110; validity_months=12
OBL-H-004,HR,HR Policy,6.2,HR starts leaver checklist on resignation (HR systems only); managers reassign duties in other systems,leaver_process,
OBL-H-005,HR,HR Policy,7.1,Support hiring freeze until 2027-03-31; exceptions need COO and Head of Finance,hiring_freeze,frozen_until=2027-03-31
OBL-F-001,Finance,Finance Policy,2.1,Committed spend must not exceed approved budget line,budget,
OBL-F-002,Finance,Finance Policy,3.2,PO approver limit must be at least the PO amount,approval_limit,
OBL-F-003,Finance,Finance Policy,3.3,"Product spend above 40,000 GBP also needs the product's accountable senior manager",approval_routing,threshold_gbp=40000
OBL-F-004,Finance,Finance Policy,4.1,Supplier due diligence complete before first PO approval,due_diligence,
OBL-L-001,Legal,Product Approval Policy,1,Each payments product holds a current unexpired Legal approval,approval,
OBL-L-002,Legal,Conduct Policy,5.3,Only staff with valid PCT-101 may sell or onboard,training,course=PCT-101; validity_months=12
OBL-L-003,Legal,Customer Terms v2.0,7.2,"Customer payment data processed and stored only in UK or EEA, including sub-processors",data_residency,"allowed_regions=UK,EEA"
OBL-L-004,Legal,Customer Terms v2.0,8.4,Complaints procedure documented and reviewed annually,policy_review,
OBL-L-005,Legal,Customer Terms v2.0,9.1,"Premium tier: 24x7 support, two agents at all times, 15-minute first response",service_level,min_hours_per_week=336
OBL-L-006,Legal,Conduct Policy,5.4,Notify regulator 5 business days before launching a new payments feature,regulatory_notification,due_date=2026-11-24
OBL-L-007,Legal,Product Change Control Policy,2,Material changes need Legal re-approval before release,change_control,
OBL-L-008,Legal,Contract Policy,4.1,Active supplier contracts must not be past end date,contract_validity,
OBL-L-009,Legal,Customer Terms v2.0,10.1,Each product has a named accountable senior manager who is available,accountability,
OBL-L-010,Legal,Contract Policy,4.2,DPA signed before a supplier processes customer data,dpa,
~~~~


## FILE: answer_key/expected_department_checks.csv

~~~~csv
check_id,department,check,expected_status,exceptions,source_files,notes
HR-C1,HR,Code of Conduct (COC-100) valid for all active staff,met,,hr/training_records.csv,
HR-C2,HR,Data Protection (DPA-110) valid for all active staff,unmet,E022,hr/training_records.csv,Lucas Meyer's DPA-110 expired 2026-10-20
HR-C3,HR,Leaver checklist started for staff serving notice,met,,hr/roster.csv,E004 checklist initiated. HR sees nothing wrong.
HR-C4,HR,Filled headcount does not exceed approved headcount,met,,hr/headcount_plan.csv,
HR-C5,HR,Frozen departments have no open requisitions,met,,hr/headcount_plan.csv,
FIN-C1,Finance,Committed spend within approved budget on every line,met,,finance/budget.csv,
FIN-C2,Finance,Approved PO amount is within the approver's limit,unmet,PO-2026-0412,finance/purchase_orders.csv; finance/approval_limits.csv,"62,000 GBP approved by an approver with a 50,000 GBP limit"
FIN-C3,Finance,"Product spend above 40,000 GBP approved by the accountable senior manager",unmet,PO-2026-0412,finance/purchase_orders.csv; finance/approval_limits.csv,Same purchase order as FIN-C2
FIN-C4,Finance,Supplier due diligence completed before first approved PO,met,,finance/vendors.csv; finance/purchase_orders.csv,Due diligence does not cover where data is processed
LEG-C1,Legal,"Product has a current, unexpired Legal approval",met,,legal/product_approval.json,Approval covers v1.4 and is unexpired. Legal is unaware of v2.0.
LEG-C2,Legal,Every obligation has a named owner and a self-attestation reviewed in the last 12 months,met,,legal/obligations_register.csv,"Legal cannot see the roster, so it cannot tell that a named owner is leaving. Self-attestation is not primary evidence."
LEG-C3,Legal,Active supplier contracts are not past their end date,unmet,C-2025-011-A,legal/contracts_register.csv,EuroCloud capacity addendum ended 2026-10-31
LEG-C4,Legal,DPA signed for every contract that requires one,met,,legal/contracts_register.csv,A signed DPA says nothing about processing location
LEG-C5,Legal,Evidence located for obligations where Legal holds the evidence,unknown,OBL-L-006,legal/obligations_register.csv,"No regulator notification on file. Due 2026-11-24, so not yet overdue."
~~~~


## FILE: answer_key/expected_seams.json

~~~~json
{
  "as_of": "2026-11-18",
  "launch_date": "2026-12-01",
  "seams": [
    {
      "seam_id": "S1",
      "type": "orphaned_obligation",
      "title": "Accountable owner leaves before launch",
      "departments": [
        "HR",
        "Legal",
        "Finance"
      ],
      "severity": "high",
      "blocks_launch": true,
      "evidence": [
        "hr/roster.csv: E004 last working day 2026-11-27, before launch 2026-12-01",
        "legal/product_approval.json: accountable_senior_manager = E004",
        "legal/obligations_register.csv: OBL-L-001, OBL-L-003, OBL-L-006 owned by E004",
        "finance/approval_limits.csv: E004 is the only approver for QuickPay product spend, no delegate",
        "finance/purchase_orders.csv: PO-2026-0450 pending with E004"
      ],
      "why_no_single_department_sees_it": "HR sees a normal leaver process. Legal sees a named owner. Finance sees a valid approver. Only together do they show the owner is gone at launch.",
      "detection_logic": "Owner or approver status is left, or serving notice with last working day before launch; scope has no other active approver.",
      "suggested_resolution": "Name a successor, reassign Legal obligations, update the Finance approval table and reroute pending purchase orders.",
      "resolver_role": "Head of HR with General Counsel and Head of Finance",
      "validation": {
        "legal_references": [
          "ASM:E004",
          "OBL-L-001",
          "OBL-L-003",
          "OBL-L-006"
        ],
        "finance_references": [
          "PO-2026-0450",
          "SCOPE:QuickPay product spend"
        ]
      }
    },
    {
      "seam_id": "S2",
      "type": "unmet_dependency",
      "title": "Sellers without valid conduct training at launch",
      "departments": [
        "HR",
        "Legal"
      ],
      "severity": "high",
      "blocks_launch": false,
      "evidence": [
        "legal/legal_policies_excerpt.md: Conduct Policy 5.3",
        "hr/product_staffing.csv: 8 sellers assigned to QuickPay sales from 2026-12-01",
        "hr/training_records.csv: E013 PCT-101 expires 2026-11-25; E014 and E015 never started"
      ],
      "why_no_single_department_sees_it": "HR's mandatory list has only COC-100 and DPA-110. Legal holds the rule but not the training records.",
      "detection_logic": "For each seller, PCT-101 must be valid on the launch date; no record, not started, or expiry before launch is a violation.",
      "suggested_resolution": "Complete training before launch or remove the three from selling until they are valid.",
      "resolver_role": "Head of Sales with Head of HR",
      "validation": {
        "untrained_at_launch": [
          "E013",
          "E014",
          "E015"
        ]
      }
    },
    {
      "seam_id": "S3",
      "type": "contradiction",
      "title": "Customer data processed outside UK and EEA",
      "departments": [
        "Legal",
        "Finance"
      ],
      "severity": "critical",
      "blocks_launch": true,
      "evidence": [
        "legal/customer_terms_v2.0_excerpt.md: 7.2 UK or EEA only",
        "product/product_record.json: StreamLedger (V002) receives customer payment data in v2.0",
        "finance/vendors.csv: V002 handles customer data, processing region US-East"
      ],
      "why_no_single_department_sees_it": "Finance records the region but not the contract promise. Legal records the promise and a signed DPA but not the region.",
      "detection_logic": "Processors in the product's data flows that handle customer data with a processing region outside UK and EEA.",
      "suggested_resolution": "Move processing to UK or EEA, or remove StreamLedger from the v2.0 data flow before launch.",
      "resolver_role": "General Counsel with Engineering Lead",
      "validation": {
        "non_eea_processors": [
          "V002"
        ]
      }
    },
    {
      "seam_id": "S4",
      "type": "promise_without_capacity",
      "title": "24x7 support promised without staff or budget",
      "departments": [
        "Legal",
        "Finance",
        "HR"
      ],
      "severity": "high",
      "blocks_launch": true,
      "evidence": [
        "legal/customer_terms_v2.0_excerpt.md: 9.1 24x7 with two agents at all times",
        "legal/obligations_register.csv: OBL-L-005 min_hours_per_week=336",
        "finance/budget.csv: B-001 six FTE, business hours only",
        "hr/headcount_plan.csv: Support hiring frozen until 2027-03-31",
        "hr/product_staffing.csv: 6 support agents"
      ],
      "why_no_single_department_sees_it": "Legal wrote the promise. Finance funded business hours. HR is within headcount and the freeze. No one compares required hours with available hours.",
      "detection_logic": "Required staffed hours (168 x 2 = 336) minus agents x weekly contract hours (6 x 40 = 240) = 96 hours short, with hiring frozen past launch.",
      "suggested_resolution": "Approve a freeze exception and out-of-hours budget, buy a managed overnight service, or delay the Premium tier.",
      "resolver_role": "COO with Head of Support and Head of Finance",
      "validation": {
        "required_hours_per_week": 336,
        "available_hours_per_week": 240,
        "shortfall_hours_per_week": 96
      }
    },
    {
      "seam_id": "S5",
      "type": "stale_evidence",
      "title": "Approval covers v1.4 but v2.0 ships",
      "departments": [
        "Legal",
        "Product"
      ],
      "severity": "high",
      "blocks_launch": true,
      "evidence": [
        "legal/product_approval.json: approved_version 1.4",
        "product/product_record.json: release_candidate 2.0 with three material changes and no change control request",
        "legal/legal_policies_excerpt.md: Change Control Policy 2"
      ],
      "why_no_single_department_sees_it": "Legal's approval is valid and unexpired for v1.4. The product record that shows v2.0 is not part of Legal's data.",
      "detection_logic": "Approved version differs from release candidate and at least one change is material with no change control request filed.",
      "suggested_resolution": "File a change control request and obtain Legal re-approval for v2.0 before release.",
      "resolver_role": "Accountable senior manager with General Counsel",
      "validation": {
        "approved_version": "1.4",
        "release_candidate": "2.0",
        "material_changes": [
          "CHG-01",
          "CHG-02",
          "CHG-03"
        ]
      }
    }
  ],
  "department_only_view": "Each department shows minor findings only (HR 1, Finance 1 purchase order, Legal 1 expired contract and 1 unknown). Nothing blocks launch.",
  "seam_view": "Five seams. S1, S3, S4 and S5 block launch. S2 is conditional (restrict selling to trained staff)."
}
~~~~


## FILE: answer_key/expected_event_effects.json

~~~~json
{
  "note": "Effects are cumulative. Open seams are listed after each event is applied.",
  "baseline": {
    "open_seams": [
      "S1",
      "S2",
      "S3",
      "S4",
      "S5"
    ]
  },
  "events": [
    {
      "event_id": "EV-01",
      "expect": {
        "s2_untrained": [
          "E013",
          "E015"
        ]
      },
      "open_seams": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5"
      ],
      "narrative": "S2 shrinks from three people to two but stays open."
    },
    {
      "event_id": "EV-02",
      "expect": {
        "leg_c5_exceptions": []
      },
      "open_seams": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5"
      ],
      "narrative": "The unknown on the regulator notification becomes met."
    },
    {
      "event_id": "EV-03",
      "expect": {
        "s3_non_eea_processors": [
          "V002",
          "V007"
        ]
      },
      "open_seams": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5"
      ],
      "narrative": "A second non-EEA processor appears. Finance and Legal paperwork for it is clean, so no department flags it."
    },
    {
      "event_id": "EV-04",
      "expect": {
        "s1_legal_references": [],
        "s1_finance_references": [
          "PO-2026-0450",
          "SCOPE:QuickPay product spend"
        ],
        "s1_blocked_pending_pos": []
      },
      "open_seams": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5"
      ],
      "narrative": "Legal side of S1 is fixed. The Finance side remains."
    },
    {
      "event_id": "EV-05",
      "expect": {
        "s1_legal_references": [],
        "s1_finance_references": [
          "PO-2026-0450",
          "SCOPE:QuickPay product spend"
        ],
        "s1_blocked_pending_pos": [
          "PO-2026-0450"
        ]
      },
      "open_seams": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5"
      ],
      "narrative": "The pending purchase order is now stuck with someone who has left."
    },
    {
      "event_id": "EV-06",
      "expect": {
        "s1_legal_references": [],
        "s1_finance_references": [],
        "s1_blocked_pending_pos": []
      },
      "open_seams": [
        "S2",
        "S3",
        "S4",
        "S5"
      ],
      "narrative": "S1 is fully resolved. The passport improves but stays no-go."
    }
  ]
}
~~~~


## FILE: answer_key/decoys_and_noise.csv

~~~~csv
item_id,kind,where,why_it_must_not_be_flagged
D1,decoy,finance/vendors.csv V003 Harbor Analytics Inc,US supplier but handles no customer data and is not in the QuickPay data flows. A naive 'US vendor' rule would flag it wrongly.
D2,decoy,hr/roster.csv E028 Rita Alvarez,Left on 2026-09-15 and owns nothing. A naive 'left employee' rule would flag her wrongly.
D3,decoy,hr/training_records.csv E017 Farid Hassan,"PCT-101 valid until 2027-02-18, so valid on launch."
D4,decoy,hr/training_records.csv E020-E024,"Support agents have no PCT-101 but do not sell or onboard, so it is not required."
D5,decoy,legal/obligations_register.csv OBL-L-004,"Complaints procedure reviewed 2026-03-01, within 12 months."
D6,decoy,legal/obligations_register.csv OBL-L-006,"Regulator notification not on file but due 2026-11-24, so it is unknown, not overdue."
D7,decoy,finance/purchase_orders.csv PO-2026-0436,"38,000 GBP corporate spend is within the approver's limit and below the 40,000 GBP product threshold."
N1,noise_clause,hr/hr_policy_excerpt.md 5.1,Remote working is not an obligation to extract.
N2,noise_clause,hr/hr_policy_excerpt.md 6.1,"Descriptive, not an obligation to test."
N3,noise_clause,finance/finance_policy_excerpt.md 5.1,Expense claim rule is out of scope for this dataset.
N4,noise_clause,legal/customer_terms_v2.0_excerpt.md 7.1 and 11.1,Not testable obligations.
N5,noise_clause,legal/legal_policies_excerpt.md 6.1,Records retention is out of scope.
~~~~


## FILE: tools/validate_dataset.py

~~~~python
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
~~~~

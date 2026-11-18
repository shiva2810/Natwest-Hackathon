# EU Banking Compliance Checker — Problem Statement

## Presentation version

NatWest operates in a complex European banking environment where regulatory obligations can affect HR, Legal and Finance records at the same time. Reviews that rely on separate departmental checks can miss gaps that only become visible when those records are considered together. Manual comparisons also make it hard for an auditor to trace a conclusion from the relevant policy wording to the exact internal evidence used.

We are developing an explainable compliance checker for NatWest that organizes in-scope EU regulatory and internal policy material into a versioned, traceable corpus, then evaluates applicable requirements against available HR, Legal and Finance data. A review may cover one domain or any combination of the three. The checker reports each requirement as passed, failed or requiring review, with a plain-language summary, linked policy and internal evidence, and a navigable record of how the decision was reached.

Internal auditors can open each evaluation step, inspect the policy section and internal document passage side by side, follow source links, and record their assessment. The checker supports the audit process; the auditor retains responsibility for the final judgment.

## One-slide version

**Problem:** EU banking compliance reviews can miss cross-functional issues when HR, Legal and Finance are checked separately. Manual policy-to-evidence comparisons are slow and difficult to audit.

**Solution:** Build an explainable checker for NatWest that evaluates EU and applicable internal policy requirements against HR, Legal and Finance data, separately or in combination.

**Auditor experience:** Every result links to the exact policy clause and internal evidence, with an interactive decision trail that opens the evaluation details and source documents.

**Outcome:** More traceable, consistent reviews across selected compliance domains, with human auditors in control of conclusions.

## Scope assumptions

- **Client and sector:** NatWest, banking.
- **Regulatory context:** European Union. The applicable EU instruments, member-state rules, NatWest policies, and entity or product scope must be explicitly selected and validated for each review; this sample does not claim a definitive legal scope.
- **Review domains:** HR, Legal and Finance. Any one domain or any combination may be selected. Cross-domain checks can use evidence from multiple selected domains where the rule requires it.
- **Result states:** Passed, failed, and needs review. Missing, conflicting, stale, or out-of-scope evidence should be visible and should not silently count as a pass.
- **Human role:** Internal auditor inspects the evidence and rationale, records corrections or comments, and owns the final assessment.

## Intended workflow

1. Select the NatWest entity, product or process, review period, EU jurisdictional scope, and one or more domains: HR, Legal, Finance.
2. Retrieve in-scope official regulatory sources and approved internal policies. Preserve exact source URLs, versions, retrieval dates, relevant provisions, and content fingerprints.
3. Extract requirements into a versioned policy corpus with applicability, domain ownership, and links to source passages.
4. Identify relevant internal records and document passages from selected domains, retaining document version, record identifier, and location.
5. Evaluate each applicable requirement against its evidence. Record matching, missing, conflicting, or stale evidence and the rule or reasoning that led to the outcome.
6. Produce an audit report with a summary and individual findings. Every decision-trail step opens a detail view that links directly to the policy provision and the internal document or data record evaluated.
7. Allow the auditor to inspect, annotate, challenge, and record the final review. Keep machine findings distinct from human decisions in the audit history.

## Traceability requirements

- Each finding identifies its domain or domains and the evidence sources that contributed to it.
- Policy-corpus and source-check steps open a view of the source, extracted provision, applicability decision, and evaluation against internal evidence.
- Policy text and internal evidence are directly accessible at the cited section, page, clause, or record. For structured data, show the relevant fields and record identifier.
- Decision details show the evaluation method, evidence considered, limitations or uncertainty, and resulting status.
- Policy snapshots, source versions, internal document versions, and auditor changes are reproducible and recorded.

## Sample report

Open `sample-audit-report.html` in a browser. It demonstrates domain filters and selectable evidence-trail steps that navigate to detailed policy-to-evidence evaluations. All organizations, findings, policies, source excerpts and identifiers in the mockup are illustrative; they are not validated NatWest records or legal advice.

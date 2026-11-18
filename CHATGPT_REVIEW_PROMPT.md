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

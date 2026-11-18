# Compliance seam detector

HR, Finance and Legal checkers feed a seam detector that produces a living compliance passport.

## Run it
```
uv venv .venv && uv pip install --python .venv -r requirements.txt
cp .env.example .env                                # paste ANTHROPIC_API_KEY (optional; .env is git-ignored)
.venv/bin/python -m pytest -q                       # tests (never call a live model)
.venv/bin/python -m scripts.eval_dataset            # score against data/answer_key: obligations, checks, seams, events
./scripts/run_demo.sh --fresh                       # API :8765 + UI :8501 on the real dataset, reset
.venv/bin/python -m scripts.demo_story --pause      # the demo story beat by beat (rehearsal / backup)
.venv/bin/python -m scripts.warm_llm                # with a key: run everything through Claude once, fill cache/llm/
.venv/bin/python -m scripts.extract --all-events    # just the extraction -> runs/records.json + report
```
What-if testing: `scenarios/*.json` (same format as the event stream; copy one to make your own),
applied from the UI, `POST /scenarios/<name>`, or `SeamClient().scenario("<name>")`.
Two processes, no workers or queues: the full pipeline runs in under a second.
If the API is down, the UI's `SeamClient` runs the engine in-process on the same state file.

## Live demo
`./scripts/run_demo.sh --fresh`, then open http://localhost:8501 (anyone on the same Wi-Fi can use the
"Network URL" it prints). The **Live check** panel answers "what if…?" on the spot:
- *Ask in plain English*: Claude drafts the data change (needs the key; cached answers replay offline)
- *Edit a record*: pick file, record, field, new value (always works, no model)

Either way you see every before/after, the predicted effect (seams opened/closed, overall status),
and nothing changes until a named person presses **Apply for real** (audit-logged as LIVE-n).
`ui/live_check.py` is a drop-in `render(client)` for Person 3's UI. With the API down, the UI runs
the engine in-process, so the UI alone can also be hosted (e.g. Streamlit Community Cloud, key as a secret).

## How it fits together
```
data/ (Person 1) ──extract──> records + entities ──LangGraph──> check_departments → build_graph
  CSV/JSON: rules     policy text: clause rules or Claude (quote-checked)   → detect_seams → score
                                                                            → referee (Claude/templates) → propose_drafts
events/ + scenarios/ ──> file changes ──> re-extract ──> selective re-check (verified against a full re-check)
                   ├── governance: tiers, named sign-off, drafts, hash-chained audit (runs/audit.jsonl)
                   ├── state saved after every change (runs/state.json) — survives restarts
                   └── FastAPI (:8765) ──> SeamClient ──> Streamlit UI (:8501, Person 3)
```

## Audit report (HTML)
The user gets the report as a single HTML file, built from the live passport:
- UI: **Download report** button (top right) or the **Audit report** tab (preview).
- API: `GET /report` (add `?download=true` to save). CLI: `python -m scripts.export_report [path]` -> `reports/`.
- Code: `SeamClient().report()` or `seam.report.render_report(passport, audit)`.

## Handoffs
- **Person 1 → 2:** a `records.json` matching `seam/schema.py::Bundle`. Run with `SEAM_RECORDS=path`.
  A new or changed file triggers a fresh run automatically. Until then, `fixtures/records.json` has 5 planted seams
  (`fixtures/answer_key.json`). Bad files fail with a clear message (missing product, duplicate ids).
- **Person 2 → 3:** use `seam.client.SeamClient`: `passport()`, `event()`, `sign()`, `decide_draft()`,
  `history()`, `audit()`, `reset()`. The raw API is listed in `seam/api.py` (docs at :8765/docs).
- **Person 1 (X.1):** pass the LLM wrapper as `Engine(..., llm=fn)`, where `fn(prompt) -> {"explanation", "fix_options"}`.

## Layout
| File | Component |
|---|---|
| `seam/schema.py` | 2.1 schema (draft until the freeze) |
| `seam/graph.py` | 4.1 graph |
| `seam/rules.py` | 4.2 seam rules (5 types + unbudgeted-contract bonus) |
| `seam/scoring.py` | 4.3 severity and priority |
| `seam/referee.py` | 4.4 referee (templates offline; optional LLM) |
| `seam/pipeline.py` | LangGraph workflow, event mutations, agent drafts |
| `seam/governance.py`, `config/autonomy_tiers.json` | 5.1 tiers, 5.2 sign-off, 5.3 audit log |
| `seam/engine.py` | state, persistence, sign-off/draft flow, passport roll-up |
| `seam/api.py`, `seam/client.py` | X.2 API and the UI client |
| `seam/report.py` | audit report: one self-contained HTML file in the layout of `samples/compliance-checker/sample-audit-report.html` |
| `ui/app.py` | placeholder UI (Person 3 replaces) |
| `scripts/` | demo launcher and scripted story |

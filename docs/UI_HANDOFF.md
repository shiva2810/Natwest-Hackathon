# UI handoff (Person 3): what to build on top of the engine

The engine, API and a working placeholder UI are done. Your job is the page the manager and the
judges see. Build against the real API, or straight from the sample JSON in `docs/samples/`.

**Golden rule: the UI never computes compliance.** Every status, seam, severity and explanation
comes from the API. The UI only shows it and sends human decisions back.

## Run the backend
```
uv venv .venv && uv pip install --python .venv -r requirements.txt
./scripts/run_demo.sh --fresh        # API on :8765 (docs at /docs), placeholder UI on :8501
```
In Python, use the client. It talks to the API, and if the API is down it runs the engine in-process:
```python
from seam.client import SeamClient, SeamError
c = SeamClient()
p = c.passport()
```
`ui/app.py` is the placeholder: copy from it freely. `ui/live_check.py` is a finished drop-in panel.

## Screens to build (in priority order)

### 1. Passport header (6.1): never cut
| Show | From `passport` |
|---|---|
| Product, version, launch date | `product.name`, `product.version`, `product.launch_date` |
| "As of" date (moves as events replay) | `as_of` |
| Overall status, big | `overall`: `go` / `conditional` / `no_go` |
| Why it is blocked | `blocking_seams` (ids) |
| Sign-off state | `signoff.state` (`pending` / `go` / `no_go`), `signoff.by`, `signoff.reason`; `signoff.invalidated` when an event reset it |
| Last verified, rules version | `last_verified`, `policy_versions.rules` |
| Disclaimer (always visible) | `disclaimer` |

### 2. Departments: "alone vs together" (the pitch in one picture)
For each of `departments.{HR, Finance, Legal, Product}`:
- `own_view`: what the department sees on its own data
- `status`: what it is once the seams are counted
- `findings[]`: in-department issues (`record`, `status`, `finding`, `items[]`)
- `self_attested[]`: Legal rows it **cannot verify alone**. Label these "self-attested"; that is the blind spot.

The story: every department looks mostly fine alone, and the combined view is NO-GO.

### 3. Seams list (6.1): never cut
For each of `seams[]` (already ranked):
| Field | Use |
|---|---|
| `title` | headline |
| `severity` (`critical`/`high`/`medium`/`low`), `blocks_launch` | badge; show "does not block launch" when false |
| `departments` | chips: which departments meet at this seam |
| `explanation`, `fix_options[]` | body (written by Claude; `facts.explained_by` says `llm` or `template`) |
| `basis[]` | "Basis:" line. Each item says *EU law*, *Internal policy* or *Contract*; never present policy as law |
| `fix_owner` | who should act |
| `facts` | evidence detail (lists such as `roles`, `breaches`, `sellers_without_valid_training`) |
| `status`, `waiver` | `waived` shows who waived it and why |

### 4. Sign-off and waivers (5.2): never cut
- `POST /signoffs` `{decision: "go"|"no_go"|"waive", signer_name, signer_role, reason, seam_id?}`
- `409` = refused (for example GO while `blocking_seams` is not empty). **Show the message**: it is part of the demo.
- `422` = blank name, role or reason.

### 5. Live check panel: ready, just mount it
`from ui.live_check import render; render(c)`. A judge asks "what if…" in plain English (Claude) or
edits one record (offline). It shows before/after, the predicted effect, then a named person applies it.
API, if you build your own: `POST /live/propose {question}`, `POST /live/field {file,key,field,value}`
-> simulation (sample: `simulation_live_check.json`), then `POST /live/apply {event, confirmed_by, reason}`.

### 6. Event timeline and what-if buttons (6.3)
- `passport.events[]`: Person 1's stream (`event_id`, `date`, `description`, `applied`) -> `POST /events/stream/{id}`
- `passport.scenarios[]`: what-ifs (`name`, `description`, `applied`) -> `POST /scenarios/{name}`
- Each returns `{diff, passport}`; replace your passport with the new one.

### 7. Before/after diff (6.4): cut second if late
From the `diff` of the last action, or `GET /history` (list of `{at, before, after, diff}`):
`opened[]`, `closed[]`, `changed[]` seam ids, `status_before` -> `status_after`,
`departments_before` -> `departments_after`, `invalidated_signoff`, and
`selective_matches_full` (show a small "verified ✓": the selective re-check matched a full one).

### 8. Agent drafts (5.1)
`passport.drafts[]`: actions an agent prepared but may not perform. Approve or reject with a name:
`POST /drafts/{id}/approve|reject {signer_name, signer_role, reason, params?}`.
`reassign_owner` needs `params.owner_id`: pick from `passport.people[]`.

### 9. Audit (5.3)
`GET /audit` -> `verify.ok` (hash chain intact) and `entries[]`. A green "chain intact ✓" is enough.

### Also available
`evidence_expiring[]` (`what`, `expires_on`), `extraction` (records per department, quote-check result),
`POST /run` (reset the demo), `POST /agent/attempt/go_no_go` (403: shows an agent cannot sign).

## Samples (real output, Claude explanations included)
| File | What |
|---|---|
| `passport_baseline.json` | the passport at the start |
| `event_EV-01_response.json` | `{diff, passport}` after one event |
| `simulation_live_check.json` | a live-check simulation (nothing applied) |
| `live_propose_response.json` | a plain-English what-if drafted by Claude |
| `history.json`, `audit.json`, `editable.json` | diff history, audit log, form-editor options |

## Demo flow the UI must support (`scripts/demo_story.py` is the scripted version)
1. Reset -> NO-GO, 5 seams; every department looks fine alone.
2. Open the top seam: explanation, basis, fix options.
3. Try GO -> refused (409 message on screen). Agent tries -> 403.
4. Play EV-01…EV-06: watch S2 shrink, S3 grow, S1 close; the diff view shows each step.
5. Live check from a judge's question -> preview -> apply.
6. Fix with what-ifs, waive the last seam with a reason, sign GO.
7. A resignation what-if -> a new seam opens and GO resets to pending automatically.
8. Audit: chain intact.

## Acceptance checklist
- [ ] Header, departments, seams and sign-off render from `GET /passport` alone
- [ ] 409/422 messages are shown to the user, never swallowed
- [ ] Every action replaces the passport with the one returned (no stale state)
- [ ] Works at 1280px and on a phone (judges may open the Network URL)
- [ ] Nothing in the UI decides met/unmet, severity or go/no-go

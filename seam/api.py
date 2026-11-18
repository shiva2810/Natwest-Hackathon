"""API (component X.2). Run: .venv/bin/uvicorn seam.api:app --port 8765

Source: the real dataset in data/ by default (SEAM_DATA to override); set SEAM_RECORDS to a
records.json to run on fixtures instead.
LLM: with ANTHROPIC_API_KEY or OPENAI_API_KEY (env or .env; see seam/providers.py) the referee uses that model, cached in cache/llm/;
without one it replays the cache and falls back to template text. SEAM_LLM=off forces offline.
SEAM_LLM_EXTRACT=on also uses Claude for policy-text extraction (default: deterministic).

Endpoints (the Person 2 <-> Person 3 contract):
  GET  /health
  GET  /passport                    current passport (departments, seams, drafts, events, scenarios, people)
  POST /run                         reload the source and start fresh (also the demo reset)
  GET  /events/stream               Person 1's event stream with applied flags
  POST /events/stream/{event_id}    apply one event from the stream -> {"diff", "passport"}
  GET  /scenarios                   what-if scenarios in scenarios/
  POST /scenarios/{name}            apply one -> {"diff", "passport"}
  POST /events/custom               apply an ad-hoc event in the stream's file-change format
  POST /events                      typed event (fixtures mode only)
  POST /audit/ask                   {"question"} -> routed to a scoped audit (HR/Finance/Legal, any mix) or a what-if
  POST /sources/upload               add a csv / md / txt / json reference file to a department
  GET  /audit/scope?domains=HR,Legal  scoped audit without a question (preset buttons)
  GET  /live/editable               tables/rows/columns and doc fields the form editor can change
  POST /live/field                  {"file", "key": {...}, "field", "value"} -> simulation (nothing applied)
  POST /live/propose                {"question"} -> Claude drafts the change -> simulation (nothing applied)
  POST /live/simulate               {"event"} -> predicted effect (nothing applied)
  POST /live/apply                  {"event", "confirmed_by", "reason"} -> applied for real
  POST /signoffs                    {"decision": "go|no_go|waive", "signer_name", "signer_role", "reason", "seam_id"?}
  POST /drafts/{id}/approve         {"signer_name", "signer_role", "reason", "params"?: {"owner_id": ...}}
  POST /drafts/{id}/reject          same body
  GET  /history                     before/after snapshots for the diff view
  GET  /audit                       entries + tamper check
  GET  /report[?download=true]      the audit report as one self-contained HTML page
  POST /agent/attempt/{action}      show the tier policy stopping an agent
"""
from __future__ import annotations

import base64
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from .engine import Engine
from .governance import ROOT, GovernanceError, SignOff
from .pipeline import Event
from .sources import EventError
from .report import render_report

SOURCE = Path(os.environ.get("SEAM_RECORDS") or os.environ.get("SEAM_DATA") or ROOT / "data")
AUDIT = Path(os.environ.get("SEAM_AUDIT", ROOT / "runs" / "audit.jsonl"))
STATE = Path(os.environ.get("SEAM_STATE", ROOT / "runs" / "state.json"))


def _llms():
    if os.environ.get("SEAM_LLM", "on").lower() == "off":
        return None, None
    from .providers import default_llm
    llm = default_llm()                     # live model + cache with a key, cache-only without
    extract = llm if os.environ.get("SEAM_LLM_EXTRACT", "off").lower() == "on" else None
    return llm, extract


LLM, EXTRACT_LLM = _llms()
app = FastAPI(title="Compliance seam detector")
lock = threading.Lock()          # one writer at a time: Streamlit reruns can fire overlapping requests
engine = Engine.open(SOURCE, AUDIT, STATE, llm=LLM, extract_llm=EXTRACT_LLM)


class DraftDecision(BaseModel):
    signer_name: str
    signer_role: str
    reason: str
    params: dict[str, Any] | None = None


class FileEvent(BaseModel):
    event_id: str = "custom"
    date: str | None = None
    description: str = ""
    changes: list[dict[str, Any]]


def _guard(fn):
    with lock:
        try:
            return fn()
        except GovernanceError as exc:
            raise HTTPException(409, str(exc))
        except (ValidationError, ValueError, KeyError, EventError) as exc:
            raise HTTPException(422, str(exc))


@app.get("/health")
def health():
    return {"ok": True, "service": "seam-detector", "source": str(SOURCE), "seams": len(engine.seams),
            "llm": "live" if (LLM and LLM.provider) else "cache-only" if LLM else "off"}


@app.get("/passport")
def passport():
    with lock:
        return engine.passport()


@app.post("/run")
def run():
    def _do():
        global engine
        fresh = Engine(SOURCE, AUDIT, STATE, llm=LLM, extract_llm=EXTRACT_LLM)   # bad source -> 422, old engine kept
        engine = fresh
        return engine.run()
    return _guard(_do)


@app.get("/events/stream")
def stream():
    with lock:
        return engine.stream()


@app.post("/events/stream/{event_id}")
def stream_event(event_id: str):
    return _guard(lambda: engine.apply_stream_event(event_id))


@app.get("/scenarios")
def scenarios():
    with lock:
        return engine.scenarios()


@app.post("/scenarios/{name}")
def scenario(name: str):
    return _guard(lambda: engine.apply_scenario(name))


@app.post("/events/custom")
def custom_event(ev: FileEvent):
    return _guard(lambda: engine.apply_dataset_event(ev.model_dump(), actor="custom"))


class LiveField(BaseModel):
    file: str
    key: dict[str, str] = {}
    field: str
    value: Any
    description: str = ""


class LiveQuestion(BaseModel):
    question: str


class LiveEvent(BaseModel):
    event: dict[str, Any]


class LiveApply(BaseModel):
    event: dict[str, Any]
    confirmed_by: str
    reason: str = ""


class AuditQuestion(BaseModel):
    question: str


@app.get("/sources")
def sources():
    with lock:
        return engine.sources()


class UploadFile(BaseModel):
    dept: str
    name: str
    content_b64: str
    actor: str = "ui"


@app.post("/sources/upload")
def source_upload(body: UploadFile):
    return _guard(lambda: engine.add_upload(body.dept, body.name, base64.b64decode(body.content_b64), body.actor))


@app.get("/sources/content")
def source_content(path: str):
    return _guard(lambda: engine.source_content(path))


@app.post("/audit/ask")
def audit_ask(body: AuditQuestion):
    from .audit import ask
    return _guard(lambda: ask(engine, body.question))


@app.get("/audit/scope")
def audit_scope(domains: str = "HR,Finance,Legal"):
    from .audit import scoped
    with lock:
        return scoped(engine.passport(), [d.strip() for d in domains.split(",")])


@app.get("/live/editable")
def live_editable():
    return _guard(engine.editable)


@app.post("/live/field")
def live_field(body: LiveField):
    from .whatif import field_change

    def _do():
        engine._need_dataset()
        ev = field_change(engine.dataset, body.file, body.key, body.field, body.value, body.description)
        return engine.simulate(ev)
    return _guard(_do)


@app.post("/live/propose")
def live_propose(body: LiveQuestion):
    return _guard(lambda: engine.propose_what_if(body.question))


@app.post("/live/simulate")
def live_simulate(body: LiveEvent):
    return _guard(lambda: engine.simulate(body.event))


@app.post("/live/apply")
def live_apply(body: LiveApply):
    return _guard(lambda: engine.apply_live(body.event, body.confirmed_by, body.reason))


@app.post("/events")
def events(ev: Event):
    if engine.dataset is not None:
        raise HTTPException(409, "typed events are for fixtures mode; use /events/stream, /scenarios or /events/custom")
    return _guard(lambda: engine.apply_event(ev))


@app.post("/signoffs")
def signoffs(s: SignOff):
    return _guard(lambda: engine.sign(s))


def _decide(draft_id: str, body: DraftDecision, approve: bool):
    s = SignOff(decision="waive", signer_name=body.signer_name, signer_role=body.signer_role,
                reason=body.reason)   # reuses the name/role/reason validation
    return engine.decide_draft(draft_id, approve, s, body.params)


@app.post("/drafts/{draft_id}/approve")
def approve(draft_id: str, body: DraftDecision):
    return _guard(lambda: _decide(draft_id, body, True))


@app.post("/drafts/{draft_id}/reject")
def reject(draft_id: str, body: DraftDecision):
    return _guard(lambda: _decide(draft_id, body, False))


@app.get("/history")
def history():
    with lock:
        return engine.history


@app.get("/audit")
def audit():
    with lock:
        return {"verify": engine.audit.verify(), "entries": engine.audit.entries()}


@app.get("/report", response_class=HTMLResponse)
def report(download: bool = False):
    with lock:
        page = render_report(engine.passport(), {"verify": engine.audit.verify(), "entries": engine.audit.entries()})
    headers = {"Content-Disposition": 'attachment; filename="compliance-audit-report.html"'} if download else {}
    return HTMLResponse(page, headers=headers)


@app.post("/agent/attempt/{action}")
def agent_attempt(action: str):
    with lock:
        try:
            return {"action": action, "result": engine.agent_attempt(action)}
        except GovernanceError as exc:
            raise HTTPException(403, str(exc))

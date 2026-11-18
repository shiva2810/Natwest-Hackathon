"""API (component X.2). Run: .venv/bin/uvicorn seam.api:app --port 8765

Endpoints (the Person 2 <-> Person 3 contract):
  GET  /health
  GET  /passport                    current passport (includes pending drafts and people for pickers)
  POST /run                         reload records.json and start fresh (also the demo reset)
  POST /events                      {"type": ..., "data": {...}} -> {"diff", "passport"}
  POST /signoffs                    {"decision": "go|no_go|waive", "signer_name", "signer_role", "reason", "seam_id"?}
  POST /drafts/{id}/approve         {"signer_name", "signer_role", "reason", "params"?: {"owner_id": ...}}
  POST /drafts/{id}/reject          same body
  GET  /history                     before/after snapshots for the diff view
  GET  /audit                       entries + tamper check
  POST /agent/attempt/{action}      show the tier policy stopping an agent
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from .engine import Engine
from .governance import ROOT, GovernanceError, SignOff
from .pipeline import Event

RECORDS = Path(os.environ.get("SEAM_RECORDS", ROOT / "fixtures" / "records.json"))
AUDIT = Path(os.environ.get("SEAM_AUDIT", ROOT / "runs" / "audit.jsonl"))
STATE = Path(os.environ.get("SEAM_STATE", ROOT / "runs" / "state.json"))

app = FastAPI(title="Compliance seam detector")
lock = threading.Lock()          # one writer at a time: Streamlit reruns can fire overlapping requests
engine = Engine.open(RECORDS, AUDIT, STATE)


class DraftDecision(BaseModel):
    signer_name: str
    signer_role: str
    reason: str
    params: dict[str, Any] | None = None


def _guard(fn):
    with lock:
        try:
            return fn()
        except GovernanceError as exc:
            raise HTTPException(409, str(exc))
        except (ValidationError, ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc))


@app.get("/health")
def health():
    return {"ok": True, "service": "seam-detector", "records": str(RECORDS), "seams": len(engine.seams)}


@app.get("/passport")
def passport():
    with lock:
        return engine.passport()


@app.post("/run")
def run():
    def _do():
        global engine
        fresh = Engine(RECORDS, AUDIT, STATE, llm=engine.llm)   # bad records.json -> 422, old engine kept
        engine = fresh
        return engine.run()
    return _guard(_do)


@app.post("/events")
def events(ev: Event):
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


@app.post("/agent/attempt/{action}")
def agent_attempt(action: str):
    with lock:
        try:
            return {"action": action, "result": engine.agent_attempt(action)}
        except GovernanceError as exc:
            raise HTTPException(403, str(exc))

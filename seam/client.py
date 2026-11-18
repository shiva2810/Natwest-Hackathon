"""One import for the UI (Person 3): `from seam.client import SeamClient`.

Talks to the API at SEAM_API (default http://127.0.0.1:8765). If the API is unreachable it runs the
engine in-process on the same state file, so the demo still works with the backend down.
Every method returns plain dicts; errors raise SeamError with the server's message.
"""
from __future__ import annotations

import os
from typing import Any

import requests


class SeamError(Exception):
    pass


class SeamClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10):
        self.base = (base_url or os.environ.get("SEAM_API", "http://127.0.0.1:8765")).rstrip("/")
        self.timeout = timeout
        self._local = None
        try:
            h = requests.get(f"{self.base}/health", timeout=2)
            h.raise_for_status()
            if h.json().get("service") != "seam-detector":   # some other app owns the port
                raise requests.RequestException(f"{self.base} is not the seam detector")
            self.mode = "api"
        except (requests.RequestException, ValueError):
            self.mode = "in-process"

    # ---------- transport ----------

    def _engine(self):
        if self._local is None:
            from . import api  # builds the engine from the same env vars and state file
            self._local = api
        return self._local

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        if self.mode == "api":
            try:
                r = requests.request(method, f"{self.base}{path}", json=body, timeout=self.timeout)
            except requests.RequestException:
                self.mode = "in-process"          # backend died mid-demo: carry on locally
                return self._call(method, path, body)
            if r.status_code >= 400:
                raise SeamError(r.json().get("detail", r.text))
            return r.json()
        return self._local_call(method, path, body)

    def _local_call(self, method: str, path: str, body: dict | None) -> Any:
        from fastapi import HTTPException
        from .api import DraftDecision, Event, SignOff
        a = self._engine()
        parts = path.strip("/").split("/")
        try:
            if path == "/passport":
                return a.passport()
            if path == "/run":
                return a.run()
            if path == "/events":
                return a.events(Event(**body))
            if path == "/signoffs":
                return a.signoffs(SignOff(**body))
            if parts[0] == "drafts":
                fn = a.approve if parts[2] == "approve" else a.reject
                return fn(parts[1], DraftDecision(**body))
            if path == "/history":
                return a.history()
            if path == "/audit":
                return a.audit()
            if parts[0] == "agent":
                return a.agent_attempt(parts[2])
        except HTTPException as exc:
            raise SeamError(exc.detail)
        except ValueError as exc:                 # pydantic validation of the request body
            raise SeamError(str(exc))
        raise SeamError(f"no local route for {method} {path}")

    # ---------- API ----------

    def passport(self) -> dict:
        return self._call("GET", "/passport")

    def reset(self) -> dict:
        return self._call("POST", "/run")

    def event(self, type: str, **data) -> dict:
        return self._call("POST", "/events", {"type": type, "data": data, "actor": "manager-ui"})

    def sign(self, decision: str, signer_name: str, signer_role: str, reason: str,
             seam_id: str | None = None) -> dict:
        return self._call("POST", "/signoffs", {"decision": decision, "signer_name": signer_name,
                                                 "signer_role": signer_role, "reason": reason,
                                                 "seam_id": seam_id})

    def decide_draft(self, draft_id: str, approve: bool, signer_name: str, signer_role: str,
                     reason: str, **params) -> dict:
        verb = "approve" if approve else "reject"
        return self._call("POST", f"/drafts/{draft_id}/{verb}", {
            "signer_name": signer_name, "signer_role": signer_role, "reason": reason, "params": params})

    def history(self) -> list:
        return self._call("GET", "/history")

    def audit(self) -> dict:
        return self._call("GET", "/audit")

    def agent_attempt(self, action: str) -> dict:
        return self._call("POST", f"/agent/attempt/{action}")

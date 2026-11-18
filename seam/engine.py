"""Engine: owns state, runs the LangGraph pipeline, enforces governance, builds passport.json.

State (bundle after events, seams, waivers, sign-off, drafts, history) is saved to runs/state.json
after every change, so an API restart mid-demo loses nothing. If records.json changes on disk
(Person 1 publishes new data), the saved state is discarded and a fresh run happens.

Person 3 owns the passport UI and may refine the roll-up (6.1); the shape of `passport()` is the
Person 2 -> Person 3 handoff, so change keys together.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Literal

from .governance import ROOT, AuditLog, GovernanceError, SignOff, TierPolicy, now
from .pipeline import Draft, Event, make_pipeline
from .rules import RULES_VERSION, Seam
from .schema import Bundle

Go = Literal["go", "conditional", "no_go"]
ORDER = {"go": 0, "conditional": 1, "no_go": 2}
STATE_VERSION = 1


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Engine:
    def __init__(self, records_path: Path, audit_path: Path | None = None,
                 state_path: Path | None = None, llm: Callable[[str], dict] | None = None):
        self.records_path = Path(records_path)
        self.bundle = Bundle.model_validate_json(self.records_path.read_text())  # raises on bad data
        self.policy = TierPolicy()
        self.audit = AuditLog(audit_path or ROOT / "runs" / "audit.jsonl")
        self.state_path = state_path or ROOT / "runs" / "state.json"
        self.llm = llm
        self.pipeline = make_pipeline(self.policy, llm)
        self.seams: dict[str, Seam] = {}
        self.drafts: dict[str, Draft] = {}
        self.signoff: dict[str, Any] = {"state": "pending"}
        self.last_verified: str | None = None
        self.history: list[dict[str, Any]] = []      # before/after snapshots for the diff view (6.4)

    # ---------- persistence ----------

    @classmethod
    def open(cls, records_path: Path, audit_path: Path | None = None, state_path: Path | None = None,
             llm: Callable[[str], dict] | None = None) -> "Engine":
        """Resume saved state if it belongs to this exact records.json, else start with a fresh run."""
        eng = cls(records_path, audit_path, state_path, llm)
        if eng.state_path.exists():
            try:
                saved = json.loads(eng.state_path.read_text())
                if saved.get("version") == STATE_VERSION and saved.get("records_sha") == _sha(eng.records_path):
                    eng._load(saved)
                    return eng
            except (ValueError, KeyError):
                pass  # corrupt state: fall through to a fresh run
        eng.run()
        return eng

    def _load(self, s: dict[str, Any]):
        self.bundle = Bundle.model_validate(s["bundle"])
        self.seams = {k: Seam.model_validate(v) for k, v in s["seams"].items()}
        self.drafts = {k: Draft.model_validate(v) for k, v in s["drafts"].items()}
        self.signoff, self.history, self.last_verified = s["signoff"], s["history"], s["last_verified"]

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "version": STATE_VERSION, "records_sha": _sha(self.records_path),
            "bundle": self.bundle.model_dump(mode="json"),
            "seams": {k: v.model_dump(mode="json") for k, v in self.seams.items()},
            "drafts": {k: v.model_dump(mode="json") for k, v in self.drafts.items()},
            "signoff": self.signoff, "history": self.history, "last_verified": self.last_verified,
        }, default=str))
        tmp.replace(self.state_path)   # atomic: a crash mid-write never leaves half a file

    # ---------- helpers ----------

    @property
    def product(self):
        return next(p for p in self.bundle.entities.products if p.id == self.bundle.scenario.product_id)

    def _log(self, kind: str, actor: str, data: dict[str, Any]):
        return self.audit.append(kind, actor, data, self.policy.version)

    def _merge_drafts(self, proposed: list[Draft]):
        for d in proposed:
            if d.id not in self.drafts or self.drafts[d.id].status == "obsolete":
                d.created_at = now()
                self.drafts[d.id] = d
        for d in self.drafts.values():   # seam closed or waived: its pending drafts no longer apply
            seam = self.seams.get(d.seam_id)
            if d.status == "pending" and (seam is None or seam.status == "waived"):
                d.status = "obsolete"

    # ---------- runs ----------

    def run(self) -> dict[str, Any]:
        out = self.pipeline.invoke({"bundle": self.bundle, "event": None})
        self.seams = {s.id: s for s in out["seams"]}
        self.drafts = {}
        self.signoff = {"state": "pending"}
        self.history = []
        self._merge_drafts(out["drafts"])
        self.last_verified = now()
        self._log("run", "agent", {"rules_version": RULES_VERSION, "records": len(self.bundle.records),
                                   "records_sha": _sha(self.records_path), "pipeline": out["trace"],
                                   "seams": sorted(self.seams), "drafts": sorted(self.drafts)})
        self.save()
        return self.passport()

    def apply_event(self, ev: Event, cause: str | None = None) -> dict[str, Any]:
        before = self.passport()
        work = self.bundle.model_copy(deep=True)            # only commit if the whole pipeline succeeds
        out = self.pipeline.invoke({"bundle": work, "event": ev})
        self.bundle, scope = work, out["scope"]

        kept = {sid: s for sid, s in self.seams.items() if not (scope & set(s.nodes))}
        fresh = {s.id: s for s in out["seams"]}
        for sid, s in fresh.items():               # carry a waiver over only if the facts are unchanged
            old = self.seams.get(sid)
            if old and old.status == "waived" and old.title == s.title:
                s.status, s.waiver = old.status, old.waiver
        self.seams = {**kept, **fresh}
        self._merge_drafts(out["drafts"])
        self.last_verified = now()

        before_ids, after_ids = {s["id"] for s in before["seams"]}, set(self.seams)
        diff = {"event": ev.model_dump(), "cause": cause, "rechecked_nodes": sorted(scope),
                "opened": sorted(after_ids - before_ids), "closed": sorted(before_ids - after_ids),
                "status_before": before["overall"], "status_after": None, "invalidated_signoff": None}
        if (diff["opened"] or diff["closed"]) and self.signoff["state"] in ("go", "no_go"):
            diff["invalidated_signoff"] = self.signoff
            self.signoff = {"state": "pending", "invalidated": self.signoff,
                            "reason": f"seams changed after event '{ev.type}'"}
        after = self.passport()
        diff["status_after"] = after["overall"]
        self.history.append({"at": now(), "before": before, "after": after, "diff": diff})
        self._log("event", ev.actor, {**diff, "pipeline": out["trace"]})
        self.save()
        return {"diff": diff, "passport": after}

    # ---------- sign-off (5.2) ----------

    def sign(self, s: SignOff) -> dict[str, Any]:
        action = "waive_seam" if s.decision == "waive" else "go_no_go"
        self.policy.enforce(action, "human")
        if s.decision == "waive":
            seam = self.seams.get(s.seam_id or "")
            if not seam:
                raise GovernanceError(f"unknown seam '{s.seam_id}'")
            seam.status = "waived"
            seam.waiver = {"by": s.signer_name, "role": s.signer_role, "reason": s.reason, "at": now()}
            self._merge_drafts([])
        elif s.decision == "go":
            blocking = [x.id for x in self.seams.values()
                        if x.status == "open" and x.severity in ("critical", "high")]
            if blocking:
                self._log("signoff_refused", s.signer_name, {"decision": "go", "blocking": blocking})
                raise GovernanceError(f"cannot sign go with open critical/high seams: {blocking}. "
                                      "Fix or waive them first.")
            self.signoff = {"state": "go", "by": s.signer_name, "role": s.signer_role,
                            "reason": s.reason, "at": now()}
        else:
            self.signoff = {"state": "no_go", "by": s.signer_name, "role": s.signer_role,
                            "reason": s.reason, "at": now()}
        self._log("signoff", s.signer_name, s.model_dump())
        self.save()
        return self.passport()

    # ---------- drafts (5.1 tier "draft": agent prepares, human approves) ----------

    def decide_draft(self, draft_id: str, approve: bool, s: SignOff,
                     params: dict[str, Any] | None = None) -> dict[str, Any]:
        d = self.drafts.get(draft_id)
        if d is None:
            raise GovernanceError(f"unknown draft '{draft_id}'")
        if d.status != "pending":
            raise GovernanceError(f"draft '{draft_id}' is {d.status}, not pending")
        self.policy.enforce(d.action, "human")
        d.params = {**d.params, **(params or {})}
        decision = {"approved": approve, "by": s.signer_name, "role": s.signer_role,
                    "reason": s.reason, "at": now()}
        result: dict[str, Any] = {}
        if approve and d.action == "reassign_owner":
            new_owner = d.params.get("owner_id")
            if not new_owner:
                raise GovernanceError("reassign_owner needs params.owner_id (the successor)")
            # execute as events so the re-check, diff and audit all happen; validate first, all or nothing
            if new_owner not in {p.id for p in self.bundle.entities.people}:
                raise GovernanceError(f"unknown person '{new_owner}'")
            for rid in d.params["record_ids"]:
                result = self.apply_event(Event(type="record_update", actor=s.signer_name,
                                                data={"record_id": rid, "owner_id": new_owner}),
                                          cause=draft_id)
        elif approve and d.action == "notify_owner":
            decision["delivery"] = "simulated (demo: no email is sent)"
        d.status = "approved" if approve else "rejected"
        d.decision = decision
        self._log("draft_" + d.status, s.signer_name, {"draft": d.model_dump(mode="json")})
        self.save()
        return {"draft": d.model_dump(mode="json"), "diff": result.get("diff"), "passport": self.passport()}

    def agent_attempt(self, action: str) -> str:
        """For the demo: show an agent being stopped by the tier policy."""
        try:
            return self.policy.enforce(action, "agent")
        except GovernanceError as exc:
            self._log("tier_denied", "agent", {"action": action, "error": str(exc)})
            raise

    # ---------- passport (handoff to Person 3) ----------

    def passport(self) -> dict[str, Any]:
        b, prod = self.bundle, self.product
        open_seams = [s for s in self.seams.values() if s.status == "open"]

        depts: dict[str, dict[str, Any]] = {}
        for name in sorted({"HR", "Finance", "Legal", "Product", *(d for s in self.seams.values() for d in s.departments)}):
            recs = [r for r in b.records if r.department == name]
            unmet = [r.id for r in recs if r.status == "unmet"]
            unknown = [r.id for r in recs if r.status == "unknown"]
            touching = [s for s in open_seams if name in s.departments]
            status: Go = "go"
            if unknown or touching:
                status = "conditional"
            if unmet or any(s.severity == "critical" for s in touching):
                status = "no_go"
            depts[name] = {"status": status, "records": len(recs), "unmet": unmet, "unknown": unknown,
                           "own_view": "no_go" if unmet else "conditional" if unknown else "go",
                           "open_seams": [s.id for s in touching]}

        overall = max((d["status"] for d in depts.values()), key=ORDER.get, default="go")
        people = {p.id: p.name for p in b.entities.people}
        horizon = b.scenario.as_of + timedelta(days=120)
        expiring = sorted(
            [{"what": f"{r.id}: {ev.source}", "expires_on": str(ev.expires_on)}
             for r in b.records for ev in r.evidence if ev.expires_on and ev.expires_on <= horizon]
            + [{"what": f"{p.name}: {t.course}", "expires_on": str(t.expires_on)}
               for p in b.entities.people for t in p.trainings if t.expires_on and t.expires_on <= horizon]
            + [{"what": f"{v.name}: due diligence", "expires_on": str(v.dd_expires_on)}
               for v in b.entities.vendors if v.dd_expires_on and v.dd_expires_on <= horizon],
            key=lambda x: x["expires_on"])

        return {
            "company": b.scenario.company,
            "product": {"id": prod.id, "name": prod.name, "version": prod.launch_version,
                        "launch_date": str(prod.launch_date)},
            "as_of": str(b.scenario.as_of),
            "overall": overall,
            "departments": depts,
            "seams": [{**s.model_dump(mode="json"), "fix_owner": people.get(s.fix_owner_id or "")}
                      for s in sorted(self.seams.values(), key=lambda s: (-s.score, s.id))],
            "drafts": [d.model_dump(mode="json") for d in self.drafts.values() if d.status == "pending"],
            "people": [{"id": p.id, "name": p.name, "role": p.role} for p in b.entities.people],
            "signoff": self.signoff,
            "evidence_expiring": expiring,
            "policy_versions": {"rules": RULES_VERSION, "tiers": self.policy.version},
            "last_verified": self.last_verified,
            "audit": self.audit.verify(),
            "disclaimer": "Evidence-backed review on synthetic data, not a compliance certificate.",
        }

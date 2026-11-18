"""Engine: owns state, runs the LangGraph pipeline, enforces governance, builds passport.json.

Two sources:
  - a data directory (the real dataset, data/): extract -> check -> detect. Events are file-level
    changes (Person 1's event stream, or custom what-if scenarios in the same format) applied to the
    raw files, then re-extracted and selectively re-checked.
  - a records.json file (fixtures): typed events mutate the bundle directly.

State is saved to runs/state.json after every change, so an API restart mid-demo loses nothing.
If the source changes on disk, saved state is discarded and a fresh run happens.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import timedelta
from pathlib import Path, PurePath
from typing import Any, Callable, Literal

from .governance import ROOT, AuditLog, GovernanceError, SignOff, TierPolicy, now
from .graph import build_graph
from .pipeline import Draft, Event, make_pipeline
from .rules import RULES_VERSION, Seam, detect
from .schema import Bundle
from .scoring import rank
from .sources import Dataset, EventError, apply_event as apply_file_event, load_dataset

Go = Literal["go", "conditional", "no_go"]
ORDER = {"go": 0, "conditional": 1, "no_go": 2}
RESULT = {"met": "passed", "unmet": "failed", "unknown": "needs_review"}   # auditor-facing wording
STATE_VERSION = 2
DOC_PATH_TO_PRODUCT = {"accountable_senior_manager", "product_owner", "data_flows", "changes",
                       "release_candidate", "approved_version", "change_control_request_filed"}


def source_sha(path: Path) -> str:
    h = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file() and "answer_key" not in p.parts) if path.is_dir() else [path]
    for f in files:
        h.update(str(f.relative_to(path) if path.is_dir() else f.name).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _upload_size(up: dict[str, Any]) -> tuple[int, str]:
    if up["kind"] == "table":
        return len(up["rows"]), "rows"
    if up["kind"] == "document":
        return len([p for p in up["text"].split("\n\n") if p.strip()]), "paragraphs"
    j = up["json"]
    return (len(j) if hasattr(j, "__len__") else 1), "fields"


class Engine:
    def __init__(self, source: Path, audit_path: Path | None = None, state_path: Path | None = None,
                 llm: Callable[[str], str] | None = None, extract_llm: Callable[[str], str] | None = None):
        self.source = Path(source)
        self.records_path = self.source            # kept for older callers
        self.llm, self.extract_llm = llm, extract_llm
        self.dataset: Dataset | None = None
        self.extraction_report: dict[str, Any] = {}
        if self.source.is_dir():
            self.dataset = load_dataset(self.source)
            self.bundle = self._extract(self.dataset)
        else:
            self.bundle = Bundle.model_validate_json(self.source.read_text())  # raises on bad data
        self.policy = TierPolicy()
        self.audit = AuditLog(audit_path or ROOT / "runs" / "audit.jsonl")
        self.state_path = state_path or ROOT / "runs" / "state.json"
        self.pipeline = make_pipeline(self.policy, llm)
        self.seams: dict[str, Seam] = {}
        self.drafts: dict[str, Draft] = {}
        self.signoff: dict[str, Any] = {"state": "pending"}
        self.last_verified: str | None = None
        self.dept_summary: dict[str, Any] = {}
        self.history: list[dict[str, Any]] = []      # before/after snapshots for the diff view (6.4)

    def _extract(self, ds: Dataset) -> Bundle:
        from .extract import build_bundle
        bundle, self.extraction_report = build_bundle(ds, llm=self.extract_llm)
        return bundle

    # ---------- persistence ----------

    @classmethod
    def open(cls, source: Path, audit_path: Path | None = None, state_path: Path | None = None,
             llm=None, extract_llm=None) -> "Engine":
        """Resume saved state if it belongs to this exact source, else start with a fresh run."""
        eng = cls(source, audit_path, state_path, llm, extract_llm)
        if eng.state_path.exists():
            try:
                saved = json.loads(eng.state_path.read_text())
                if saved.get("version") == STATE_VERSION and saved.get("source_sha") == source_sha(eng.source):
                    eng._load(saved)
                    return eng
            except (ValueError, KeyError):
                pass  # corrupt state: fall through to a fresh run
        eng.run()
        return eng

    def _load(self, s: dict[str, Any]):
        self.bundle = Bundle.model_validate(s["bundle"])
        if self.dataset is not None and s.get("dataset"):
            d = s["dataset"]
            self.dataset.tables, self.dataset.docs = d["tables"], d["docs"]
            self.dataset.as_of, self.dataset.applied = d["as_of"], d["applied"]
            self.dataset.uploads = d.get("uploads", {})
        self.seams = {k: Seam.model_validate(v) for k, v in s["seams"].items()}
        self.drafts = {k: Draft.model_validate(v) for k, v in s["drafts"].items()}
        self.signoff, self.history, self.last_verified = s["signoff"], s["history"], s["last_verified"]
        self.dept_summary = s.get("dept_summary", {})

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        ds = self.dataset
        tmp.write_text(json.dumps({
            "version": STATE_VERSION, "source_sha": source_sha(self.source),
            "bundle": self.bundle.model_dump(mode="json"),
            "dataset": {"tables": ds.tables, "docs": ds.docs, "as_of": ds.as_of, "applied": ds.applied,
                        "uploads": ds.uploads} if ds else None,
            "seams": {k: v.model_dump(mode="json") for k, v in self.seams.items()},
            "drafts": {k: v.model_dump(mode="json") for k, v in self.drafts.items()},
            "signoff": self.signoff, "history": self.history, "last_verified": self.last_verified,
            "dept_summary": self.dept_summary,
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
        if self.dataset is not None:                      # fresh run = original files, no events
            self.dataset = load_dataset(self.source)
            self.bundle = self._extract(self.dataset)
        out = self.pipeline.invoke({"bundle": self.bundle, "event": None})
        self.seams = {s.id: s for s in out["seams"]}
        self.drafts, self.signoff, self.history = {}, {"state": "pending"}, []
        self.dept_summary = out.get("dept_summary", {})
        self._merge_drafts(out["drafts"])
        self.last_verified = now()
        self._log("run", "agent", {"rules_version": RULES_VERSION, "records": len(self.bundle.records),
                                   "source_sha": source_sha(self.source), "pipeline": out["trace"],
                                   "departments": self.dept_summary,
                                   "seams": sorted(self.seams), "drafts": sorted(self.drafts)})
        self.save()
        return self.passport()

    def _commit(self, out: dict, before: dict, ev_desc: dict, actor: str, cause: str | None) -> dict[str, Any]:
        """Merge a selective re-check into state, verify it against a full re-check, log, save."""
        scope = out["scope"]
        kept = {sid: s for sid, s in self.seams.items() if not (scope & set(s.nodes))}
        fresh = {s.id: s for s in out["seams"]}
        for sid, s in fresh.items():               # carry a waiver over only if the facts are unchanged
            old = self.seams.get(sid)
            if old and old.status == "waived" and old.title == s.title:
                s.status, s.waiver = old.status, old.waiver
        merged = {**kept, **fresh}

        # safety net: the selective result must equal a full re-check (rules are cheap and deterministic)
        full = {s.id: s.title for s in detect(build_graph(self.bundle), self.bundle)}
        selective_ok = full == {sid: s.title for sid, s in merged.items()}
        if not selective_ok:
            redo = self.pipeline.invoke({"bundle": self.bundle, "event": None})
            merged = {s.id: s for s in redo["seams"]}
        ranked = rank(list(merged.values()), self.bundle.scenario.as_of, self.product.launch_date)  # as_of may move
        self.seams = {s.id: s for s in ranked}
        self.dept_summary = out.get("dept_summary", self.dept_summary)
        self._merge_drafts(out["drafts"])
        self.last_verified = now()

        before_ids, after_ids = {s["id"] for s in before["seams"]}, set(self.seams)
        before_titles = {s["id"]: s["title"] for s in before["seams"]}
        diff = {"event": ev_desc, "cause": cause, "rechecked_nodes": sorted(scope),
                "selective_matches_full": selective_ok,
                "opened": sorted(after_ids - before_ids), "closed": sorted(before_ids - after_ids),
                "changed": sorted(sid for sid in after_ids & before_ids if self.seams[sid].title != before_titles[sid]),
                "status_before": before["overall"], "status_after": None, "invalidated_signoff": None,
                "departments_before": {k: v["own_view"] for k, v in before["departments"].items()}}
        if (diff["opened"] or diff["closed"] or diff["changed"]) and self.signoff["state"] in ("go", "no_go"):
            diff["invalidated_signoff"] = self.signoff
            self.signoff = {"state": "pending", "invalidated": self.signoff,
                            "reason": f"seams changed after event '{ev_desc.get('id') or ev_desc.get('type')}'"}
        after = self.passport()
        diff["status_after"] = after["overall"]
        diff["departments_after"] = {k: v["own_view"] for k, v in after["departments"].items()}
        self.history.append({"at": now(), "before": before, "after": after, "diff": diff})
        self._log("event", actor, {**diff, "pipeline": out["trace"]})
        self.save()
        return {"diff": diff, "passport": after}

    def apply_event(self, ev: Event, cause: str | None = None) -> dict[str, Any]:
        """Typed event (records mode, and owner reassignment from drafts)."""
        before = self.passport()
        work = self.bundle.model_copy(deep=True)            # only commit if the whole pipeline succeeds
        out = self.pipeline.invoke({"bundle": work, "event": ev})
        self.bundle = work
        return self._commit(out, before, {"type": ev.type, "data": ev.data}, ev.actor, cause)

    # ---------- dataset events (Person 1's stream and what-if scenarios) ----------

    def stream(self) -> list[dict[str, Any]]:
        if self.dataset is None:
            return []
        return [{"event_id": e["event_id"], "date": e.get("date"), "description": e.get("description"),
                 "applied": e["event_id"] in self.dataset.applied} for e in self.dataset.events]

    def apply_dataset_event(self, event: dict[str, Any], actor: str = "event-stream") -> dict[str, Any]:
        if self.dataset is None:
            raise GovernanceError("dataset events need the engine to run on a data directory")
        eid = event.get("event_id", "custom")
        if eid in self.dataset.applied:
            raise GovernanceError(f"event {eid} is already applied; POST /run to reset")
        before = self.passport()
        g_before = build_graph(self.bundle)
        work = self.dataset.copy()
        touched = apply_file_event(work, event)              # EventError on a bad change: nothing applied
        new_bundle = self._extract(work)
        g_after = build_graph(new_bundle)
        changed = {t for t in touched if t in g_before or t in g_after}
        if any(t in DOC_PATH_TO_PRODUCT for t in touched):
            changed.add(new_bundle.scenario.product_id)
        out = self.pipeline.invoke({"bundle": new_bundle, "event": None, "changed": changed, "g_before": g_before})
        self.dataset, self.bundle = work, new_bundle
        desc = {"id": eid, "date": event.get("date"), "description": event.get("description"),
                "files": sorted({c["file"] for c in event["changes"]})}
        return self._commit(out, before, desc, actor, None)

    SCENARIOS = ROOT / "scenarios"

    def scenarios(self) -> list[dict[str, Any]]:
        applied = set(self.dataset.applied) if self.dataset else set()
        out = []
        for f in sorted(self.SCENARIOS.glob("*.json")):
            ev = json.loads(f.read_text())
            out.append({"name": f.stem, "event_id": ev.get("event_id"), "description": ev.get("description"),
                        "applied": ev.get("event_id") in applied})
        return out

    def apply_scenario(self, name: str) -> dict[str, Any]:
        f = self.SCENARIOS / f"{name}.json"
        if not f.is_file() or f.parent != self.SCENARIOS:
            raise GovernanceError(f"unknown scenario '{name}'")
        return self.apply_dataset_event(json.loads(f.read_text()), actor=f"scenario:{name}")

    # ---------- live what-if checks ----------

    def _need_dataset(self):
        if self.dataset is None:
            raise GovernanceError("live what-if checks need the engine to run on a data directory")

    def simulate(self, event: dict[str, Any]) -> dict[str, Any]:
        """Predict what an event would do. Validates it, changes nothing, logs nothing."""
        from .checkers import run_checks
        from .extract import build_bundle
        from .whatif import validate
        self._need_dataset()
        preview = validate(self.dataset, event)
        work = self.dataset.copy()
        apply_file_event(work, event)
        nb, _ = build_bundle(work)                       # deterministic and fast: no model calls
        run_checks(nb)
        launch = next(p for p in nb.entities.products if p.id == nb.scenario.product_id).launch_date
        predicted = {s.id: s for s in rank(detect(build_graph(nb), nb), nb.scenario.as_of, launch)}
        for sid, sm in predicted.items():                # a waiver survives only if the facts are unchanged
            old = self.seams.get(sid)
            if old and old.status == "waived" and old.title == sm.title:
                sm.status, sm.waiver = old.status, old.waiver
        before = self.passport()
        saved = (self.bundle, self.seams)
        self.bundle, self.seams = nb, predicted
        try:
            after = self.passport()
        finally:
            self.bundle, self.seams = saved
        b_ids = {x["id"]: x["title"] for x in before["seams"]}
        a_ids = {x["id"]: x["title"] for x in after["seams"]}
        return {
            "event": event, "preview": preview,
            "opened": sorted(set(a_ids) - set(b_ids)), "closed": sorted(set(b_ids) - set(a_ids)),
            "changed": sorted(k for k in set(a_ids) & set(b_ids) if a_ids[k] != b_ids[k]),
            "status_before": before["overall"], "status_after": after["overall"],
            "departments": {k: {"before": before["departments"][k]["status"], "after": v["status"]}
                            for k, v in after["departments"].items() if k in before["departments"]},
            "seams_after": [{"id": x["id"], "title": x["title"], "severity": x["severity"], "status": x["status"]}
                            for x in after["seams"]],
            "signoff_would_reset": bool(set(a_ids) ^ set(b_ids) or any(a_ids[k] != b_ids[k] for k in set(a_ids) & set(b_ids)))
                                   and self.signoff["state"] in ("go", "no_go"),
        }

    def propose_what_if(self, question: str) -> dict[str, Any]:
        """Claude drafts the data change for a plain-English what-if; returns it with a simulation.
        Draft tier: nothing is applied until a named human confirms with apply_live."""
        from .whatif import WhatIfError, propose
        self._need_dataset()
        if self.policy.enforce("propose_what_if", "agent") != "draft":
            raise GovernanceError("policy does not allow agents to draft what-ifs")
        from .llm import OfflineMiss
        if self.llm is None:
            raise WhatIfError("no language model configured: use the form editor, or add an API key to .env (ANTHROPIC_API_KEY or OPENAI_API_KEY)")
        try:
            event = propose(question, self.dataset, self.llm)
        except OfflineMiss:
            raise WhatIfError("offline and this question was not asked before: use the form editor, "
                              "or add an API key to .env (ANTHROPIC_API_KEY or OPENAI_API_KEY)") from None
        sim = self.simulate(event)
        self._log("what_if_proposed", "agent", {"question": question, "event": event,
                                                "predicted": {k: sim[k] for k in ("opened", "closed", "changed",
                                                                                  "status_before", "status_after")}})
        return sim

    def apply_live(self, event: dict[str, Any], confirmed_by: str, reason: str = "") -> dict[str, Any]:
        """Apply a what-if for real. Needs a named human (proposals from a model are draft tier)."""
        from .whatif import validate
        self._need_dataset()
        if len((confirmed_by or "").strip()) < 3:
            raise GovernanceError("a live change must be confirmed by a named person")
        validate(self.dataset, event)
        n = 1 + sum(1 for a in self.dataset.applied if a.startswith("LIVE-"))
        ev = {**event, "event_id": f"LIVE-{n}", "date": event.get("date") or self.dataset.as_of}
        if reason:
            ev["description"] = f"{ev.get('description', '')} (confirmed by {confirmed_by}: {reason})"
        return self.apply_dataset_event(ev, actor=confirmed_by.strip())

    # ---------- data & documents (left panel) ----------

    DEPT_NAMES = {"hr": "HR", "finance": "Finance", "legal": "Legal", "product": "Product"}

    def sources(self) -> dict[str, Any]:
        """Every file the review is built from, grouped by department, with live sizes (events change them)."""
        ds = self.dataset
        if ds is None:
            return {"path": str(self.source), "kind": "records.json", "as_of": str(self.bundle.scenario.as_of),
                    "applied_events": 0, "departments": []}
        groups: dict[str, list[dict[str, Any]]] = {}

        def add(file: str, kind: str, size: int, unit: str):
            key, _, name = file.partition("/")
            groups.setdefault(key, []).append({"file": file, "name": name, "kind": kind, "size": size, "unit": unit})

        for f, rows in ds.tables.items():
            add(f, "table", len(rows), "rows")
        for f, text in ds.texts.items():
            add(f, "document", len([p for p in text.split("\n\n") if p.strip()]), "paragraphs")
        for f, doc in ds.docs.items():
            add(f, "record", len(doc) if hasattr(doc, "__len__") else 1, "fields")
        for f, up in ds.uploads.items():
            add(f, up["kind"], *_upload_size(up))
            groups[f.partition("/")[0]][-1]["uploaded"] = True
        return {"path": str(self.source), "kind": "folder", "as_of": ds.as_of, "applied_events": len(ds.applied),
                "departments": [{"key": k, "name": self.DEPT_NAMES.get(k, k.title()),
                                 "files": sorted(groups[k], key=lambda x: (x["kind"] != "document", x["name"]))}
                                for k in ("hr", "finance", "legal", "product") if k in groups]}

    def source_content(self, file: str, limit: int = 200) -> dict[str, Any]:
        """The live content of one source file (so a preview shows applied events too)."""
        ds = self.dataset
        if ds is not None and file in ds.tables:
            return {"file": file, "kind": "table", "total": len(ds.tables[file]), "rows": ds.tables[file][:limit]}
        if ds is not None and file in ds.texts:
            return {"file": file, "kind": "document", "text": ds.texts[file]}
        if ds is not None and file in ds.docs:
            return {"file": file, "kind": "record", "json": ds.docs[file]}
        if ds is not None and file in ds.uploads:
            up = ds.uploads[file]
            if up["kind"] == "table":
                return {"file": file, "kind": "table", "total": len(up["rows"]), "rows": up["rows"][:limit]}
            return {"file": file, "kind": up["kind"], **{k: up[k] for k in ("text", "json") if k in up}}
        raise GovernanceError(f"unknown source file '{file}'")

    UPLOAD_EXT = (".csv", ".md", ".txt", ".json")
    UPLOAD_MAX = 1_000_000

    def add_upload(self, dept: str, name: str, data: bytes, actor: str = "ui") -> dict[str, Any]:
        """Add a reference file to one department's data. It is stored in the engine state, shows in the data
        panel and is searchable in Q&A, but the compliance checks never read it (they only read the known files)."""
        self._need_dataset()
        dept = (dept or "").lower()
        if dept not in self.DEPT_NAMES:
            raise ValueError(f"unknown department '{dept}'")
        name = PurePath((name or "").replace("\\", "/")).name
        if not name or not name.lower().endswith(self.UPLOAD_EXT):
            raise ValueError(f"'{name}': only {', '.join(self.UPLOAD_EXT)} files can be added")
        if len(data) > self.UPLOAD_MAX:
            raise ValueError(f"'{name}' is larger than {self.UPLOAD_MAX // 1_000_000} MB")
        key, ds = f"{dept}/{name}", self.dataset
        if key in ds.tables or key in ds.texts or key in ds.docs:
            raise ValueError(f"'{key}' is one of the review's own files and cannot be replaced; rename the upload")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError(f"'{name}' is not UTF-8 text") from None
        if not text.strip():
            raise ValueError(f"'{name}' is empty")
        up: dict[str, Any] = {"dept": dept, "by": actor, "at": now()}
        if name.lower().endswith(".csv"):
            rows = [dict(r) for r in csv.DictReader(io.StringIO(text))]
            if not rows:
                raise ValueError(f"'{name}' has no data rows")
            up |= {"kind": "table", "rows": rows}
        elif name.lower().endswith(".json"):
            try:
                up |= {"kind": "record", "json": json.loads(text)}
            except ValueError as exc:
                raise ValueError(f"'{name}' is not valid JSON: {exc}") from None
        else:
            up |= {"kind": "document", "text": text}
        ds.uploads[key] = up
        self._log("file_added", actor, {"file": key, "kind": up["kind"], "bytes": len(data)})
        self.save()
        return {"file": key, "kind": up["kind"], "size": _upload_size(up)[0], "unit": _upload_size(up)[1]}

    def editable(self) -> dict[str, Any]:
        from .whatif import editable
        self._need_dataset()
        return editable(self.dataset)

    def apply_stream_event(self, event_id: str) -> dict[str, Any]:
        ev = next((e for e in (self.dataset.events if self.dataset else []) if e["event_id"] == event_id), None)
        if ev is None:
            raise GovernanceError(f"unknown event '{event_id}'")
        return self.apply_dataset_event(ev)

    # ---------- sign-off (5.2) ----------

    def blocking(self) -> list[str]:
        return [x.id for x in self.seams.values()
                if x.status == "open" and (x.blocks_launch or x.severity == "critical")]

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
            blocking = self.blocking()
            if blocking:
                self._log("signoff_refused", s.signer_name, {"decision": "go", "blocking": blocking})
                raise GovernanceError(f"cannot sign go with open launch-blocking seams: {blocking}. "
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
            if new_owner not in {p.id for p in self.bundle.entities.people}:
                raise GovernanceError(f"unknown person '{new_owner}'")
            if self.dataset is not None:   # real data: reassign in Legal's register file, like EV-04 does
                result = self.apply_dataset_event({
                    "event_id": f"draft:{draft_id}", "date": self.dataset.as_of,
                    "description": f"Approved draft: reassign obligations to {new_owner}",
                    "changes": [{"file": "legal/obligations_register.csv", "op": "update",
                                 "match": {"obligation_id": rid}, "set": {"owner_id": new_owner}}
                                for rid in d.params["record_ids"]]}, actor=s.signer_name)
            else:
                for rid in d.params["record_ids"]:
                    result = self.apply_event(Event(type="record_update", actor=s.signer_name,
                                                    data={"record_id": rid, "owner_id": new_owner}), cause=draft_id)
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
            own: Go = "conditional" if (unmet or unknown) else "go"   # in-department findings: fix, not block
            status: Go = own
            if touching:
                status = "conditional"
            if any(s.blocks_launch or s.severity == "critical" for s in touching):
                status = "no_go"
            depts[name] = {
                "status": status, "own_view": own, "records": len(recs), "unmet": unmet, "unknown": unknown,
                "open_seams": [s.id for s in touching],
                "results": {k: sum(1 for r in recs if RESULT[r.status] == k) for k in ("passed", "failed", "needs_review")},
                "findings": [{"record": r.id, "status": r.status, "result": RESULT[r.status],
                              "basis": r.attributes.get("check", {}).get("basis"),
                              "finding": r.attributes.get("check", {}).get("finding"),
                              "items": r.attributes.get("check", {}).get("items", [])}
                             for r in recs if r.status != "met"],
                "self_attested": [r.id for r in recs if r.attributes.get("check", {}).get("basis") == "self_attested"],
            }

        overall = max((d["status"] for d in depts.values()), key=ORDER.get, default="go")
        people = {p.id: p.name for p in b.entities.people}
        horizon = b.scenario.as_of + timedelta(days=120)
        expiring = sorted(
            [{"what": f"{r.id}: {ev.source}", "expires_on": str(ev.expires_on)}
             for r in b.records for ev in r.evidence if ev.expires_on and ev.expires_on <= horizon]
            + [{"what": f"{p.name}: {t.course}", "expires_on": str(t.expires_on)}
               for p in b.entities.people if p.active for t in p.trainings
               if t.expires_on and b.scenario.as_of <= t.expires_on <= horizon]
            + [{"what": f"{v.name}: due diligence", "expires_on": str(v.dd_expires_on)}
               for v in b.entities.vendors if v.dd_expires_on and v.dd_expires_on <= horizon]
            + [{"what": f"{c.id} {c.title}", "expires_on": str(c.end_date)}
               for c in b.entities.contracts if c.end_date and b.scenario.as_of <= c.end_date <= horizon],
            key=lambda x: x["expires_on"])

        return {
            "company": b.scenario.company,
            "source": "dataset" if self.dataset is not None else "records",
            "product": {"id": prod.id, "name": prod.name, "version": prod.launch_version,
                        "launch_date": str(prod.launch_date)},
            "as_of": str(b.scenario.as_of),
            "overall": overall,
            "blocking_seams": self.blocking(),
            "departments": depts,
            "seams": [{**s.model_dump(mode="json"), "fix_owner": people.get(s.fix_owner_id or "")}
                      for s in sorted(self.seams.values(), key=lambda s: (-s.score, s.id))],
            "drafts": [d.model_dump(mode="json") for d in self.drafts.values() if d.status == "pending"],
            "people": [{"id": p.id, "name": p.name, "role": p.role} for p in b.entities.people if p.active],
            "events": self.stream(),
            "scenarios": self.scenarios() if self.dataset is not None else [],
            "records": [{**r.model_dump(mode="json"), "owner": people.get(r.owner_id or "")}

                        for r in b.records],          # every check, so a report can show passes too
            "signoff": self.signoff,
            "evidence_expiring": expiring,
            "policy_versions": {"rules": RULES_VERSION, "tiers": self.policy.version},
            "extraction": {k: self.extraction_report.get(k) for k in ("records_by_department", "quote_check")}
                          if self.extraction_report else None,
            "last_verified": self.last_verified,
            "audit": self.audit.verify(),
            "disclaimer": "Evidence-backed review on synthetic data, not a compliance certificate.",
        }

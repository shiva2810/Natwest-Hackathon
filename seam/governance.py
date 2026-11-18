"""Governance (components 5.1-5.3): autonomy tiers, named sign-off, hash-chained audit log."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator

Tier = Literal["auto", "draft", "human"]
Actor = Literal["agent", "human"]

ROOT = Path(__file__).resolve().parent.parent
GENESIS = "0" * 64


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- 5.1 autonomy tiers ----------

class GovernanceError(Exception):
    pass


class TierPolicy:
    def __init__(self, path: Path = ROOT / "config" / "autonomy_tiers.json"):
        cfg = json.loads(path.read_text())
        self.version: str = cfg["policy_version"]
        self.actions: dict[str, Tier] = cfg["actions"]

    def tier(self, action: str) -> Tier:
        return self.actions.get(action, "human")   # unknown actions default to the safest tier

    def enforce(self, action: str, actor: Actor) -> Literal["execute", "draft"]:
        """What happens when `actor` tries `action`. Raises if not allowed."""
        t = self.tier(action)
        if actor == "human":
            return "execute"
        if t == "auto":
            return "execute"
        if t == "draft":
            return "draft"
        raise GovernanceError(f"'{action}' is tier '{t}': an agent may not perform it")


# ---------- 5.3 hash-chained audit log ----------

class AuditLog:
    """Append-only JSONL. Each entry's hash covers its content and the previous hash."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    @staticmethod
    def _hash(prev: str, body: dict[str, Any]) -> str:
        payload = prev + json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def entries(self) -> list[dict[str, Any]]:
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def append(self, kind: str, actor: str, data: dict[str, Any], policy_version: str) -> dict[str, Any]:
        entries = self.entries()
        prev = entries[-1]["hash"] if entries else GENESIS
        body = {"seq": len(entries), "at": now(), "kind": kind, "actor": actor,
                "policy_version": policy_version, "data": data, "prev_hash": prev}
        entry = {**body, "hash": self._hash(prev, body)}
        with self.path.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def verify(self) -> dict[str, Any]:
        prev = GENESIS
        entries = self.entries()
        for i, e in enumerate(entries):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev_hash") != prev or self._hash(prev, body) != e.get("hash"):
                return {"ok": False, "entries": len(entries), "broken_at": i}
            prev = e["hash"]
        return {"ok": True, "entries": len(entries), "broken_at": None, "head": prev}


# ---------- 5.2 named human sign-off ----------

class SignOff(BaseModel):
    decision: Literal["go", "no_go", "waive"]
    signer_name: str
    signer_role: str
    reason: str
    seam_id: str | None = None          # required for "waive"

    @field_validator("signer_name", "signer_role", "reason")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if len(v.strip()) < 3:
            raise ValueError("must be a real value, not blank")
        return v.strip()

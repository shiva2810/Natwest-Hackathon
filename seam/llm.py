"""LLM wrapper (X.1, minimal): provider-agnostic, disk cache, offline mode.

A provider is any function `prompt -> str`. Wrap it in `CachedLLM` and every response is stored
under cache/llm/<sha256>.json, keyed by the prompt. With no provider (offline), cached answers are
replayed and a cache miss raises `OfflineMiss`, so callers fall back to deterministic output.
Commit the cache directory to make the demo work with no network.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "llm"


class OfflineMiss(RuntimeError):
    pass


class CachedLLM:
    def __init__(self, provider: Callable[[str], str] | None = None, cache_dir: Path = CACHE_DIR,
                 model_tag: str = "default"):
        self.provider, self.cache_dir, self.model_tag = provider, Path(cache_dir), model_tag
        self.hits = self.misses = 0

    def _path(self, prompt: str) -> Path:
        key = hashlib.sha256(f"{self.model_tag}\n{prompt}".encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    def __call__(self, prompt: str) -> str:
        p = self._path(prompt)
        if p.exists():
            self.hits += 1
            return json.loads(p.read_text())["response"]
        if self.provider is None:
            raise OfflineMiss("no provider configured and no cached response for this prompt")
        self.misses += 1
        response = self.provider(prompt)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"model": self.model_tag, "prompt": prompt, "response": response}, indent=1))
        return response


def parse_json(text: str | dict | list) -> Any:
    """Accept a dict/list, raw JSON, or JSON inside a ```json fence or surrounded by prose."""
    if isinstance(text, (dict, list)):
        return text
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    body = m.group(1) if m else text
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start = min((i for i in (body.find("["), body.find("{")) if i >= 0), default=-1)
        if start < 0:
            raise
        end = max(body.rfind("]"), body.rfind("}"))
        return json.loads(body[start:end + 1])

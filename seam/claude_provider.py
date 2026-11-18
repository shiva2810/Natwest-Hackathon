"""Claude provider for the LLM wrapper: `prompt -> str`, via the official Anthropic SDK.

Reads ANTHROPIC_API_KEY from the environment or from .env at the repo root. Pair with CachedLLM so
every answer is cached and the demo also works offline:

    from seam.claude_provider import default_llm
    llm = default_llm()        # CachedLLM(Claude) if a key is set, else cache-only (offline)
"""
from __future__ import annotations

import os
from pathlib import Path

from .llm import CachedLLM

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("SEAM_MODEL", "claude-opus-5-5")


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader (KEY=value lines). Never overrides variables already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def has_key() -> bool:
    load_dotenv()
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key) and not key.startswith("paste-")


class ClaudeRefused(RuntimeError):
    pass


def claude_provider(model: str = MODEL, effort: str = "medium"):
    import anthropic  # imported lazily so offline runs need no SDK call

    load_dotenv()
    client = anthropic.Anthropic(timeout=120.0, max_retries=3)

    def call(prompt: str) -> str:
        resp = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],   # a safety decline re-runs on a fallback model
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            raise ClaudeRefused(f"model declined: {getattr(resp.stop_details, 'category', None)}")
        return "".join(b.text for b in resp.content if b.type == "text")

    return call


def default_llm() -> CachedLLM:
    """Live Claude (cached) when a key is configured, otherwise cache-only offline mode."""
    if has_key():
        return CachedLLM(claude_provider(), model_tag=MODEL)
    return CachedLLM(None, model_tag=MODEL)

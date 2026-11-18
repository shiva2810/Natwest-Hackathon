"""Pick the LLM provider from the environment: Anthropic (Claude), OpenAI, or any OpenAI-compatible API.

Set these in .env at the repo root (copy .env.example) or in the real environment:

    SEAM_LLM_PROVIDER   anthropic | openai | auto      (default auto: Anthropic if its key is set, else OpenAI)
    OPENAI_API_KEY      key for OpenAI, or for any OpenAI-compatible service
    OPENAI_BASE_URL     optional; default https://api.openai.com/v1  (OpenRouter, Groq, Azure, Ollama, vLLM ...)
    ANTHROPIC_API_KEY   key for Claude
    SEAM_MODEL          optional model name; default depends on the provider

Everything goes through CachedLLM, so answers are cached in cache/llm/ and the demo still runs offline.
The cache is keyed by provider and model, so Claude answers and OpenAI answers never get mixed up.
With no key at all the result is the same as before: cache-only (offline) mode.

    from seam.providers import default_llm
    llm = default_llm()
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from .claude_provider import load_dotenv
from .llm import CachedLLM

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4o"}
OPENAI_URL = "https://api.openai.com/v1"


def _real(key: str) -> bool:
    return bool(key) and not key.startswith("paste-")


def provider_name() -> str | None:
    """'anthropic', 'openai', or None when no usable key is configured (offline mode)."""
    load_dotenv()
    want = os.environ.get("SEAM_LLM_PROVIDER", "auto").strip().lower()
    if want not in ("auto", "anthropic", "openai"):
        raise ValueError(f"SEAM_LLM_PROVIDER must be anthropic, openai or auto, not '{want}'")
    have = {"anthropic": _real(os.environ.get("ANTHROPIC_API_KEY", "")),
            # a custom base URL (local server) may not need a key at all
            "openai": _real(os.environ.get("OPENAI_API_KEY", "")) or bool(os.environ.get("OPENAI_BASE_URL"))}
    if want != "auto":
        return want if have[want] else None
    return next((n for n in ("anthropic", "openai") if have[n]), None)


def model_name(provider: str | None = None) -> str:
    load_dotenv()
    return os.environ.get("SEAM_MODEL") or DEFAULT_MODELS[provider or provider_name() or "anthropic"]


def has_key() -> bool:
    return provider_name() is not None


def openai_provider(model: str):
    """`prompt -> str` over the chat-completions API. Plain `requests`, so no extra SDK is needed."""
    load_dotenv()
    base = os.environ.get("OPENAI_BASE_URL", OPENAI_URL).rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "")
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if _real(key) else {})}

    def call(prompt: str) -> str:
        body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        for attempt in range(4):
            r = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=120)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"OpenAI-compatible API error {r.status_code}: {r.text[:300]}")
            choice = r.json()["choices"][0]
            if choice["message"].get("refusal"):
                raise RuntimeError(f"model declined: {choice['message']['refusal']}")
            return choice["message"].get("content") or ""
        raise RuntimeError("OpenAI-compatible API kept failing")   # unreachable: the last attempt raises above

    return call


def default_llm() -> CachedLLM:
    """Live LLM (cached) when a key is configured, otherwise cache-only offline mode."""
    name = provider_name()
    if name == "openai":
        model = model_name("openai")
        return CachedLLM(openai_provider(model), model_tag=f"openai:{model}")
    if name == "anthropic":
        from .claude_provider import claude_provider
        model = model_name("anthropic")
        return CachedLLM(claude_provider(model), model_tag=model)   # tag unchanged: keeps the committed Claude cache valid
    return CachedLLM(None, model_tag=DEFAULT_MODELS["anthropic"])      # offline: replay the committed Claude cache

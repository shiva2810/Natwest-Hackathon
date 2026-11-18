"""Provider selection and the OpenAI-compatible call. No test touches the network."""
import pytest

from seam import providers
from seam.llm import CachedLLM, OfflineMiss

KEYS = ("SEAM_LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "SEAM_MODEL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(providers, "load_dotenv", lambda *a, **k: None)   # ignore a real .env on this machine


def test_no_key_is_offline():
    assert providers.provider_name() is None and not providers.has_key()
    llm = providers.default_llm()
    assert llm.provider is None and llm.model_tag == "claude-opus-5-5"     # replays the committed Claude cache


def test_placeholder_key_counts_as_no_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "paste-your-key-here")
    assert providers.provider_name() is None


def test_openai_key_selects_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert providers.provider_name() == "openai"
    llm = providers.default_llm()
    assert llm.model_tag == "openai:gpt-4o" and llm.provider is not None


def test_auto_prefers_anthropic_but_explicit_choice_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert providers.provider_name() == "anthropic"
    monkeypatch.setenv("SEAM_LLM_PROVIDER", "openai")
    assert providers.provider_name() == "openai"
    monkeypatch.delenv("OPENAI_API_KEY")
    assert providers.provider_name() is None            # asked for openai but no openai key: offline, not a silent switch


def test_bad_provider_name_is_rejected(monkeypatch):
    monkeypatch.setenv("SEAM_LLM_PROVIDER", "gemini")
    with pytest.raises(ValueError):
        providers.provider_name()


def test_custom_base_url_needs_no_key(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")     # e.g. a local Ollama
    assert providers.provider_name() == "openai"


def test_model_override(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SEAM_MODEL", "gpt-4.1-mini")
    assert providers.default_llm().model_tag == "openai:gpt-4.1-mini"


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.text = status, body or {}, str(body)

    def json(self):
        return self._body


def test_openai_call_shape_and_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1/")
    seen = []

    def fake_post(url, headers, json, timeout):
        seen.append((url, headers, json))
        return FakeResp(200, {"choices": [{"message": {"content": "hello"}}]})
    monkeypatch.setattr(providers.requests, "post", fake_post)
    llm = CachedLLM(providers.openai_provider("gpt-4o"), cache_dir=tmp_path, model_tag="openai:gpt-4o")
    assert llm("hi") == "hello" and llm("hi") == "hello"        # second call is served from the cache
    assert len(seen) == 1
    url, headers, body = seen[0]
    assert url == "https://example.test/v1/chat/completions" and headers["Authorization"] == "Bearer sk-test"
    assert body == {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
    other = CachedLLM(None, cache_dir=tmp_path, model_tag="claude-opus-5-5")
    with pytest.raises(OfflineMiss):                              # a different provider's cache is separate
        other("hi")


def test_openai_errors_surface(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(providers.requests, "post", lambda *a, **k: FakeResp(401, {"error": "bad key"}))
    with pytest.raises(RuntimeError, match="401"):
        providers.openai_provider("gpt-4o")("hi")


def test_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    replies = iter([FakeResp(429, {}), FakeResp(200, {"choices": [{"message": {"content": "ok"}}]})])
    monkeypatch.setattr(providers.requests, "post", lambda *a, **k: next(replies))
    assert providers.openai_provider("gpt-4o")("hi") == "ok"

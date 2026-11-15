import pytest
from langchain_core.runnables import RunnableLambda

import app.agent.model_factory as mf


class FakeModel:
    def __init__(self, fn):
        self.fn = fn

    def bind_tools(self, tools):
        return RunnableLambda(self.fn)


def _install(monkeypatch, models):
    monkeypatch.setattr(mf, "load_model_registry", lambda: [{"id": k} for k in models])
    monkeypatch.setattr(mf, "_build_chat_model", lambda target: models[target["id"]])


def _boom(_):
    raise RuntimeError("rate limited")


def test_failover_happens_at_call_time(monkeypatch):
    _install(monkeypatch, {"a": FakeModel(_boom), "b": FakeModel(lambda _: "from-b")})
    assert mf.get_llm_with_fallbacks([], None).invoke("x") == "from-b"


def test_requested_provider_is_tried_first(monkeypatch):
    _install(monkeypatch, {"a": FakeModel(lambda _: "from-a"), "b": FakeModel(lambda _: "from-b")})
    assert mf.get_llm_with_fallbacks([], "b").invoke("x") == "from-b"
    assert mf.get_llm_with_fallbacks([], None).invoke("x") == "from-a"


def test_unavailable_providers_are_skipped(monkeypatch):
    _install(monkeypatch, {"a": None, "b": FakeModel(lambda _: "from-b")})
    assert mf.get_llm_with_fallbacks([], None).invoke("x") == "from-b"


def test_no_usable_provider_is_an_error(monkeypatch):
    _install(monkeypatch, {"a": None})
    with pytest.raises(RuntimeError):
        mf.get_llm_with_fallbacks([], None)
    monkeypatch.setattr(mf, "load_model_registry", lambda: [])
    with pytest.raises(RuntimeError):
        mf.get_llm_with_fallbacks([], None)


def test_keys_rotate_round_robin(monkeypatch):
    monkeypatch.setattr(mf, "_PROVIDER_KEY_CYCLERS", {})
    assert [mf._get_next_key("p", ["k1", "k2"]) for _ in range(3)] == ["k1", "k2", "k1"]
    assert mf._get_next_key("empty", []) is None


def test_registry_expands_env_vars_and_comma_lists(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GEMINI_API_KEYS", "a, b")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    reg = {p["id"]: p for p in mf.load_model_registry()}
    assert reg["groq-cloud"]["resolved_keys"] == ["gsk_test"]
    assert reg["google-gemini"]["resolved_keys"] == ["a", "b"]
    # loading twice must not accumulate keys (the cached registry is never mutated)
    assert {p["id"]: p for p in mf.load_model_registry()}["groq-cloud"]["resolved_keys"] == ["gsk_test"]

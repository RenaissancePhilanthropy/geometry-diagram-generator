"""Public model options: Claude 5 models get a real output limit instead of langchain's 4096
fallback; GeometryConfig.model_options reaches every model a run builds; and
register_model_options() is the documented way to add per-model kwargs / extra_body."""
from __future__ import annotations

import pytest

from geometry_diagrams import GeometryConfig, register_model_options
from geometry_diagrams.config import resolve_config
from geometry_diagrams.strategies import llm
from geometry_diagrams.strategies.llm import get_chat_model, model_options_context


@pytest.fixture(autouse=True)
def keys_and_clean_registry(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(llm, "_MODEL_SPECIFIC_KWARGS", dict(llm._MODEL_SPECIFIC_KWARGS))
    monkeypatch.setattr(llm, "_MODEL_SPECIFIC_EXTRA_BODY", dict(llm._MODEL_SPECIFIC_EXTRA_BODY))


# --- the Claude 5 output limit -------------------------------------------------

@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"])
def test_claude_5_models_are_not_capped_at_4096(model):
    assert get_chat_model(f"anthropic:{model}").max_tokens == 16000
    assert get_chat_model(model).max_tokens == 16000  # bare name: literal Anthropic model


def test_explicit_max_tokens_beats_the_default():
    assert get_chat_model("anthropic:claude-sonnet-5-5", max_tokens=2000).max_tokens == 2000


def test_older_claude_models_keep_langchains_own_limit():
    assert get_chat_model("anthropic:claude-sonnet-4-6").max_tokens == 64000


# --- GeometryConfig.model_options ----------------------------------------------

def test_model_options_reach_a_model_built_inside_the_context():
    with model_options_context({"temperature": 0.2, "max_tokens": 1234}):
        model = get_chat_model("anthropic:claude-sonnet-5-5")
    assert model.temperature == 0.2 and model.max_tokens == 1234


def test_model_options_beat_registered_defaults_and_lose_to_explicit_kwargs():
    with model_options_context({"max_tokens": 1234}):
        assert get_chat_model("anthropic:claude-sonnet-5-5").max_tokens == 1234
        assert get_chat_model("anthropic:claude-sonnet-5-5", max_tokens=99).max_tokens == 99


def test_context_ends():
    with model_options_context({"temperature": 0.2}):
        pass
    assert get_chat_model("anthropic:claude-sonnet-5-5").temperature is None


def test_config_field_and_resolve_config():
    cfg = GeometryConfig(model_options={"temperature": 0})
    assert resolve_config(cfg).model_options == {"temperature": 0}
    assert resolve_config(cfg, model_options={"timeout": 30}).model_options == {"timeout": 30}


def test_facade_wraps_the_run_in_the_context():
    import asyncio
    from unittest.mock import AsyncMock, patch

    from geometry_diagrams import render_geometry_diagram
    from geometry_diagrams.strategies.python_full import PythonFullStrategy

    seen = {}

    async def run(self, *a, **k):
        seen["max_tokens"] = get_chat_model("anthropic:claude-sonnet-5-5").max_tokens
        raise RuntimeError("stop")

    cfg = GeometryConfig(strategy="python_full", renderer="svg", model_options={"max_tokens": 777})
    with patch.object(PythonFullStrategy, "run", run):
        with pytest.raises(RuntimeError, match="stop"):
            asyncio.run(render_geometry_diagram("a triangle", config=cfg))
    assert seen["max_tokens"] == 777


# --- register_model_options -----------------------------------------------------

def test_register_kwargs_apply_to_every_backend():
    register_model_options("anthropic:claude-sonnet-4-6", kwargs={"max_tokens": 5000})
    assert get_chat_model("anthropic:claude-sonnet-4-6").max_tokens == 5000


def test_register_extra_body_merges_with_the_providers_own():
    register_model_options("openrouter:vendor/some-model", extra_body={"provider": {"zdr": True}})
    model = get_chat_model("openrouter:vendor/some-model")
    assert model.extra_body["provider"] == {"zdr": True}
    assert model.extra_body["usage"] == {"include": True}  # openrouter's own opt-in survives


def test_register_merges_with_an_existing_entry_and_later_calls_win():
    register_model_options("openai:gpt-5.6-luna", kwargs={"temperature": 0.1})
    register_model_options("openai:gpt-5.6-luna", kwargs={"temperature": 0.3})
    model = get_chat_model("openai:gpt-5.6-luna")
    assert model.temperature == 0.3 and model.reasoning_effort == "none"  # the built-in kept


def test_extra_body_is_openai_compatible_only():
    with pytest.raises(ValueError, match="OpenAI-compatible"):
        register_model_options("anthropic:claude-sonnet-4-6", extra_body={"x": 1})


def test_register_rejects_a_model_id_without_a_provider():
    with pytest.raises(ValueError, match="provider:model"):
        register_model_options("claude-sonnet-4-6", kwargs={"max_tokens": 1})

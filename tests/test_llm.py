"""Tests for geometry_diagrams/strategies/llm.py's provider-resolution logic.

Uses monkeypatch to set the env vars _generic_openai_provider needs, rather
than relying on .env being loaded — these tests must be deterministic
regardless of the ambient environment.
"""
from __future__ import annotations

from unittest.mock import patch

from geometry_diagrams.strategies.llm import get_chat_model, make_system_message


def _set_openrouter_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def test_model_specific_extra_body_merges_with_provider_default_for_qwen37flash(monkeypatch):
    """qwen3.7-flash needs reasoning disabled (see llm.py's
    _MODEL_SPECIFIC_EXTRA_BODY) alongside openrouter's own usage-include
    opt-in (see _GENERIC_DEFAULT_KWARGS) — both must land in the same
    extra_body dict, neither clobbering the other."""
    _set_openrouter_env(monkeypatch)
    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        get_chat_model("openrouter:qwen/qwen3.7-flash")
        _, kwargs = mock_chat_openai.call_args
    assert kwargs["extra_body"] == {
        "usage": {"include": True},
        "reasoning": {"enabled": False},
    }


def test_model_specific_extra_body_does_not_leak_to_other_openrouter_models(monkeypatch):
    """The reasoning:false override is scoped to the exact model id — a
    different openrouter model must only get the provider-wide default."""
    _set_openrouter_env(monkeypatch)
    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        get_chat_model("openrouter:kwaipilot/kat-coder-air-v2.5")
        _, kwargs = mock_chat_openai.call_args
    assert kwargs["extra_body"] == {"usage": {"include": True}}


def test_model_specific_extra_body_pins_deepseek_to_fast_providers(monkeypatch):
    """deepseek-v4-flash-0731 hit a 52% timeout rate on OpenRouter's default
    routing — pinning to the fastest measured providers (BaseTen, CoreWeave,
    with fallback) must land in the same extra_body as the usage-include
    opt-in, without clobbering it."""
    _set_openrouter_env(monkeypatch)
    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        get_chat_model("openrouter:deepseek/deepseek-v4-flash-0731")
        _, kwargs = mock_chat_openai.call_args
    assert kwargs["extra_body"] == {
        "usage": {"include": True},
        "provider": {"order": ["BaseTen", "CoreWeave"], "allow_fallbacks": True},
    }


def test_model_specific_extra_body_sorts_gemma_by_throughput(monkeypatch):
    """gemma-4-31b-it hit a 26% scenario-timeout rate on OpenRouter's default
    routing — sorting by throughput (rather than pinning specific provider
    names, which drift stale) must land in the same extra_body as the
    usage-include opt-in, without clobbering it."""
    _set_openrouter_env(monkeypatch)
    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        get_chat_model("openrouter:google/gemma-4-31b-it")
        _, kwargs = mock_chat_openai.call_args
    assert kwargs["extra_body"] == {
        "usage": {"include": True},
        "provider": {"sort": "throughput"},
    }


def test_model_specific_extra_body_does_not_leak_gemma_sort_to_other_models(monkeypatch):
    """The throughput-sort override is scoped to the exact model id."""
    _set_openrouter_env(monkeypatch)
    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        get_chat_model("openrouter:qwen/qwen3.6-35b-a3b")
        _, kwargs = mock_chat_openai.call_args
    assert kwargs["extra_body"] == {"usage": {"include": True}}


# ---------------------------------------------------------------------------
# max_tokens must be scoped per-model, not a blanket mantle/mantle-oa
# default — confirmed (2026-08-07) that a provider-wide max_tokens=16000
# (added to help gpt-oss-20b/glm-4.7-flash's hidden reasoning channel)
# regressed google.gemma-4-31b from 84% to 57% pass rate: 3/4 manual trials
# at max_tokens=16000 returned a degenerate {"script":":"} tool call under
# forced tool_choice, vs. 2/2 clean at max_tokens=2000.
# ---------------------------------------------------------------------------

def _set_bedrock_env(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-token")


def test_model_specific_kwargs_applies_max_tokens_to_gpt_oss_20b_only(monkeypatch):
    _set_bedrock_env(monkeypatch)
    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        get_chat_model("mantle:openai.gpt-oss-20b")
        _, kwargs = mock_chat_openai.call_args
    assert kwargs["max_tokens"] == 16000


def test_model_specific_kwargs_does_not_leak_to_other_mantle_models(monkeypatch):
    """gemma-4-31b (via mantle-oa) must NOT get the max_tokens override that
    gpt-oss-20b/glm-4.7-flash need — this exact leak caused the 2026-08-07
    regression."""
    _set_bedrock_env(monkeypatch)
    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        get_chat_model("mantle-oa:google.gemma-4-31b")
        _, kwargs = mock_chat_openai.call_args
    assert "max_tokens" not in kwargs


def test_model_specific_kwargs_does_not_leak_to_other_mantle_family_models(monkeypatch):
    """nvidia.nemotron-super-3-120b (plain mantle:, not mantle-oa:) must also
    not get the override — it's not in _MODEL_SPECIFIC_KWARGS."""
    _set_bedrock_env(monkeypatch)
    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        get_chat_model("mantle:nvidia.nemotron-super-3-120b")
        _, kwargs = mock_chat_openai.call_args
    assert "max_tokens" not in kwargs


# ---------------------------------------------------------------------------
# make_system_message's cache_control content-block form is an Anthropic-only
# extension. Sending it to a non-Anthropic provider is at best a silently
# ignored no-op and at worst a hard rejection — confirmed (2026-08-06) that
# Fireworks.ai 400s on it ("Input should be a valid string, field:
# 'messages[0].content.str'"). enable_cache must only take effect when
# model_id resolves to Anthropic (or is omitted, for un-updated callers).
# ---------------------------------------------------------------------------

def test_make_system_message_uses_cache_control_for_anthropic_model():
    msg = make_system_message("hello", enable_cache=True, model_id="anthropic:claude-sonnet-4-6")
    assert msg.content == [{
        "type": "text",
        "text": "hello",
        "cache_control": {"type": "ephemeral"},
    }]


def test_make_system_message_ignores_enable_cache_for_non_anthropic_model(monkeypatch):
    monkeypatch.setenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
    msg = make_system_message(
        "hello", enable_cache=True, model_id="fireworks:accounts/fireworks/models/deepseek-v4-flash-0731"
    )
    assert msg.content == "hello"


def test_make_system_message_defaults_to_cache_control_when_model_id_omitted():
    """Backward-compatible default for any caller not yet updated to pass
    model_id — must not silently start dropping caching for existing
    Anthropic-only callers."""
    msg = make_system_message("hello", enable_cache=True)
    assert msg.content == [{
        "type": "text",
        "text": "hello",
        "cache_control": {"type": "ephemeral"},
    }]

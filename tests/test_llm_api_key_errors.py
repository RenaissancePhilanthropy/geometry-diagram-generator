"""A missing API key is a clear RuntimeError and is not retried as a generation failure."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.llm import get_chat_model
from geometry_diagrams.strategies.python_full import PythonFullStrategy
from geometry_diagrams.strategies.structured import StructureStrategy


def test_missing_explicit_key_env_names_variable_and_provider(monkeypatch):
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match=r"BASETEN_API_KEY.*'baseten'"):
        get_chat_model("baseten:some-model")


def test_missing_openai_key_names_variable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_chat_model("openai:gpt-6-luna")


def test_missing_google_key_names_variable(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        get_chat_model("google:gemini-2.5-flash")


def test_explicit_key_kwarg_is_not_reported_missing(monkeypatch):
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    assert get_chat_model("baseten:some-model", api_key="k") is not None


@pytest.mark.asyncio
async def test_structured_does_not_retry_a_configuration_error():
    with patch(
        "geometry_diagrams.strategies.structured.get_chat_model",
        side_effect=RuntimeError("Missing API key: X"),
    ) as get_model:
        with pytest.raises(RuntimeError, match="Missing API key"):
            await StructureStrategy().run("draw", model="anthropic:claude-sonnet-4-6")
    assert get_model.call_count == 1


@pytest.mark.asyncio
async def test_python_full_does_not_retry_a_configuration_error():
    with patch(
        "geometry_diagrams.strategies.python_full.get_chat_model",
        side_effect=RuntimeError("Missing API key: X"),
    ) as get_model:
        with pytest.raises(RuntimeError, match="Missing API key"):
            await PythonFullStrategy().run(
                "draw", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer(),
            )
    assert get_model.call_count == 1

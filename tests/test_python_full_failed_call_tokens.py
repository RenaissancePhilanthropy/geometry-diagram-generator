"""python_full counts the tokens of a generation call whose reply then failed to
parse (the exception path has no message to read usage from)."""
from __future__ import annotations

from typing import Any, Callable
from unittest.mock import patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies.python_full import (
    MAX_RETRIES, PydslScriptOutput, PythonFullStrategy,
)

SCRIPT = "a = point(0, 0)\nb = point(4, 0)\nc = point(0, 3)\nt = triangle(a, b, c)\ndraw(t)\n"


class UsageStub(BaseChatModel):
    """Every call 'costs' 12 input / 5 output tokens; the structured chain then
    runs `after` on the reply (which may raise)."""

    after: Any = None

    @property
    def _llm_type(self) -> str:
        return "usage-stub"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = AIMessage(
            content="reply",
            usage_metadata={"input_tokens": 12, "output_tokens": 5, "total_tokens": 17},
            response_metadata={"model_name": "stub"},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def with_structured_output(self, schema, *, include_raw=False, **kwargs):
        return self | RunnableLambda(self.after)


def _raise_validation_error(msg):
    # A ValidationError whose input is the full raw text: the salvage path reads it.
    PydslScriptOutput.model_validate_json(f"```python\n{SCRIPT}```")


def _raise_value_error(msg):
    raise ValueError("boom")


async def _run(after: Callable) -> tuple[PythonFullStrategy, Any, Exception | None]:
    strategy = PythonFullStrategy()
    result, error = None, None
    with patch.object(pf, "get_chat_model", return_value=UsageStub(after=after)):
        try:
            result = await strategy.run(
                "a triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer(),
            )
        except RuntimeError as exc:
            error = exc
    return strategy, result, error


@pytest.mark.asyncio
async def test_salvaged_script_still_counts_the_failed_parse_call():
    _, result, error = await _run(_raise_validation_error)
    assert error is None
    assert result.script.strip() == SCRIPT.strip()
    assert (result.input_tokens, result.output_tokens) == (12, 5)


@pytest.mark.asyncio
async def test_failed_attempts_count_their_tokens():
    strategy, result, error = await _run(_raise_value_error)
    assert result is None and error is not None
    assert strategy._partial_input_tokens == 12 * MAX_RETRIES
    assert strategy._partial_output_tokens == 5 * MAX_RETRIES

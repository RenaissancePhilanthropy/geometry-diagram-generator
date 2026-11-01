"""List-valued (thinking + text block) message content is handled, not dropped."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies import pre_assert_step as pas
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies.python_full import PythonFullStrategy

SCRIPT = "a = point(0, 0)\nb = point(4, 0)\nc = point(0, 3)\nt = triangle(a, b, c)\ndraw(t)\n"


def _blocks(text: str) -> list[dict]:
    return [{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": text}]


@pytest.mark.asyncio
async def test_raw_text_model_salvages_script_from_list_content():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content=_blocks(f"```python\n{SCRIPT}```")))
    with patch.object(pf, "get_chat_model", return_value=llm):
        result = await PythonFullStrategy().run(
            "a triangle", model="vercel:meta/muse-spark-1.2-contributor", renderer=SVGRenderer(),
        )
    assert result.script.strip() == SCRIPT.strip()


@pytest.mark.asyncio
async def test_unparsed_structured_output_salvages_script_from_list_content():
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value={
        "raw": AIMessage(content=_blocks(f"```python\n{SCRIPT}```")),
        "parsed": None,
        "parsing_error": "bad",
    })
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    with patch.object(pf, "get_chat_model", return_value=llm):
        result = await PythonFullStrategy().run(
            "a triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer(),
        )
    assert result.script.strip() == SCRIPT.strip()
    assert result.retries == 0


def test_pre_step_content_to_text_joins_text_blocks():
    assert pas._content_to_text(_blocks("assert_x()")) == "assert_x()"
    assert pas._content_to_text("plain") == "plain"

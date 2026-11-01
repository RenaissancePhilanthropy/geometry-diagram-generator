"""enable_cache reaches the python_full edit-generation LLM calls."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies.python_full import PythonFullStrategy

SCRIPT = "a = point(0, 0)\nb = point(4, 0)\nc = point(0, 3)\nt = triangle(a, b, c)\ndraw(t)\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("enable_cache", [True, False])
async def test_search_replace_edit_passes_enable_cache(enable_cache):
    response = MagicMock()
    response.content = "<<<<<<< SEARCH\nc = point(0, 3)\n=======\nc = point(0, 5)\n>>>>>>> REPLACE"
    response.usage_metadata = {"input_tokens": 1, "output_tokens": 1}
    response.response_metadata = {}
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=response)
    with patch.object(pf, "get_chat_model", return_value=llm) as get_model:
        await PythonFullStrategy(enable_cache=enable_cache).edit(
            "move c up", SCRIPT, model="anthropic:claude-sonnet-4-6",
            renderer=SVGRenderer(), edit_generation_mode="search_replace",
        )
    assert get_model.call_args.kwargs["enable_cache"] is enable_cache
    system_content = llm.ainvoke.call_args.args[0][0].content
    assert isinstance(system_content, list) is enable_cache

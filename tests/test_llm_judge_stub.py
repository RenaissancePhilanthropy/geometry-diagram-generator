"""Offline llm_judge tests with a stub chat model: structured dispatch, clamping, list content."""
import asyncio

from langchain_core.messages import AIMessage

from geometry_diagrams.util import llm_judge


class _StubChain:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages):
        return self._result


class _StubModel:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        self.calls.append((schema, kwargs))
        return _StubChain(self._result)


def _patch_model(monkeypatch, result):
    stub = _StubModel(result)
    monkeypatch.setattr(llm_judge, "get_chat_model", lambda model: stub)
    return stub


def test_judge_uses_structured_dispatch_and_clamps_scores(monkeypatch):
    parsed = llm_judge._JudgeResult(
        geometric_accuracy=9, labeling=0, completeness=4, likely_renders=5,
        score=7, reasoning="ok",
    )
    stub = _patch_model(monkeypatch, {"raw": None, "parsed": parsed, "parsing_error": None})
    out = asyncio.run(llm_judge.judge_tikz_code("p", "code"))
    assert stub.calls and stub.calls[0][1].get("include_raw") is True
    assert out["geometric_accuracy"] == 5
    assert out["labeling"] == 1
    assert out["score"] == 5
    assert out["reasoning"] == "ok"


def test_judge_falls_back_to_list_valued_raw_content(monkeypatch):
    raw = AIMessage(
        content=[
            {"type": "thinking", "thinking": "hmm"},
            {
                "type": "text",
                "text": "Geometric accuracy: 4\nLabeling: 2\nCompleteness: 3\n"
                "Likely renders: 5\nOverall score: 3",
            },
        ]
    )
    _patch_model(monkeypatch, {"raw": raw, "parsed": None, "parsing_error": ValueError("x")})
    out = asyncio.run(llm_judge.judge_tikz_code("p", "code"))
    assert out["geometric_accuracy"] == 4
    assert out["labeling"] == 2
    assert out["likely_renders"] == 5
    assert out["score"] == 3

"""
Tests for util/llm_judge.py.

Pure-logic tests (no API): _parse_visual_response
Live API tests (ANTHROPIC_API_KEY required): judge_tikz_code against known inputs

The mocked tests from the original version are removed — they only verified
Python dict plumbing and provided no signal about whether the judge actually works.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.availability import api_key_available


# ---------------------------------------------------------------------------
# Pure-logic tests — _parse_visual_response (no API required)
# ---------------------------------------------------------------------------

def test_parse_visual_response_extracts_scores():
    from util.llm_judge import _parse_visual_response

    text = """\
Geometric accuracy: 4/5
Labeling: 3/5
Completeness: 5/5
Visual quality: 4/5
Overall score: 4/5
The diagram correctly shows a right triangle.
"""
    result = _parse_visual_response(text)
    assert result["geometric_accuracy"] == 4
    assert result["labeling"] == 3
    assert result["completeness"] == 5
    assert result["visual_quality"] == 4
    assert result["score"] == 4


def test_parse_visual_response_defaults_to_3_on_parse_failure():
    from util.llm_judge import _parse_visual_response
    result = _parse_visual_response("No scores here at all.")
    assert result["score"] == 3
    assert result["geometric_accuracy"] == 3


def test_parse_visual_response_clamps_out_of_range():
    from util.llm_judge import _parse_visual_response
    text = "Overall score: 7\nGeometric accuracy: 0"
    result = _parse_visual_response(text)
    assert 1 <= result["score"] <= 5
    assert 1 <= result["geometric_accuracy"] <= 5


def test_parse_visual_response_includes_reasoning_text():
    from util.llm_judge import _parse_visual_response
    text = "Overall score: 4. The triangle looks correct and all points are labeled."
    result = _parse_visual_response(text)
    assert isinstance(result["reasoning"], str)
    assert len(result["reasoning"]) > 0


# ---------------------------------------------------------------------------
# Live API tests — judge_tikz_code (ANTHROPIC_API_KEY required)
# ---------------------------------------------------------------------------

_SKIP_LIVE = pytest.mark.skipif(
    not api_key_available(),
    reason="ANTHROPIC_API_KEY not set",
)

# Known-good: right triangle ABC with correct perpendicular coordinates at B
_GOOD_RIGHT_TRIANGLE_TIKZ = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(3,2){C}
\tkzDrawPolygon(A,B,C)
\tkzMarkRightAngle(A,B,C)
\tkzLabelPoints[below left](A)
\tkzLabelPoints[below right](B)
\tkzLabelPoints[above right](C)
"""

# Bad: prompt says right angle at B, but coordinates make an acute triangle
_BAD_TIKZ_WRONG_ANGLE = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(1.5,2.6){C}
\tkzDrawPolygon(A,B,C)
"""

# Bad: no labels at all despite prompt requesting labeled points
_BAD_TIKZ_NO_LABELS = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(3,2){C}
\tkzDrawPolygon(A,B,C)
"""

# Incomplete: prompt says triangle + circle but only triangle is drawn
_INCOMPLETE_TIKZ_NO_CIRCLE = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(2,3){C}
\tkzDrawPolygon(A,B,C)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C)
"""

_PROMPT_RIGHT_TRIANGLE = "Draw a right triangle ABC with the right angle at B"
_PROMPT_LABELED_TRIANGLE = "Draw a right triangle ABC with the right angle at B. Label all vertices."
_PROMPT_CIRCUMSCRIBED = "Draw a triangle with its circumscribed circle"


def _run(coro):
    return asyncio.run(coro)


@_SKIP_LIVE
def test_judge_scores_good_tikz_highly():
    """Known-correct right triangle should score >= 4."""
    from util.llm_judge import judge_tikz_code
    result = _run(judge_tikz_code(_PROMPT_RIGHT_TRIANGLE, _GOOD_RIGHT_TRIANGLE_TIKZ))
    assert result["score"] >= 4, (
        f"Expected good TikZ to score >= 4, got {result['score']}. "
        f"Reasoning: {result['reasoning']}"
    )


@_SKIP_LIVE
def test_judge_scores_wrong_geometry_low():
    """
    Prompt asks for right angle at B, but coordinates make an acute triangle
    with no right angle mark. Should score <= 3.
    """
    from util.llm_judge import judge_tikz_code
    result = _run(judge_tikz_code(_PROMPT_RIGHT_TRIANGLE, _BAD_TIKZ_WRONG_ANGLE))
    assert result["score"] <= 3, (
        f"Expected bad geometry to score <= 3, got {result['score']}. "
        f"Reasoning: {result['reasoning']}"
    )


@_SKIP_LIVE
def test_judge_detects_missing_labels():
    """TikZ with no label commands should score labeling <= 2."""
    from util.llm_judge import judge_tikz_code
    result = _run(judge_tikz_code(_PROMPT_LABELED_TRIANGLE, _BAD_TIKZ_NO_LABELS))
    assert result["labeling"] <= 2, (
        f"Expected labeling score <= 2, got {result['labeling']}. "
        f"Reasoning: {result['reasoning']}"
    )


@_SKIP_LIVE
def test_judge_detects_incomplete_diagram():
    """Prompt asks for triangle + circle but only triangle drawn. completeness <= 3."""
    from util.llm_judge import judge_tikz_code
    result = _run(judge_tikz_code(_PROMPT_CIRCUMSCRIBED, _INCOMPLETE_TIKZ_NO_CIRCLE))
    assert result["completeness"] <= 3, (
        f"Expected completeness score <= 3, got {result['completeness']}. "
        f"Reasoning: {result['reasoning']}"
    )


@_SKIP_LIVE
def test_judge_returns_all_expected_keys():
    """Sanity check: judge always returns all required fields in valid ranges."""
    from util.llm_judge import judge_tikz_code
    result = _run(judge_tikz_code(_PROMPT_RIGHT_TRIANGLE, _GOOD_RIGHT_TRIANGLE_TIKZ))

    for key in ("score", "geometric_accuracy", "labeling", "completeness", "likely_renders", "reasoning"):
        assert key in result, f"Missing key: {key}"

    for key in ("score", "geometric_accuracy", "labeling", "completeness", "likely_renders"):
        assert 1 <= result[key] <= 5, f"{key}={result[key]} is out of 1-5 range"

    assert isinstance(result["reasoning"], str) and len(result["reasoning"]) > 0

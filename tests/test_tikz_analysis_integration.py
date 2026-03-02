"""
Integration tests: tikz_analysis on real LLM-generated TikZ code.

Our unit tests in test_tikz_analysis.py only exercise hand-written TikZ.
Real LLM output can differ in spacing, ordering, multi-line formatting, and
which construction idioms the model chooses. These tests verify the analysis
module works on actual agent output.

Requires: Docker + RUN_LLM_TESTS=true + ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import asyncio

import pytest

from strategies.raw_code import RawCodeStrategy
from tests.availability import api_key_available, llm_tests_enabled, renderer_available
from util.tikz_analysis import (
    extract_defined_points,
    extract_draw_commands,
    extract_marks,
    resolve_all_coordinates,
    validate_geometric_property,
)
from tests.agent_helpers import extract_tikz_from_run


pytestmark = [
    pytest.mark.skipif(
        not renderer_available(),
        reason="TikZ renderer container not running on localhost:8001",
    ),
    pytest.mark.skipif(
        not llm_tests_enabled(),
        reason="RUN_LLM_TESTS is not enabled",
    ),
    pytest.mark.skipif(
        not api_key_available(),
        reason="ANTHROPIC_API_KEY not set",
    ),
]


def _run_agent(prompt: str):
    agent = RawCodeStrategy().build_agent()
    return asyncio.run(agent.run(prompt))


# ---------------------------------------------------------------------------
# Right triangle — highest-value test
# ---------------------------------------------------------------------------

def test_analysis_finds_named_points_in_right_triangle():
    """
    Agent generates right triangle ABC — analysis must find A, B, C coordinates.
    """
    result = _run_agent("Draw a right triangle ABC with the right angle at B")
    tikz = extract_tikz_from_run(result)
    assert tikz is not None, "No TikZ extracted from agent output"

    coords = resolve_all_coordinates(tikz)
    missing = [p for p in ["A", "B", "C"] if p not in coords]
    assert not missing, (
        f"Points {missing} not found in extracted coords. "
        f"Full coords: {list(coords)}. TikZ:\n{tikz}"
    )


def test_analysis_validates_right_angle_in_agent_output():
    """
    Agent generates right triangle ABC at B — validate_geometric_property
    should confirm the right angle using the actual coordinates chosen by the LLM.
    """
    result = _run_agent("Draw a right triangle ABC with the right angle at B")
    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    coords = resolve_all_coordinates(tikz)
    if not all(p in coords for p in ["A", "B", "C"]):
        pytest.skip(f"Points A,B,C not all resolvable. Got: {list(coords)}")

    is_right = validate_geometric_property(coords, "right_angle", ["A", "B", "C"])
    assert is_right is True, (
        f"Right angle not confirmed at B. "
        f"A={coords.get('A')}, B={coords.get('B')}, C={coords.get('C')}. "
        f"TikZ:\n{tikz}"
    )


# ---------------------------------------------------------------------------
# Midpoint — tests computed point extraction
# ---------------------------------------------------------------------------

def test_analysis_resolves_midpoint_from_agent_output():
    """
    Agent draws segment AB with midpoint M — analysis resolves M's coordinates
    and validates it is the true midpoint.
    """
    result = _run_agent("Draw a segment AB and mark its midpoint M")
    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    coords = resolve_all_coordinates(tikz)
    if not all(p in coords for p in ["A", "B", "M"]):
        pytest.skip(f"Points A,B,M not all resolvable. Got: {list(coords)}")

    is_midpoint = validate_geometric_property(coords, "midpoint", ["M", "A", "B"])
    assert is_midpoint is True, (
        f"M is not the midpoint of AB. "
        f"A={coords.get('A')}, B={coords.get('B')}, M={coords.get('M')}"
    )


# ---------------------------------------------------------------------------
# Draw commands — verify extraction works on real LLM output
# ---------------------------------------------------------------------------

def test_analysis_extracts_draw_commands_from_triangle():
    """
    Agent draws a triangle — extract_draw_commands should find at least one
    polygon or segment command.
    """
    result = _run_agent("Draw a right triangle ABC with the right angle at B")
    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    cmds = extract_draw_commands(tikz)
    draw_cmds = [c for c in cmds if c["type"] in ("polygon", "segment", "line")]
    assert len(draw_cmds) >= 1, (
        f"No polygon/segment/line commands found in agent TikZ output. "
        f"Commands: {cmds}. TikZ:\n{tikz}"
    )


def test_analysis_extracts_right_angle_mark_from_agent():
    """
    Agent draws a right triangle with a right angle mark — extract_marks
    should find a right_angle mark.
    """
    result = _run_agent("Draw a right triangle ABC with the right angle at B")
    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    marks = extract_marks(tikz)
    right_angle_marks = [m for m in marks if m["type"] == "right_angle"]
    assert len(right_angle_marks) >= 1, (
        f"Expected \\tkzMarkRightAngle in agent output, not found. "
        f"Marks: {marks}. TikZ:\n{tikz}"
    )


# ---------------------------------------------------------------------------
# Robustness — analysis shouldn't crash on any LLM output
# ---------------------------------------------------------------------------

def test_analysis_does_not_crash_on_complex_diagram():
    """
    Complex prompt — analysis may not resolve all points, but must not raise.
    """
    result = _run_agent("Draw a triangle with its circumscribed circle")
    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    # These must not raise, regardless of what the LLM generated
    coords = resolve_all_coordinates(tikz)
    cmds = extract_draw_commands(tikz)
    marks = extract_marks(tikz)

    assert isinstance(coords, dict)
    assert isinstance(cmds, list)
    assert isinstance(marks, list)

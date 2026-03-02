"""
End-to-end agent tests: prompt → LLM → TikZ → Docker → SVG → geometric checks.

These are the most important tests in the suite — they verify the actual
system behavior, not just the scaffolding.

Requirements:
  - TikZ renderer Docker container running on localhost:8001
  - ANTHROPIC_API_KEY set in environment

Each test takes 10-30s (one LLM call + one render).
"""
from __future__ import annotations

import asyncio

import pytest

from strategies.raw_code import RawCodeStrategy
from tests.availability import api_key_available, renderer_available
from util.svg_checks import run_svg_checks
from util.tikz_analysis import resolve_all_coordinates, validate_geometric_property
from tests.agent_helpers import (
    count_tool_calls,
    extract_svg_from_run,
    extract_tikz_from_run,
)


pytestmark = [
    pytest.mark.skipif(
        not renderer_available(),
        reason="TikZ renderer container not running on localhost:8001",
    ),
    pytest.mark.skipif(
        not api_key_available(),
        reason="ANTHROPIC_API_KEY not set",
    ),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run_agent(prompt: str):
    """Run the agent synchronously and return the RunResult."""
    agent = RawCodeStrategy().build_agent()
    return asyncio.run(agent.run(prompt))


def _assert_svg_valid(svg: str) -> None:
    failures = run_svg_checks(svg)
    assert failures == [], f"SVG quality checks failed: {failures}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_right_triangle_svg_and_geometry():
    """
    The most fundamental test: the agent draws a right triangle with the right
    angle at B, and we verify both the SVG and the geometry.
    """
    result = _run_agent("Draw a right triangle ABC with the right angle at B")

    svg = extract_svg_from_run(result)
    assert svg is not None, "Agent did not produce an SVG"
    _assert_svg_valid(svg)

    tikz = extract_tikz_from_run(result)
    assert tikz is not None, "Could not extract TikZ from agent output"

    coords = resolve_all_coordinates(tikz)
    assert "A" in coords, f"Point A not found in coords. Got: {list(coords)}"
    assert "B" in coords, f"Point B not found in coords. Got: {list(coords)}"
    assert "C" in coords, f"Point C not found in coords. Got: {list(coords)}"

    is_right = validate_geometric_property(coords, "right_angle", ["A", "B", "C"])
    assert is_right is True, (
        f"Expected right angle at B but got is_right={is_right}. "
        f"Coords: A={coords.get('A')}, B={coords.get('B')}, C={coords.get('C')}"
    )


def test_midpoint_construction():
    """Agent draws segment AB with midpoint M — verify M is actually the midpoint."""
    result = _run_agent("Draw a segment AB and mark its midpoint M")

    svg = extract_svg_from_run(result)
    assert svg is not None
    _assert_svg_valid(svg)

    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    coords = resolve_all_coordinates(tikz)
    assert "A" in coords and "B" in coords, f"Points A,B not found. Got: {list(coords)}"
    assert "M" in coords, f"Midpoint M not found. Got: {list(coords)}"

    is_midpoint = validate_geometric_property(coords, "midpoint", ["M", "A", "B"])
    assert is_midpoint is True, (
        f"M is not the midpoint of AB. "
        f"A={coords.get('A')}, B={coords.get('B')}, M={coords.get('M')}"
    )


def test_equilateral_triangle_equal_sides():
    """Agent draws equilateral triangle — verify all three sides are equal length."""
    result = _run_agent("Draw an equilateral triangle ABC")

    svg = extract_svg_from_run(result)
    assert svg is not None
    _assert_svg_valid(svg)

    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    coords = resolve_all_coordinates(tikz)
    if not all(p in coords for p in ["A", "B", "C"]):
        pytest.skip(f"Points A,B,C not all resolvable. Got: {list(coords)}")

    is_equilateral = validate_geometric_property(
        coords, "equal_lengths", [["A", "B"], ["B", "C"], ["C", "A"]]
    )
    assert is_equilateral is True, (
        f"Triangle sides are not equal. Coords: {coords}"
    )


def test_circumscribed_circle_draws_circle():
    """Agent draws triangle + circumscribed circle — TikZ must include a circle draw."""
    result = _run_agent("Draw a triangle with its circumscribed circle")

    svg = extract_svg_from_run(result)
    assert svg is not None
    _assert_svg_valid(svg)

    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    # The TikZ code must include a circle drawing command
    assert "\\tkzDrawCircle" in tikz or "\\draw" in tikz and "circle" in tikz.lower(), (
        "Expected a circle drawing command in TikZ output"
    )


def test_agent_calls_render_tool():
    """Verify the agent actually calls render_diagram (not just returning text)."""
    result = _run_agent("Draw a right triangle ABC with the right angle at B")
    n = count_tool_calls(result.all_messages(), "render_diagram")
    assert n >= 1, "Agent never called render_diagram"


def test_svg_is_non_trivial():
    """
    The SVG should represent a real diagram, not a stub.
    We check that the viewBox is bigger than a single point.
    """
    result = _run_agent("Draw a segment AB and mark its midpoint M")
    svg = extract_svg_from_run(result)
    assert svg is not None

    import xml.etree.ElementTree as ET
    root = ET.fromstring(svg)
    viewbox = root.get("viewBox", "")
    parts = viewbox.split()
    assert len(parts) == 4, f"Unexpected viewBox format: {viewbox!r}"
    width, height = float(parts[2]), float(parts[3])
    assert width > 1 and height > 1, f"SVG viewBox is too small: {width}x{height}"


def test_parallel_lines_prompt():
    """
    Parallel lines scenario — verify SVG renders and TikZ has two line commands.
    This is harder for tikz_analysis to verify geometrically (lines extend infinitely),
    so we just check structural correctness.
    """
    result = _run_agent(
        "Draw a transversal intersecting two parallel lines, "
        "and label two opposite interior angles"
    )

    svg = extract_svg_from_run(result)
    assert svg is not None
    _assert_svg_valid(svg)

    tikz = extract_tikz_from_run(result)
    assert tikz is not None

    # Should draw at least two lines/segments
    from util.tikz_analysis import extract_draw_commands
    cmds = extract_draw_commands(tikz)
    line_cmds = [c for c in cmds if c["type"] in ("line", "segment", "polygon")]
    assert len(line_cmds) >= 2, (
        f"Expected at least 2 line/segment commands, got {len(line_cmds)}: {cmds}"
    )

"""
Integration tests for util/tikz_renderer.py.
These tests require the TikZ renderer container to be running on port 8001.
"""

import asyncio

import pytest

from tests.availability import renderer_available
from util.tikz_renderer import render_tikz
from util.svg_checks import run_svg_checks

pytestmark = pytest.mark.skipif(
    not renderer_available(),
    reason="TikZ renderer container not running on localhost:8001",
)


def _assert_valid_svg(svg: str) -> None:
    """Assert the string is a well-formed, non-empty SVG."""
    assert "<svg" in svg
    assert "</svg>" in svg
    failures = run_svg_checks(svg)
    assert failures == [], f"SVG quality checks failed: {failures}"


# ---------------------------------------------------------------------------
# Existing tests (kept from original)
# ---------------------------------------------------------------------------

def test_simple_triangle():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(1.5,2.6){C}
\tkzDrawPolygon(A,B,C)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C)
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_right_triangle_with_right_angle_mark():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(3,2){C}
\tkzDrawPolygon(A,B,C)
\tkzMarkRightAngle(A,B,C)
\tkzLabelPoints[below left](A)
\tkzLabelPoints[below right](B)
\tkzLabelPoints[above right](C)
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_invalid_tikz_raises():
    with pytest.raises(RuntimeError, match="lualatex"):
        render_tikz(r"\undefinedcommandthatdoesnotexist")


def test_with_tkzelements():
    tkzelements = r"""
z.A = point: new (0, 0)
z.B = point: new (4, 0)
z.C = point: new (2, 3)
"""
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(2,3){C}
\tkzDrawPolygon(A,B,C)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C)
"""
    svg = render_tikz(tikz, tkzelements=tkzelements)
    _assert_valid_svg(svg)


# ---------------------------------------------------------------------------
# New tests
# ---------------------------------------------------------------------------

def test_circumscribed_circle():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(1,3){C}
\tkzDrawPolygon(A,B,C)
\tkzCircumCenter(A,B,C) \tkzGetPoint{O}
\tkzDrawCircle(O,A)
\tkzDrawPoint(O)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C)
\tkzLabelPoint[right](O){$O$}
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_parallel_lines():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(0,2){C}
\tkzDefPoint(4,2){D}
\tkzDrawLine(A,B)
\tkzDrawLine(C,D)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C,D)
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_angle_marks():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(1.5,2.6){C}
\tkzDrawPolygon(A,B,C)
\tkzMarkAngle[size=0.5](B,A,C)
\tkzMarkAngle[size=0.5](C,B,A)
\tkzMarkAngle[size=0.5](A,C,B)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C)
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_segment_tick_marks():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(0,3){C}
\tkzDrawPolygon(A,B,C)
\tkzMarkSegment[mark=|](A,B)
\tkzMarkSegment[mark=|](A,C)
\tkzMarkSegment[mark=||](B,C)
\tkzLabelPoints[below left](A)
\tkzLabelPoints[below right](B)
\tkzLabelPoints[above left](C)
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_midpoint_construction():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefMidPoint(A,B) \tkzGetPoint{M}
\tkzDrawSegment(A,B)
\tkzDrawPoint(M)
\tkzLabelPoints[below](A,B,M)
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_line_intersection():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,4){B}
\tkzDefPoint(0,4){C}
\tkzDefPoint(4,0){D}
\tkzInterLL(A,B)(C,D) \tkzGetPoint{P}
\tkzDrawLine(A,B)
\tkzDrawLine(C,D)
\tkzDrawPoint(P)
\tkzLabelPoint[right](P){$P$}
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_complex_diagram_with_multiple_features():
    """Polygon + circle + marks + labels + midpoint."""
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(4,3){C}
\tkzDrawPolygon(A,B,C)
\tkzMarkRightAngle(A,B,C)
\tkzMarkSegment[mark=|](A,B)
\tkzDefMidPoint(A,C) \tkzGetPoint{M}
\tkzDrawPoint(M)
\tkzLabelPoints[below left](A)
\tkzLabelPoints[below right](B)
\tkzLabelPoints[above right](C)
\tkzLabelPoint[above left](M){$M$}
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)


def test_tkzelements_computed_circumcenter():
    """Use tkz-elements Lua to compute a circumcenter, then draw it."""
    tkzelements = r"""
z.A = point: new (0, 0)
z.B = point: new (4, 0)
z.C = point: new (2, 3)
T.ABC = triangle: new (z.A, z.B, z.C)
z.O = T.ABC.circumcenter
"""
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(2,3){C}
\tkzCircumCenter(A,B,C) \tkzGetPoint{O}
\tkzDrawPolygon(A,B,C)
\tkzDrawCircle(O,A)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C)
"""
    svg = render_tikz(tikz, tkzelements=tkzelements)
    _assert_valid_svg(svg)


def test_empty_tikz_raises_or_produces_minimal_svg():
    """
    Empty TikZ code should either raise (compile error) or produce a minimal SVG.
    Either outcome is acceptable; this test documents the actual behavior.
    """
    try:
        svg = render_tikz("")
        # If it renders, it should at least be syntactically valid XML
        assert "<svg" in svg
    except RuntimeError:
        pass  # Compile error is also acceptable


def test_concurrent_renders():
    """Multiple simultaneous render requests should all succeed."""

    async def _render_all():
        tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(1.5,2.6){C}
\tkzDrawPolygon(A,B,C)
"""

        async def render_async(idx):
            # render_tikz is sync; run in thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, render_tikz, tikz)

        results = await asyncio.gather(*[render_async(i) for i in range(3)])
        return results

    results = asyncio.run(_render_all())
    assert len(results) == 3
    for svg in results:
        _assert_valid_svg(svg)


def test_very_long_labels():
    """Labels with longer text strings should not crash the renderer."""
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDrawSegment(A,B)
\tkzLabelPoint[below](A){$A_{\text{start}}$}
\tkzLabelPoint[below](B){$B_{\text{end}}$}
"""
    svg = render_tikz(tikz)
    _assert_valid_svg(svg)

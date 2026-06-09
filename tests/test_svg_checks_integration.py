"""
Integration tests: svg_checks against actual dvisvgm-rendered SVGs.

Our hand-crafted SVG fixtures in test_svg_checks.py don't necessarily match
real dvisvgm output (which uses namespaced elements, glyph <use> elements,
specific path formats, etc.). These tests verify the checks work on the real thing.

Requires: TikZ renderer Docker container on localhost:8001.
"""
from __future__ import annotations

import pytest

from tests.availability import renderer_available
from geometry_diagrams.util.tikz_renderer import render_tikz
from geometry_diagrams.util.svg_checks import (
    check_svg_has_content,
    check_svg_reasonable_size,
    check_svg_wellformed,
    run_svg_checks,
)

pytestmark = pytest.mark.skipif(
    not renderer_available(),
    reason="TikZ renderer container not running on localhost:8001",
)


# ---------------------------------------------------------------------------
# Fixtures — rendered once and reused
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def triangle_svg():
    return render_tikz(r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(1.5,2.6){C}
\tkzDrawPolygon(A,B,C)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C)
""")


@pytest.fixture(scope="module")
def complex_svg():
    return render_tikz(r"""
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
""")


@pytest.fixture(scope="module")
def circle_svg():
    return render_tikz(r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(1,3){C}
\tkzDrawPolygon(A,B,C)
\tkzCircumCenter(A,B,C) \tkzGetPoint{O}
\tkzDrawCircle(O,A)
\tkzLabelPoints[below](A,B)
\tkzLabelPoints[above](C)
""")


# ---------------------------------------------------------------------------
# Wellformed check
# ---------------------------------------------------------------------------

def test_real_triangle_svg_is_wellformed(triangle_svg):
    assert check_svg_wellformed(triangle_svg) is None


def test_real_complex_svg_is_wellformed(complex_svg):
    assert check_svg_wellformed(complex_svg) is None


def test_real_circle_svg_is_wellformed(circle_svg):
    assert check_svg_wellformed(circle_svg) is None


def test_real_svg_has_viewbox(triangle_svg):
    """dvisvgm always produces a viewBox — verify ours does too."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(triangle_svg)
    assert root.get("viewBox") is not None, "Real SVG missing viewBox"


# ---------------------------------------------------------------------------
# Content check
# ---------------------------------------------------------------------------

def test_real_triangle_svg_has_content(triangle_svg):
    assert check_svg_has_content(triangle_svg) is None


def test_real_complex_svg_has_content(complex_svg):
    assert check_svg_has_content(complex_svg) is None


def test_real_circle_svg_has_content(circle_svg):
    assert check_svg_has_content(circle_svg) is None


# ---------------------------------------------------------------------------
# Size check
# ---------------------------------------------------------------------------

def test_real_triangle_svg_reasonable_size(triangle_svg):
    assert check_svg_reasonable_size(triangle_svg) is None


def test_real_complex_svg_reasonable_size(complex_svg):
    assert check_svg_reasonable_size(complex_svg) is None


# ---------------------------------------------------------------------------
# Full run_svg_checks
# ---------------------------------------------------------------------------

def test_run_svg_checks_triangle_passes(triangle_svg):
    failures = run_svg_checks(triangle_svg)
    assert failures == [], f"Real triangle SVG failed checks: {failures}"


def test_run_svg_checks_complex_passes(complex_svg):
    failures = run_svg_checks(complex_svg)
    assert failures == [], f"Real complex SVG failed checks: {failures}"


def test_run_svg_checks_circle_passes(circle_svg):
    failures = run_svg_checks(circle_svg)
    assert failures == [], f"Real circle SVG failed checks: {failures}"


# ---------------------------------------------------------------------------
# Structural spot-checks on real dvisvgm output
# ---------------------------------------------------------------------------

def test_real_svg_uses_svg_namespace(triangle_svg):
    """dvisvgm always emits SVG with the standard namespace."""
    assert 'xmlns="http://www.w3.org/2000/svg"' in triangle_svg or \
           "http://www.w3.org/2000/svg" in triangle_svg


def test_real_svg_viewbox_is_numeric(triangle_svg):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(triangle_svg)
    viewbox = root.get("viewBox", "")
    parts = viewbox.split()
    assert len(parts) == 4
    for p in parts:
        float(p)  # Should not raise


def test_real_svg_has_reasonable_aspect_ratio(triangle_svg):
    """
    A standard geometry diagram should have a reasonable aspect ratio —
    not a degenerate 1000:1 rectangle.
    """
    import xml.etree.ElementTree as ET
    root = ET.fromstring(triangle_svg)
    parts = root.get("viewBox", "0 0 0 0").split()
    w, h = float(parts[2]), float(parts[3])
    assert w > 0 and h > 0
    ratio = max(w, h) / min(w, h)
    assert ratio < 20, f"Aspect ratio {ratio:.1f} is unreasonably extreme"

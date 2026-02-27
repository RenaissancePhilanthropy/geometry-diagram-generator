"""
Integration tests for util/tikz_renderer.py.
These tests require the TikZ renderer container to be running on port 8001.
"""

import pytest
import httpx

from util.tikz_renderer import render_tikz


def _renderer_available() -> bool:
    try:
        httpx.get("http://localhost:8001/docs", timeout=2.0)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _renderer_available(),
    reason="TikZ renderer container not running on localhost:8001",
)


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
    assert "<svg" in svg
    assert "</svg>" in svg


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
    assert "<svg" in svg
    assert "</svg>" in svg


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
    assert "<svg" in svg

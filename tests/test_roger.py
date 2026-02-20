"""
Tests for using Roger to generate SVGs from substances, and to validate substances without rendering.
"""

import pytest
from util.roger import render_svg

def test_render_valid_substance():
    substance = """
    Point A
    AutoLabel A
    """
    svg = render_svg(substance, "valid substance")
    assert "<svg" in svg and "</svg>" in svg
    print("SVG output for valid substance:\n", svg)
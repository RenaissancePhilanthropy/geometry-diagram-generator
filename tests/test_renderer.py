"""Tests for ir/renderer.py.

NOTE: Tests that call TikZRenderer.render() require the renderer Docker container
(docker run -p 8001:8001 tikz-renderer). Structural tests below do not.
"""
from __future__ import annotations

import pytest

from ir.ir import DiagramIR, PointFixed, Triangle, Draw
from ir.to_sympy import compile_defs
from ir.renderer import Renderer, RenderResult, TikZRenderer


# ---------------------------------------------------------------------------
# Structural tests — no renderer container needed
# ---------------------------------------------------------------------------

def test_tikz_renderer_is_renderer_subclass():
    """TikZRenderer must satisfy the Renderer ABC."""
    r = TikZRenderer()
    assert isinstance(r, Renderer)


def test_render_result_fields():
    """RenderResult stores output, format, and optional intermediate."""
    r = RenderResult(output="<svg/>", format="svg", intermediate="\\tkzDefPoint(0,0){A}")
    assert r.output == "<svg/>"
    assert r.format == "svg"
    assert r.intermediate == "\\tkzDefPoint(0,0){A}"


def test_render_result_intermediate_defaults_empty():
    r = RenderResult(output="<svg/>", format="svg")
    assert r.intermediate == ""


def test_tikz_renderer_check_health_returns_bool():
    """check_health() must return a bool regardless of container state."""
    r = TikZRenderer()
    result = r.check_health()
    assert isinstance(result, bool)


def test_tikz_renderer_accepts_custom_url():
    """TikZRenderer stores a custom renderer_url without error."""
    r = TikZRenderer(renderer_url="http://custom:9999")
    assert r._url == "http://custom:9999"

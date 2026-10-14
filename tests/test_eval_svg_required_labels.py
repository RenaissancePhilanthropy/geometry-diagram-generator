"""required_labels evaluated against the rendered SVG's label text (svg renderer)."""
from __future__ import annotations

import asyncio

import pytest

from evals.run import _svg_required_label_checks
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline


def _svg(*labels) -> str:
    d = ir.DiagramIR(
        define=[
            ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=6, y=0),
            ir.Segment(id="AB", a="A", b="B"),
        ],
        render=[ir.Draw(obj="AB"), ir.LabelPoint(p="A"), ir.LabelPoint(p="B"), *labels],
    )
    return asyncio.run(run_ir_pipeline(d, SVGRenderer())).svg


def test_units_label_missing_when_svg_only_has_bare_number():
    svg = _svg(ir.LabelSegment(seg="AB", text="6"))
    res = _svg_required_label_checks(svg, ["6 units"])
    assert res["passed"] is False and res["missing"] == ["6 units"]


def test_units_label_present_passes():
    svg = _svg(ir.LabelFreeText(text="6 units", at=[3, 1]))
    assert _svg_required_label_checks(svg, ["6 units"])["passed"] is True
    svg = _svg(ir.LabelSegment(seg="AB", text="6 units"))
    assert _svg_required_label_checks(svg, ["6 units"])["passed"] is True


def test_point_labels_match_exactly():
    svg = _svg()
    assert _svg_required_label_checks(svg, ["A", "B"])["passed"] is True
    res = _svg_required_label_checks(svg, ["A", "C"])
    assert res["missing"] == ["C"]


def test_wired_into_gate_failures_when_tikz_path_is_empty():
    from evals.run import _finalize_gate_status
    record = {"generation_success": True, "svg_rendered": True, "tikz_code": None,
              "tikz_checks": {"required_labels": {"passed": False, "missing": ["6 units"]}}}
    _finalize_gate_status(record)
    assert record["gate_status"] == "fail" and "required_labels" in record["gate_failures"]

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


def test_forbidden_label_found_as_whole_token():
    from evals.run import _svg_forbidden_label_checks

    svg = _svg(ir.LabelFreeText(text="V = 24", at=[3, 1]))
    res = _svg_forbidden_label_checks(svg, ["24", "12"])
    assert res == {"passed": False, "found": ["24"]}


def test_forbidden_label_not_matched_inside_larger_number():
    from evals.run import _svg_forbidden_label_checks

    svg = _svg(ir.LabelSegment(seg="AB", text="240"))
    assert _svg_forbidden_label_checks(svg, ["24"])["passed"] is True


def test_forbidden_labels_normalized_and_gate_fails(tmp_path):
    from evals.run import _collect_check_outcomes
    from evals.scenarios import load_scenarios

    f = tmp_path / "s.yaml"
    f.write_text(
        "- id: x\n  prompt: p\n  forbidden_labels: ['24']\n"
    )
    assert load_scenarios(f)[0]["forbidden_labels"] == ["24"]
    failures, _, _ = _collect_check_outcomes(
        {"tikz_checks": {"forbidden_labels": {"passed": False, "found": ["24"]}}}
    )
    assert failures == ["forbidden_labels"]

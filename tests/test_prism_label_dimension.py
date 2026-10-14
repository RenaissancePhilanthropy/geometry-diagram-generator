"""A numeric label on a prism edge is compared with the edge's true length."""
from __future__ import annotations

import asyncio

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline


def _run(*labels: ir.LabelSegment):
    d = ir.DiagramIR(
        define=[
            ir.PointFixed(id="O", x=0, y=0),
            ir.RectangularPrism(id="P", origin="O", length=10, width=6, height=5),
        ],
        render=[ir.Draw(obj="P"), *labels],
    )
    return asyncio.run(run_ir_pipeline(d, SVGRenderer()))


def _label_warnings(result) -> list[str]:
    return [w for w in result.warnings if "label" in w.lower() and "true length" in w.lower()]


def test_number_not_matching_edge_true_length_warns():
    r = _run(ir.LabelSegment(seg="P_e_010_110", text="5"))
    warns = _label_warnings(r)
    assert len(warns) == 1
    assert "P_e_010_110" in warns[0] and "10" in warns[0] and "length" in warns[0]


def test_matching_height_edge_does_not_warn():
    assert not _label_warnings(_run(ir.LabelSegment(seg="P_e_000_010", text="5")))


def test_units_text_parses_the_number():
    assert not _label_warnings(_run(ir.LabelSegment(seg="P_e_000_001", text="6 units")))
    assert _label_warnings(_run(ir.LabelSegment(seg="P_e_000_001", text="5 units")))


def test_schematic_label_without_number_never_warns():
    assert not _label_warnings(_run(ir.LabelSegment(seg="P_e_000_100", text="l")))


def test_label_on_non_prism_segment_is_ignored():
    d = ir.DiagramIR(
        define=[
            ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=3, y=0),
            ir.Segment(id="AB", a="A", b="B"),
        ],
        render=[ir.Draw(obj="AB"), ir.LabelSegment(seg="AB", text="7")],
    )
    assert not _label_warnings(asyncio.run(run_ir_pipeline(d, SVGRenderer())))

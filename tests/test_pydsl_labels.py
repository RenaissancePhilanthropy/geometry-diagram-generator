# tests/test_pydsl_labels.py
"""Tests for pydsl label support: Point.label(), segment()/Segment.label(),
AngleRef.label(), and label_text() — all wrapping IR RenderOp kinds
(LabelPoint/LabelSegment/LabelAngle/LabelFreeText) that already exist and
are already rendered by to_tikz.py/to_svg.py."""
import pytest

from geometry_diagrams.pydsl.api import point
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.ir.ir import LabelPoint


def test_point_label_records_label_point():
    with new_builder_context() as builder:
        p = point(1, 2)
        p.label("A")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelPoint) and r.p == p.id]
    assert len(matches) == 1
    assert matches[0].text == "A"
    assert matches[0].pos == "auto"
    assert matches[0].show_coords is False


def test_point_label_with_pos_and_show_coords():
    with new_builder_context() as builder:
        p = point(1, 2)
        p.label("A", pos="above left", show_coords=True)
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelPoint) and r.p == p.id]
    assert matches[0].pos == "above left"
    assert matches[0].show_coords is True

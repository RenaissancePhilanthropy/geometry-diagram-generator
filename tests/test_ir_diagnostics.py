"""Tests for evals/ir_diagnostics.py — IR failure classification."""
from __future__ import annotations

import json

import pytest

from geometry_diagrams.ir.ir import (
    DiagramIR, PointFixed, PointMidpoint, PointIntersection,
    PointOn, PointOnParam, Segment, LineThrough, Triangle,
    CircleCenterPoint,
)
from evals.ir_diagnostics import classify_ir, IRDiagnostics


def _make_triangle_ir():
    return DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=2, y=3),
        Segment(id="s_AB", a="A", b="B"),
        Triangle(id="T", a="A", b="B", c="C"),
    ])


def test_classify_ir_counts_point_fixed():
    diag = _make_triangle_ir()
    result = classify_ir(diag)
    assert result.hardcoded_count == 3  # A, B, C are all point_fixed


def test_classify_ir_counts_parametric():
    diag = DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        Segment(id="s", a="A", b="B"),
        PointOn(id="D", on="s", how=PointOnParam(t=0.75)),
    ])
    result = classify_ir(diag)
    assert result.parametric_count == 1


def test_classify_ir_counts_missing_pick():
    diag = DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="O", x=2, y=0),
        CircleCenterPoint(id="c", center="O", through="A"),
        LineThrough(id="l", p="A", q="B"),
        PointIntersection(id="I", obj1="c", obj2="l"),  # no pick!
    ])
    result = classify_ir(diag)
    assert result.missing_pick_count == 1


def test_classify_ir_no_issues_for_clean_ir():
    diag = DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=0, y=3),
        Segment(id="s_AB", a="A", b="B"),
        PointMidpoint(id="M", p="A", q="B"),
    ])
    result = classify_ir(diag)
    assert result.parametric_count == 0
    assert result.missing_pick_count == 0


def test_classify_ir_returns_dict_serializable():
    diag = _make_triangle_ir()
    result = classify_ir(diag)
    d = result.to_dict()
    json.dumps(d)  # must not raise

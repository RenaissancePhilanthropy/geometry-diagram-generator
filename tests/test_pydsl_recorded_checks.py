"""A passing assert_* call is kept in the IR as a Check, so the IR describes what the script
claimed about itself and verify_geometry_diagram can re-check it."""
from __future__ import annotations

import asyncio

import pytest

from geometry_diagrams import verify_geometry_diagram
from geometry_diagrams.ir.ir import DistanceEquals, RightAngle
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl.builder import OpCapExceededError, new_builder_context
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.strategies.ir_pipeline import PipelineError, run_ir_pipeline

SCRIPT = """
canvas((-2, 12), (-2, 10))
a = point(0, 6); b = point(0, 0); c = point(8, 0)
t = triangle(a, b, c); draw(t)
assert_distance(t.side(a, b), 6)
assert_right_angle(t.angle_at(b))
assert_distance(t.side(b, c), 8, tol=0.5)
"""


def _ir():
    result = run_script(SCRIPT, timeout_seconds=60)
    assert result.error is None, result.error
    return result.diagram_ir


def test_passing_asserts_are_recorded_in_order():
    checks = _ir().checks
    assert [type(c) for c in checks] == [DistanceEquals, RightAngle, DistanceEquals]
    assert checks[0].expected == 6 and checks[2].tol == 0.5


def test_a_failing_assert_still_raises_and_records_nothing():
    result = run_script(SCRIPT.replace("assert_distance(t.side(a, b), 6)", "assert_distance(t.side(a, b), 7)"),
                        timeout_seconds=60)
    assert result.diagram_ir is None and "length" in (result.error or "").lower()


def test_the_pipeline_reevaluates_them_and_they_pass():
    ir = _ir()
    assert asyncio.run(run_ir_pipeline(ir, SVGRenderer())).svg
    report = verify_geometry_diagram(ir.model_dump())
    assert report["ok"] is True and [c["passed"] for c in report["checks"]] == [True, True, True]


def test_a_recorded_check_that_no_longer_holds_fails_the_pipeline():
    ir = _ir().model_copy(deep=True)
    ir.checks[0].expected = 7  # tampered after the script ran
    with pytest.raises(PipelineError, match="Geometric checks failed"):
        asyncio.run(run_ir_pipeline(ir, SVGRenderer()))


def test_recorded_checks_count_toward_the_op_cap():
    with new_builder_context() as builder:
        builder._op_cap = 3
        builder._add_check(DistanceEquals(seg="s", expected=1))
        builder._add_check(DistanceEquals(seg="s", expected=1))
        builder._add_check(DistanceEquals(seg="s", expected=1))
        with pytest.raises(OpCapExceededError):
            builder._add_check(DistanceEquals(seg="s", expected=1))


def test_a_script_without_asserts_has_no_checks():
    result = run_script("a = point(0, 0)\nb = point(1, 0)\ndraw(segment(a, b))", timeout_seconds=60)
    assert result.diagram_ir.checks == []

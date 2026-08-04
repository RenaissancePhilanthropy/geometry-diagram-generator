# tests/test_pydsl_builder.py
"""Tests for the pydsl Builder core: contextvar isolation and the op-count cap."""
import pytest

from geometry_diagrams.pydsl.builder import Builder, get_builder, new_builder_context


def test_get_builder_raises_outside_context():
    """Calling get_builder() with no active builder context is an error, not a silent None."""
    with pytest.raises(RuntimeError, match="no active Builder"):
        get_builder()


def test_new_builder_context_activates_and_resets():
    """Inside the context, get_builder() returns the same instance; outside, it's gone again."""
    with new_builder_context() as builder:
        assert get_builder() is builder
    with pytest.raises(RuntimeError):
        get_builder()


def test_sequential_builder_contexts_do_not_leak_ops():
    """Running two scripts back-to-back must not let ops from the first leak into the second.

    This is the concrete failure mode of an ambient-builder design: if the contextvar
    or the Builder's internal def-list were ever shared/reused across executions,
    script N+1's DiagramIR would silently include script N's geometry.
    """
    from geometry_diagrams.ir.ir import PointFixed

    with new_builder_context() as b1:
        b1._add(PointFixed(id="p1", x=0, y=0))
        ir1 = b1.build()

    with new_builder_context() as b2:
        b2._add(PointFixed(id="p2", x=1, y=1))
        ir2 = b2.build()

    assert [d.id for d in ir1.define] == ["p1"]
    assert [d.id for d in ir2.define] == ["p2"]


from geometry_diagrams.pydsl.builder import OpCapExceededError


def test_op_cap_raises_once_exceeded():
    """A script that records more ops than the cap gets a clean, catchable error."""
    from geometry_diagrams.ir.ir import PointFixed

    with new_builder_context(op_cap=3) as builder:
        for i in range(3):
            builder._add(PointFixed(id=f"p{i}", x=i, y=i))
        with pytest.raises(OpCapExceededError, match="more than 3 ops"):
            builder._add(PointFixed(id="p_overflow", x=99, y=99))

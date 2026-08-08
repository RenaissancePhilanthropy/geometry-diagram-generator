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


def test_build_emits_none_canvas_so_renderers_auto_size():
    """Builder.build() must not hardcode a fixed canvas — a small construction
    would render tiny and zoomed-out inside an unnecessarily large fixed
    -5..5 canvas, since both renderers only ever expand those bounds outward,
    never shrink them. canvas=None lets each renderer auto-size from the
    actual resolved geometry instead (both already support this)."""
    from geometry_diagrams.ir.ir import PointFixed

    with new_builder_context() as builder:
        builder._add(PointFixed(id="p1", x=0, y=0))
        ir = builder.build()
    assert ir.canvas is None


def test_resolve_point_returns_coordinates_for_a_literal_point():
    from geometry_diagrams.ir.ir import PointFixed

    with new_builder_context() as builder:
        builder._add(PointFixed(id="p1", x=3.0, y=4.0))
        builder._coord_floats["p1"] = (3.0, 4.0)
        assert builder._resolve_point("p1") == (3.0, 4.0)


def test_resolve_point_compiles_a_simple_derived_point():
    """A point_on(line, 0.5) has never had a value in _coord_floats before —
    _resolve_point must compile it via the real to_sympy pipeline."""
    from geometry_diagrams.ir.ir import LineThrough, PointFixed, PointOn, PointOnParam

    with new_builder_context() as builder:
        builder._add(PointFixed(id="a", x=0.0, y=0.0))
        builder._coord_floats["a"] = (0.0, 0.0)
        builder._add(PointFixed(id="b", x=4.0, y=0.0))
        builder._coord_floats["b"] = (4.0, 0.0)
        builder._add(LineThrough(id="line", p="a", q="b"))
        builder._add(PointOn(id="mid", on="line", how=PointOnParam(t=0.5)))

        x, y = builder._resolve_point("mid")
    assert x == pytest.approx(2.0)
    assert y == pytest.approx(0.0)
    assert builder._coord_floats["mid"] == pytest.approx((2.0, 0.0))


def test_resolve_point_caches_and_does_not_recompile():
    """A second _resolve_point call for an already-resolved point must not
    re-walk the def list — verified by corrupting builder._sym after the
    first resolve and confirming the cached value still comes back."""
    from geometry_diagrams.ir.ir import LineThrough, PointFixed, PointOn, PointOnParam

    with new_builder_context() as builder:
        builder._add(PointFixed(id="a", x=0.0, y=0.0))
        builder._coord_floats["a"] = (0.0, 0.0)
        builder._add(PointFixed(id="b", x=4.0, y=0.0))
        builder._coord_floats["b"] = (4.0, 0.0)
        builder._add(LineThrough(id="line", p="a", q="b"))
        builder._add(PointOn(id="mid", on="line", how=PointOnParam(t=0.5)))

        first = builder._resolve_point("mid")
        builder._coord_floats["mid"] = (999.0, 999.0)  # poison the cache
        second = builder._resolve_point("mid")
    assert second == (999.0, 999.0)  # came from cache, not recomputed
    assert first == pytest.approx((2.0, 0.0))


def test_resolve_point_raises_the_real_underlying_error():
    """Two parallel lines never meet — resolving the intersection must
    surface to_sympy's real IntersectionError, not a generic message."""
    from geometry_diagrams.ir.ir import LineThrough, PointFixed, PointIntersection
    from geometry_diagrams.ir.to_sympy import IntersectionError

    with new_builder_context() as builder:
        for pid, x, y in [("a", 0.0, 0.0), ("b", 4.0, 0.0), ("c", 0.0, 1.0), ("d", 4.0, 1.0)]:
            builder._add(PointFixed(id=pid, x=x, y=y))
            builder._coord_floats[pid] = (x, y)
        builder._add(LineThrough(id="l1", p="a", q="b"))
        builder._add(LineThrough(id="l2", p="c", q="d"))
        builder._add(PointIntersection(id="isect", obj1="l1", obj2="l2", pick=None))

        with pytest.raises(IntersectionError):
            builder._resolve_point("isect")


def test_pin_on_observe_makes_ambiguous_intersection_deterministic():
    """The load-bearing regression test for the bug a design review caught:
    an unpicked intersection with two candidates must resolve to the SAME
    point whether read early (via _resolve_point, partial sym) or via a
    full from-scratch compile_defs() at the very end, even when later defs
    would shift the auto-pick heuristic's centroid tiebreak if the
    intersection were re-resolved unpinned against the complete sym table.

    Setup: circle centered at origin, radius 5, intersected with the
    vertical line x=3 -> candidates (3, 4) and (3, -4), both within the
    default +/-5 canvas. With only {a=(0,0), l1=(3,0), l2=(3,1)} in scope,
    the centroid of existing points is (2, 0.33), closer to (3, 4) -> that
    candidate wins. Appending several points near (3, -4) afterward shifts
    the centroid enough that an UNPINNED re-resolve would flip to (3, -4)
    (asserted directly below as a control) -- pin-on-observe must prevent
    that flip for the actual builder-driven flow.
    """
    from geometry_diagrams.ir.ir import CircleCenterRadius, LineThrough, PickClosestTo, PointFixed, PointIntersection
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        builder._add(PointFixed(id="o", x=0.0, y=0.0))
        builder._coord_floats["o"] = (0.0, 0.0)
        builder._add(CircleCenterRadius(id="circ", center="o", radius=5))
        builder._add(PointFixed(id="l1", x=3.0, y=0.0))
        builder._coord_floats["l1"] = (3.0, 0.0)
        builder._add(PointFixed(id="l2", x=3.0, y=1.0))
        builder._coord_floats["l2"] = (3.0, 1.0)
        builder._add(LineThrough(id="line", p="l1", q="l2"))
        builder._add(PointIntersection(id="isect", obj1="circ", obj2="line", pick=None))

        previewed = builder._resolve_point("isect")
        assert previewed == pytest.approx((3.0, 4.0))

        isect_def = next(d for d in builder._defs if d.id == "isect")
        assert isinstance(isect_def.pick, PickClosestTo)

        # Simulate more script statements clustering near the OTHER candidate.
        for i in range(5):
            pid = f"extra{i}"
            builder._add(PointFixed(id=pid, x=3.0, y=-4.0))
            builder._coord_floats[pid] = (3.0, -4.0)

        final_ir = builder.build()
        final_sym = compile_defs(final_ir)
        final_point = final_sym["isect"]
    assert (float(final_point.x), float(final_point.y)) == pytest.approx((3.0, 4.0))

    # Control: the SAME final def list, but with isect's pick left as None
    # (i.e. never previewed/pinned), DOES flip to the other candidate --
    # proving this scenario really would have diverged without pinning.
    from geometry_diagrams.ir.ir import DiagramIR

    unpinned_defs = [d.model_copy() for d in final_ir.define]
    for d in unpinned_defs:
        if d.id == "isect":
            d.pick = None
    unpinned_ir = DiagramIR(define=unpinned_defs, render=[], canvas=None, styles={})
    unpinned_sym = compile_defs(unpinned_ir)
    unpinned_point = unpinned_sym["isect"]
    assert (float(unpinned_point.x), float(unpinned_point.y)) == pytest.approx((3.0, -4.0))


def test_pinned_hidden_defs_do_not_count_against_op_cap():
    from geometry_diagrams.ir.ir import CircleCenterRadius, LineThrough, PointFixed, PointIntersection

    with new_builder_context(op_cap=8) as builder:
        # 8 explicit _add calls below exactly fill the cap; the pin's hidden
        # PointFixed must not push this over and raise OpCapExceededError.
        builder._add(PointFixed(id="o", x=0.0, y=0.0))
        builder._coord_floats["o"] = (0.0, 0.0)
        builder._add(CircleCenterRadius(id="circ", center="o", radius=5))
        builder._add(PointFixed(id="l1", x=3.0, y=0.0))
        builder._coord_floats["l1"] = (3.0, 0.0)
        builder._add(PointFixed(id="l2", x=3.0, y=1.0))
        builder._coord_floats["l2"] = (3.0, 1.0)
        builder._add(LineThrough(id="line", p="l1", q="l2"))
        builder._add(PointIntersection(id="isect", obj1="circ", obj2="line", pick=None))
        assert builder.op_count == 6
        builder._resolve_point("isect")  # appends a hidden pin PointFixed

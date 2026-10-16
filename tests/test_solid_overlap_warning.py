"""Advisory warning: separately drawn solids whose screen boxes overlap.

Solids are not depth-sorted against each other, so overlapping solids paint
in draw order. ``DerivedRegistry.overlap_warnings`` (fed by each kind's
``screen_bounds`` hook) warns once per overlapping pair of DRAWN solids.
"""
from __future__ import annotations

import asyncio

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import REGISTRY
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import format_warnings_for_retry, run_ir_pipeline

PHRASE = "draw order is not depth order"


def _msg(a: str, b: str) -> str:
    return f"draw order is not depth order; solids '{a}' and '{b}' overlap on screen"


def _stack(sid: str, origin: str) -> ir.BlockStack:
    return ir.BlockStack(id=sid, origin=origin, heights=[[2, 1], [1, 3]])


def _prism(pid: str, origin: str) -> ir.RectangularPrism:
    return ir.RectangularPrism(id=pid, origin=origin, length=3, width=2, height=2)


def _diagram(solids: list, origins: dict[str, tuple[float, float]], draw: list[str]) -> ir.DiagramIR:
    points = [ir.PointFixed(id=k, x=x, y=y) for k, (x, y) in origins.items()]
    return ir.DiagramIR(define=[*points, *solids], render=[ir.Draw(obj=d) for d in draw])


def _overlap(diagram: ir.DiagramIR) -> list[str]:
    return REGISTRY.overlap_warnings(diagram, compile_defs(diagram))


def _run(diagram: ir.DiagramIR):
    return asyncio.run(run_ir_pipeline(diagram, SVGRenderer()))


NEAR = {"O": (0, 0), "Q": (1, 1)}
FAR = {"O": (0, 0), "Q": (30, 0)}


def test_two_stacks_overlap_warn_once():
    d = _diagram([_stack("S1", "O"), _stack("S2", "Q")], NEAR, ["S1", "S2"])
    assert _overlap(d) == [_msg("S1", "S2")]


def test_stack_and_prism_overlap():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, ["S1", "P"])
    assert _overlap(d) == [_msg("S1", "P")]


def test_two_prisms_overlap():
    d = _diagram([_prism("P1", "O"), _prism("P2", "Q")], NEAR, ["P1", "P2"])
    assert _overlap(d) == [_msg("P1", "P2")]


def test_three_solids_pairwise_in_authored_order():
    origins = {"O": (0, 0), "Q": (1, 0), "R": (0, 1)}
    d = _diagram([_prism("A", "O"), _stack("B", "Q"), _prism("C", "R")], origins, ["C", "A", "B"])
    assert _overlap(d) == [_msg("A", "B"), _msg("A", "C"), _msg("B", "C")]


def test_side_by_side_never_warns():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], FAR, ["S1", "P"])
    assert _overlap(d) == []


def test_lone_solid_never_warns():
    d = _diagram([_stack("S1", "O")], {"O": (0, 0)}, ["S1"])
    assert _overlap(d) == []


def test_undrawn_solid_does_not_participate():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, ["S1"])
    assert _overlap(d) == []
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, [])
    assert _overlap(d) == []


def test_touching_boxes_do_not_warn():
    # A prism's box is [ox, ox+dx_max] wide; place the second at exactly the
    # first's right edge and bottom-aligned.
    d1 = _diagram([_prism("P1", "O")], {"O": (0, 0)}, ["P1"])
    sym = compile_defs(d1)
    xmin, ymin, xmax, ymax = REGISTRY.screen_bounds(sym["P1"])
    d = _diagram([_prism("P1", "O"), _prism("P2", "Q")], {"O": (0, 0), "Q": (xmax - xmin, 0)}, ["P1", "P2"])
    assert _overlap(d) == []
    # Nudged inward by a positive amount: now they overlap.
    d = _diagram([_prism("P1", "O"), _prism("P2", "Q")], {"O": (0, 0), "Q": (xmax - xmin - 0.1, 0)}, ["P1", "P2"])
    assert _overlap(d) == [_msg("P1", "P2")]


def test_screen_bounds_matches_projected_points():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, ["S1", "P"])
    sym = compile_defs(d)
    prism = sym["P"]
    xs = [float(p.x) for p in prism.corners.values()]
    ys = [float(p.y) for p in prism.corners.values()]
    assert REGISTRY.screen_bounds(sym["P"]) == (min(xs), min(ys), max(xs), max(ys))
    st = sym["S1"]
    xs = [float(p.x) for p in st.lattice.values()]
    ys = [float(p.y) for p in st.lattice.values()]
    assert REGISTRY.screen_bounds(st) == (min(xs), min(ys), max(xs), max(ys))
    assert REGISTRY.screen_bounds(sym["O"]) is None


def test_warning_reaches_pipeline_result_and_retry_prompt():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, ["S1", "P"])
    result = _run(d)
    assert _msg("S1", "P") in result.warnings
    assert sum(PHRASE in w for w in result.warnings) == 1
    prompt = format_warnings_for_retry(result.warnings)
    assert f"- {_msg('S1', 'P')}" in prompt


def test_no_warning_without_overlap_in_pipeline():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], FAR, ["S1", "P"])
    assert not any(PHRASE in w for w in _run(d).warnings)


# --- "drawn" through any of the solid's own ids (faces, edges, top faces) --------

from geometry_diagrams.pydsl.sandbox import run_script  # noqa: E402
from geometry_diagrams.recipe.dsl import RecipeDSL  # noqa: E402
from geometry_diagrams.recipe.lower import lower_to_ir  # noqa: E402


def _custom(render: list, solids: list, origins=NEAR) -> ir.DiagramIR:
    points = [ir.PointFixed(id=k, x=x, y=y) for k, (x, y) in origins.items()]
    return ir.DiagramIR(define=[*points, *solids], render=render)


def _shaded_faces() -> list:
    """How every solids guidance surface builds a shaded prism: fill and draw
    the three visible face ids, never the prism id."""
    out: list = []
    for face in ("P_front", "P_right", "P_top"):
        out += [ir.Fill(obj=face, style="lightgray"), ir.Draw(obj=face)]
    return out


def test_face_filled_and_drawn_prism_overlapping_a_stack_warns_once():
    d = _custom([*_shaded_faces(), ir.Draw(obj="S1")], [_prism("P", "O"), _stack("S1", "Q")])
    assert _overlap(d) == [_msg("P", "S1")]


def test_single_face_fill_alone_counts_as_drawn():
    # A fill paints pixels (hoisted behind later ordered polygons), so a solid
    # whose only render op is a Fill of one of its face ids is on screen.
    d = _custom([ir.Fill(obj="P_front", style="lightgray"), ir.Draw(obj="S1")],
                [_prism("P", "O"), _stack("S1", "Q")])
    assert _overlap(d) == [_msg("P", "S1")]


def test_edge_only_draw_counts_as_drawn():
    d = _custom([ir.Draw(obj="P_e_000_100"), ir.Draw(obj="S1")], [_prism("P", "O"), _stack("S1", "Q")])
    assert _overlap(d) == [_msg("P", "S1")]


def test_stack_drawn_through_a_top_face_counts():
    d = _custom([ir.Draw(obj="P"), ir.Fill(obj="S1_top_0_0", style="red")],
                [_prism("P", "O"), _stack("S1", "Q")])
    assert _overlap(d) == [_msg("P", "S1")]


def test_labelled_or_centroid_targeted_solid_does_not_participate():
    labels = [
        ir.LabelFreeText(text="x", centroid_of="P"),
        ir.LabelSegment(seg="P_e_000_100", text="3"),
        ir.LabelPoint(p="P_v000", text="A") if hasattr(ir, "LabelPoint") else ir.LabelFreeText(text="y", centroid_of="P"),
    ]
    d = _custom([*labels, ir.Draw(obj="S1")], [_prism("P", "O"), _stack("S1", "Q")])
    assert _overlap(d) == []


def test_pair_reported_once_when_drawn_through_several_ids_and_its_own():
    d = _custom([ir.Draw(obj="P"), *_shaded_faces(), ir.Draw(obj="S1"), ir.Fill(obj="S1_top_0_0", style="red")],
                [_prism("P", "O"), _stack("S1", "Q")])
    assert _overlap(d) == [_msg("P", "S1")]


def test_pydsl_script_following_the_python_full_guidance_warns():
    script = (
        "o = point(0, 0)\n"
        "q = point(1, 1)\n"
        "box = prism(o, 3, 2, 2)\n"
        "for name in ('front', 'right', 'top'):\n"
        "    fill(box.face(name), 'lightgray')\n"
        "    draw(box.face(name))\n"
        "blocks = stack(q, heights=[[2, 1], [1, 3]])\n"
        "draw(blocks)\n"
    )
    res = run_script(script, timeout_seconds=60, features={"solids"})
    assert res.error is None, res.error
    sym = compile_defs(res.diagram_ir)
    warnings = REGISTRY.overlap_warnings(res.diagram_ir, sym)
    assert len(warnings) == 1 and PHRASE in warnings[0]
    ids = [s.id for s in res.diagram_ir.define if REGISTRY.screen_bounds(sym[s.id]) is not None]
    assert all(f"'{i}'" in warnings[0] for i in ids) and len(ids) == 2


def test_recipe_following_the_catalog_guidance_warns():
    dsl = RecipeDSL.model_validate({
        "construction": [
            {"op": "point", "id": "O", "coords": [0, 0]},
            {"op": "point", "id": "Q", "coords": [1, 1]},
            {"op": "prism", "id": "P", "origin": "O", "length": 3, "width": 2, "height": 2, "visible": False},
            {"op": "stack", "id": "S", "origin": "Q", "heights": [[2, 1], [1, 3]]},
        ],
        "annotations": {"auto_draw_all": False, "draws": [
            {"obj": "P_front"}, {"obj": "P_right"}, {"obj": "P_top"}, {"obj": "S"}]},
    })
    d = lower_to_ir(dsl)
    assert _overlap(d) == [_msg("P", "S")]


def test_render_view_rejects_a_non_diagram():
    import pytest
    from geometry_diagrams.ir.derived import render_view

    class Fake:
        def model_copy(self, update):  # the old duck-typed fallback would call this
            return self

    with pytest.raises(TypeError, match="render_view needs a DiagramIR"):
        render_view(Fake(), {"render": []})

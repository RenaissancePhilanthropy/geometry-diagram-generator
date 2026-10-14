"""Effective-definitions view: authored definitions plus the definitions a
registered kind synthesizes.

Exercised with a TEST-ONLY registration on the ``triangle`` kind (no
production kind synthesizes anything yet). Like the prism it stands in for,
the test kind owns a derived point (``{id}_tkc``, the centroid) and
synthesizes definitions that reference it: one Segment (``{id}_tkside``,
from vertex a to the centroid) and one Polygon (``{id}_tkface``, a, b and the
centroid).

The view must reach every entry point (shared pipeline, facade query tool,
eval viewer re-render, incremental builder) and must stay invisible to the
consumers that read only what was authored (eval IR diagnostics, edit
diagnostics, auto-checks), and the authored IR must never be rewritten.
"""
from __future__ import annotations

import asyncio
import json
import xml.etree.ElementTree as ET

import pytest
import sympy.geometry as spg

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.auto_checks import generate_auto_checks
from geometry_diagrams.ir.derived import REGISTRY, DerivedConstruction, effective_defs
from geometry_diagrams.ir.edit_diagnostics import check_edit_locality
from geometry_diagrams.ir.render_util import build_entity_manifest
from geometry_diagrams.ir.renderer import SVGRenderer, TikZRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from tests.availability import renderer_available


# ---------------------------------------------------------------------------
# The test-only registered kind
# ---------------------------------------------------------------------------

def _centroid_id(stmt: ir.Triangle) -> str:
    return f"{stmt.id}_tkc"


def _register_centroid(stmt: ir.Triangle, obj, sym: dict) -> None:
    if isinstance(obj, spg.Polygon) and _centroid_id(stmt) not in sym:
        sym[_centroid_id(stmt)] = obj.centroid


def _synthesize(stmt: ir.Triangle) -> list[ir.DefStmt]:
    c = _centroid_id(stmt)
    return [
        ir.Segment(id=f"{stmt.id}_tkside", a=stmt.a, b=c),
        ir.Polygon(id=f"{stmt.id}_tkface", points=[stmt.a, stmt.b, c]),
    ]


@pytest.fixture
def test_kind(monkeypatch):
    entry = DerivedConstruction(
        kind="triangle",
        id_forms=("{id}_tkc", "{id}_tkside", "{id}_tkface"),
        owned_ids=lambda stmt: [_centroid_id(stmt)],
        register=_register_centroid,
        synthesize=_synthesize,
    )
    monkeypatch.setitem(REGISTRY._by_kind, "triangle", entry)
    return entry


def _diagram(c=(0, 6)) -> ir.DiagramIR:
    # P is authored BEFORE the triangle and references the synthesized
    # segment: dependency ordering must still compile it after T.
    return ir.DiagramIR(
        define=[
            ir.PointOn(id="P", on="T_tkside", how=ir.PointOnParam(t=0.5)),
            ir.PointFixed(id="A", x=0, y=0),
            ir.PointFixed(id="B", x=6, y=0),
            ir.PointFixed(id="C", x=c[0], y=c[1]),
            ir.Triangle(id="T", a="A", b="B", c="C"),
            ir.PointMidpoint(id="M", p="A", q="T_tkc"),
        ],
        render=[
            ir.Fill(obj="T_tkface"),
            ir.Draw(obj="T"),
            ir.Draw(obj="T_tkside"),
            ir.DrawPoints(points=["A", "B", "C", "P"]),
        ],
    )


def _ir_ids(svg: str) -> set[str]:
    root = ET.fromstring(svg)
    return {el.get("data-ir-id") for el in root.iter() if el.get("data-ir-id")}


# ---------------------------------------------------------------------------
# The view itself
# ---------------------------------------------------------------------------

def test_view_is_authored_plus_synthesized(test_kind):
    diagram = _diagram()
    authored = [d.id for d in diagram.define]
    ids = [d.id for d in effective_defs(diagram)]
    assert [i for i in ids if i in authored] == authored
    assert sorted(set(ids) - set(authored)) == ["T_tkface", "T_tkside"]
    assert len(ids) == len(authored) + 2


def test_view_is_deterministic(test_kind):
    a, b = _diagram(), _diagram()
    assert effective_defs(a) == effective_defs(b)
    assert effective_defs(a) == effective_defs(a)


def test_view_is_idempotent(test_kind):
    diagram = _diagram()
    once = effective_defs(diagram)
    twice = effective_defs(ir.DiagramIR(define=once))
    assert once == twice


def test_authored_definition_wins_over_a_synthesized_one(test_kind):
    diagram = _diagram()
    diagram.define.append(ir.Segment(id="T_tkside", a="A", b="B"))
    view = effective_defs(diagram)
    sides = [d for d in view if d.id == "T_tkside"]
    assert sides == [ir.Segment(id="T_tkside", a="A", b="B")]


def test_kinds_without_synthesis_contribute_nothing():
    diagram = _diagram()
    diagram.define.append(ir.PolygonExterior(id="sq", a="A", b="B", ref="C", sides=4))
    assert effective_defs(diagram) == list(diagram.define)


# ---------------------------------------------------------------------------
# Entry point 1: the shared deterministic pipeline
# ---------------------------------------------------------------------------

def test_pipeline_compiles_queries_and_renders_synthesized_defs(test_kind):
    diagram = _diagram()
    before = diagram.model_copy(deep=True)

    result = asyncio.run(run_ir_pipeline(diagram, renderer=SVGRenderer()))

    sym = result.sym_full
    assert isinstance(sym["T_tkside"], spg.Segment)
    assert isinstance(sym["T_tkface"], spg.Polygon)
    # P sits halfway along A -> centroid (2, 2).
    assert result.sym_table["P"] == pytest.approx((1.0, 1.0))
    assert {"T_tkside", "T_tkface"} <= _ir_ids(result.svg)

    # Authored IR is untouched.
    assert diagram == before
    assert [d.id for d in diagram.define] == [d.id for d in before.define]


def test_queries_answer_on_synthesized_defs(test_kind):
    from geometry_diagrams.strategies.structured import dispatch_query

    sym = compile_defs(_diagram())
    length = json.loads(dispatch_query(sym, "length", {"segment": "T_tkside"}))
    assert length["length"] == pytest.approx(8 ** 0.5)
    area = json.loads(dispatch_query(sym, "area", {"id": "T_tkface"}))
    assert area["area"] == pytest.approx(6.0)


def test_compile_and_render_do_not_mutate_authored_ir(test_kind):
    diagram = _diagram()
    before = diagram.model_copy(deep=True)
    sym = compile_defs(diagram)
    SVGRenderer().render(diagram, sym)
    ir_to_tikz(diagram, sym)
    assert diagram == before


def test_tikz_emits_synthesized_defs(test_kind):
    diagram = _diagram()
    tikz = ir_to_tikz(diagram, compile_defs(diagram))
    assert "T_tkc" in tikz


@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
def test_tikz_smoke_through_pipeline(test_kind):
    result = asyncio.run(run_ir_pipeline(_diagram(), renderer=TikZRenderer()))
    assert "<svg" in result.svg


# ---------------------------------------------------------------------------
# Entry point 2: the stateless facade query tool
# ---------------------------------------------------------------------------

def _triangle_dsl() -> dict:
    from geometry_diagrams.recipe.dsl import RecipeDSL, TriangleOp

    return RecipeDSL(construction=[
        TriangleOp(id="T", vertices=["A", "B", "C"], spec={"side_AB": 3, "side_BC": 4, "side_CA": 5}),
    ]).model_dump()


def test_facade_query_tool_sees_synthesized_defs(test_kind):
    from geometry_diagrams.facade import query_geometry_diagram

    result = json.loads(query_geometry_diagram(_triangle_dsl(), "length", {"segment": "T_tkside"}))
    assert "error" not in result
    assert result["length"] > 0
    objects = json.loads(query_geometry_diagram(_triangle_dsl(), "list_objects"))
    assert "T_tkface" in json.dumps(objects)


# ---------------------------------------------------------------------------
# Entry point 3: the eval viewer's re-render path
# ---------------------------------------------------------------------------

class _FakeRequest:
    def __init__(self, body: dict) -> None:
        self._body = body

    async def json(self) -> dict:
        return self._body


def _viewer_compile_ir(body: dict) -> tuple[int, dict]:
    from evals.eval_viewer import compile_ir

    response = asyncio.run(compile_ir(_FakeRequest(body)))
    return response.status_code, json.loads(response.body)


def test_eval_viewer_rerender_sees_synthesized_defs(test_kind):
    status, payload = _viewer_compile_ir({"diagram_ir": _diagram().model_dump(mode="json")})
    assert status == 200, payload
    assert {"T_tkside", "T_tkface"} <= _ir_ids(payload["svg"])


@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
def test_eval_viewer_tikz_smoke(test_kind):
    status, payload = _viewer_compile_ir(
        {"diagram_ir": _diagram().model_dump(mode="json"), "renderer": "tikz"}
    )
    assert status == 200, payload
    assert "<svg" in payload["svg"]


# ---------------------------------------------------------------------------
# Entry point 4: the pydsl incremental builder
# ---------------------------------------------------------------------------

def test_incremental_builder_resolves_point_on_synthesized_segment(test_kind):
    from geometry_diagrams.pydsl.builder import get_builder, new_builder_context

    with new_builder_context():
        b = get_builder()
        for d in _diagram().define[1:]:
            b._add(d)
        b._add(ir.PointOn(id="P", on="T_tkside", how=ir.PointOnParam(t=0.5)))
        mid_script = b._resolve_point("P")
        diagram = b.build()
    p = compile_defs(diagram)["P"]
    assert mid_script == pytest.approx((float(p.x), float(p.y)))
    assert mid_script == pytest.approx((1.0, 1.0))


# ---------------------------------------------------------------------------
# Authored-only consumers
# ---------------------------------------------------------------------------

def test_auto_checks_ignore_synthesized_segments(test_kind):
    # M is the midpoint of A and the centroid; the synthesized T_tkside
    # joins exactly those points. Auto-checks only look for an AUTHORED
    # segment, so none is generated.
    assert generate_auto_checks(_diagram()) == []


def test_eval_ir_diagnostics_ignore_synthesized_defs(monkeypatch):
    from evals.ir_diagnostics import classify_ir

    entry = DerivedConstruction(
        kind="triangle", id_forms=("{id}_tkmid",), owned_ids=lambda s: [],
        register=lambda s, o, sym: None,
        synthesize=lambda s: [ir.PointMidpoint(id=f"{s.id}_tkmid", p=s.a, q=s.b)],
    )
    monkeypatch.setitem(REGISTRY._by_kind, "triangle", entry)
    diagram = _diagram()
    assert any(d.kind == "point_midpoint" and d.id == "T_tkmid" for d in effective_defs(diagram))
    assert classify_ir(diagram).primitive_count == 1  # only the authored M


def test_eval_polygon_count_ignores_synthesized_polygons(test_kind):
    from evals.run import _run_structural_checks

    checks = [{"name": "polys", "type": "polygon_count", "args": {"min": 2}}]
    result = _run_structural_checks(checks, _diagram().model_dump(mode="json"), None)
    assert result["polys"]["passed"] is False
    assert "found 1" in result["polys"]["message"]


def test_entity_manifest_grounds_names_bound_to_synthesized_ids(test_kind):
    diagram = _diagram()
    sym = compile_defs(diagram)
    manifest = build_entity_manifest(diagram, sym, {"side": "T_tkside", "face": "T_tkface"})
    named = {e["name"]: e for e in manifest["named"]}
    assert named["side"]["type"] == "segment"
    assert named["face"]["type"] == "polygon"
    anon_types = [e["type"] for e in manifest["anonymous"]]
    assert "fill" in anon_types


def test_edit_diagnostics_attribute_synthesized_entities_to_their_owner(test_kind):
    # Moving C moves the centroid and therefore the synthesized side; the
    # diagnostic must treat that as downstream of the edit (via the owner),
    # not as an unexpected move. B is untouched and stays put.
    old_ir, new_ir = _diagram(c=(0, 6)), _diagram(c=(3, 9))
    names = {"side": "T_tkside", "face": "T_tkface", "b": "B", "c": "C"}
    old_sym, new_sym = compile_defs(old_ir), compile_defs(new_ir)
    old_manifest = build_entity_manifest(old_ir, old_sym, names)
    new_manifest = build_entity_manifest(new_ir, new_sym, names)

    diag = check_edit_locality(old_manifest, old_ir, old_sym, new_manifest, new_ir, new_sym)

    assert diag.matched_names == set(names)
    assert {"side", "face"} <= diag.downstream_names
    assert diag.violations == []


def test_linear_pair_resolution_counts_synthesized_segments(test_kind):
    from geometry_diagrams.ir.checks import check_render_angles

    diagram = _diagram()
    # Drop M (its midpoint pair would also connect A and the centroid).
    diagram.define = [d for d in diagram.define if d.id != "M"]
    # A-B is a triangle side; A-centroid exists only as the synthesized
    # T_tkside. Structural resolution alone (no sym) must accept it.
    diagram.render.append(ir.MarkAngles(angles=[ir.AngleSpec(a="B", o="A", b="T_tkc")]))
    assert check_render_angles(diagram) == []

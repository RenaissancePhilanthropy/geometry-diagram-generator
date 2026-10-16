"""Post-review fixes: eager degenerate-view validation (typed compile error)
and owner attribution for errors raised in synthesized definitions."""
from __future__ import annotations

import asyncio

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.prism import projection_for
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.pydsl import api
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline


def _stack_diagram(**kw) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), ir.BlockStack(id="S", origin="O", heights=[[1]], **kw)],
        render=[ir.Draw(obj="S")],
    )


def _prism_diagram(**kw) -> ir.DiagramIR:
    fields = dict(id="P", origin="O", length=2, width=2, height=2)
    fields.update(kw)
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), ir.RectangularPrism(**fields)],
        render=[ir.Draw(obj="P")],
    )


_DEGENERATE = [
    {"depth_scale": 1e-300},
    {"depth_angle": 1e-300},
    {"depth_angle": 1e-300, "depth_scale": 1e-300},
]


@pytest.mark.parametrize("kw", _DEGENERATE)
def test_projection_for_rejects_a_degenerate_view_with_a_helpful_message(kw):
    with pytest.raises(ValueError) as exc:
        projection_for("oblique", "right", kw.get("depth_angle"), kw.get("depth_scale"))
    msg = str(exc.value)
    assert "depth_scale" in msg and "depth_angle" in msg and "edge-on" in msg


@pytest.mark.parametrize("kw", _DEGENERATE)
@pytest.mark.parametrize("make,owner", [(_stack_diagram, "S"), (_prism_diagram, "P")])
def test_degenerate_view_is_a_compile_time_typed_error(make, owner, kw):
    with pytest.raises(IRCompileError) as exc:
        compile_defs(make(**kw))
    assert exc.value.def_id == owner and "depth_scale" in str(exc.value)


@pytest.mark.parametrize("make", [_stack_diagram, _prism_diagram])
def test_pipeline_raises_typed_error_not_valueerror(make):
    with pytest.raises(IRCompileError):
        asyncio.run(run_ir_pipeline(make(depth_scale=1e-300), SVGRenderer()))


def test_pydsl_stack_degenerate_view_is_a_script_error_for_the_retry_loop():
    from geometry_diagrams.pydsl.sandbox import run_script

    res = run_script(
        "o = point(0, 0)\ns = stack(o, heights=[[1]], depth_scale=1e-300)\ndraw(s)\n",
        timeout_seconds=60, features=frozenset({"solids"}),
    )
    assert res.diagram_ir is None
    assert res.error is not None and "depth_scale" in str(res.error)
    assert "ValueError" not in str(res.error).split("depth_scale")[0][:80]


def test_pydsl_builder_degenerate_view_raises_typed_error():
    with new_builder_context():
        with pytest.raises(IRCompileError):
            api.stack(api.point(0, 0), heights=[[1]], depth_scale=1e-300)


@pytest.mark.parametrize("angle", [10, 45, 89])
@pytest.mark.parametrize("scale", [0.05, 0.5, 3])
def test_ordinary_views_still_compile(angle, scale):
    compile_defs(_stack_diagram(depth_angle=angle, depth_scale=scale))
    compile_defs(_prism_diagram(depth_angle=angle, depth_scale=scale))


# --- item 2: owner attribution for synthesized definitions -------------------------

def test_tiny_prism_error_names_the_prism_not_a_derived_face():
    with pytest.raises(IRCompileError) as exc:
        compile_defs(_prism_diagram(length=1e-300))
    assert exc.value.def_id == "P"
    assert "_front" in str(exc.value) or "derived" in str(exc.value)  # detail kept


def test_synthesized_definition_error_reports_its_owner_generic_mechanism(monkeypatch):
    """Provoke a failure in a synthesized def of a different derived kind."""
    from geometry_diagrams.ir import to_sympy

    original = to_sympy._compile_one

    def boom(stmt, *a, **k):
        if getattr(stmt, "_synthesized_by", None):
            raise IRCompileError(stmt.id, "boom detail")
        return original(stmt, *a, **k)

    monkeypatch.setattr(to_sympy, "_compile_one", boom)
    d = ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), ir.BlockStack(id="S", origin="O", heights=[[1]])],
        render=[],
    )
    with pytest.raises(IRCompileError) as exc:
        compile_defs(d)
    assert exc.value.def_id == "S"
    assert "boom detail" in str(exc.value) and "of 'S'" in str(exc.value)


def test_authored_id_errors_are_unchanged():
    d = ir.DiagramIR(define=[ir.PointMidpoint(id="M", p="A", q="B")], render=[])
    with pytest.raises(IRCompileError) as exc:
        compile_defs(d)
    assert exc.value.def_id == "M" and "derived" not in str(exc.value)


# --- item 3/4 wording ------------------------------------------------------------

def test_prism_guidance_does_not_claim_fill_accepts_the_prism_id():
    from geometry_diagrams.recipe.catalog import dsl_docs_for

    docs = dsl_docs_for(frozenset({"solids"}))
    assert "Fill/label/draw accept the prism id" not in docs
    assert "fill accepts face ids but not the prism id" in " ".join(docs.split())


def test_skew_warnings_do_not_claim_the_solid_is_drawn():
    for diagram in (_stack_diagram(), _prism_diagram()):
        diagram.canvas = ir.Canvas(aspect=2)
        res = asyncio.run(run_ir_pipeline(diagram, SVGRenderer()))
        skew = [w for w in res.warnings if "unequal axis scales" in w]
        assert skew and all("is drawn on a canvas" not in w for w in skew)

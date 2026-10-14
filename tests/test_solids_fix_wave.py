"""Regression tests for the solids final-review fix wave (items A-E): typed
style-conflict error, recipe segment reuse of prism edges, pre-assert stub
features, the unit_cubes not-drawn warning and guidance, and non-finite prism
dimensions."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import effective_diagram, lower_render
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline


def _prism(**overrides) -> ir.RectangularPrism:
    fields = dict(id="P", origin="O", length=4, width=3, height=2)
    fields.update(overrides)
    return ir.RectangularPrism(**fields)


def _diagram(prism=None, render=None, styles=None) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), prism or _prism()],
        render=render if render is not None else [ir.Draw(obj="P")],
        styles=styles or {},
    )


# --- A: style-name conflict is a typed, retry-feedable error ---------------

_CONFLICT = {"__P_hidden": {"color": "red"}}


def test_lowering_style_conflict_is_an_ir_compile_error_naming_the_style():
    diagram = _diagram(styles=_CONFLICT)
    with pytest.raises(IRCompileError) as exc:
        lower_render(effective_diagram(diagram))
    assert exc.value.def_id == "P"
    assert "__P_hidden" in str(exc.value)


@pytest.mark.asyncio
async def test_lowering_style_conflict_reaches_the_shared_pipeline_typed():
    diagram = _diagram(styles=_CONFLICT)
    with pytest.raises(IRCompileError):
        await run_ir_pipeline(diagram, SVGRenderer())

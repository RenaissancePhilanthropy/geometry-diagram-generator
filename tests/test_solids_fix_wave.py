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


# --- B: a recipe `segment` op along one prism edge reuses that edge ---------

from geometry_diagrams.ir.to_sympy import compile_defs  # noqa: E402
from geometry_diagrams.ir.to_svg import ir_to_svg  # noqa: E402
from geometry_diagrams.recipe.dsl import RecipeDSL  # noqa: E402
from geometry_diagrams.recipe.lower import lower_to_ir  # noqa: E402


def _recipe(extra_ops=(), annotations=None, prism=None) -> RecipeDSL:
    p = {"op": "prism", "id": "P", "origin": "O", "length": 4, "width": 3, "height": 2}
    p.update(prism or {})
    return RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]}, p, *extra_ops],
        "annotations": annotations or {},
    })


def _svg(diagram: ir.DiagramIR) -> str:
    return ir_to_svg(diagram, compile_defs(diagram))


def _segments_between(diagram, p, q):
    return [d for d in diagram.define if isinstance(d, ir.Segment) and {d.a, d.b} == {p, q}]


_EDGE_SEG = {"op": "segment", "id": "s", "endpoints": ["P_v000", "P_v010"]}


def test_segment_op_along_a_prism_edge_adds_no_segment_and_no_stroke():
    with_seg = lower_to_ir(_recipe([_EDGE_SEG]))
    without = lower_to_ir(_recipe())
    assert _segments_between(with_seg, "P_v000", "P_v010") == []
    assert not any(isinstance(r, ir.Draw) and r.obj == "s" for r in with_seg.render)
    assert with_seg.render == without.render
    assert _svg(with_seg) == _svg(without)


def test_segment_op_along_an_edge_still_resolves_when_another_op_references_it():
    # Intersection of the edge-segment s (bottom front edge, y=0) with a line.
    d = lower_to_ir(_recipe([
        {"op": "segment", "id": "s", "endpoints": ["P_v000", "P_v100"]},
        {"op": "point", "id": "Q1", "coords": [2, -1]},
        {"op": "point", "id": "Q2", "coords": [2, 1]},
        {"op": "line_through", "id": "L", "points": ["Q1", "Q2"]},
        {"op": "intersection", "id": "X", "of": ["s", "L"]},
    ]))
    sym = compile_defs(d)
    assert (float(sym["X"].x), float(sym["X"].y)) == pytest.approx((2.0, 0.0))
    assert not any(isinstance(r, ir.Draw) and r.obj == "s" for r in d.render)


def test_explicit_draw_of_an_edge_segment_op_draws_the_prism_edge():
    d = lower_to_ir(_recipe([_EDGE_SEG], annotations={
        "auto_draw_all": False,
        "draws": [{"obj": "P"}, {"obj": "s", "style": "red"}],
    }))
    draws = [(r.obj, r.style) for r in d.render if isinstance(r, ir.Draw)]
    assert ("P_e_000_010", "red") in draws
    assert not any(obj == "s" for obj, _ in draws)
    compile_defs(d)


def test_edge_segment_op_is_drawn_as_the_edge_when_its_prism_is_hidden():
    d = lower_to_ir(_recipe([_EDGE_SEG], prism={"visible": False}))
    draws = [r.obj for r in d.render if isinstance(r, ir.Draw)]
    assert "P" not in draws and "P_e_000_010" in draws


def test_diagonal_and_non_prism_segment_ops_are_unchanged():
    d = lower_to_ir(_recipe([
        {"op": "segment", "id": "diag", "endpoints": ["P_v000", "P_v111"]},
        {"op": "point", "id": "A", "coords": [6, 0]},
        {"op": "point", "id": "B", "coords": [7, 1]},
        {"op": "segment", "id": "ab", "endpoints": ["A", "B"]},
    ]))
    segs = {s.id: (s.a, s.b) for s in d.define if isinstance(s, ir.Segment)}
    assert segs == {"diag": ("P_v000", "P_v111"), "ab": ("A", "B")}
    draws = [r.obj for r in d.render if isinstance(r, ir.Draw)]
    assert "diag" in draws and "ab" in draws


# --- C: the python_full pre-assert step sees the enabled feature groups -----

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from geometry_diagrams.ir import pre_assert_filter as paf  # noqa: E402
from geometry_diagrams.strategies import pre_assert_step as pas  # noqa: E402

SOLIDS = frozenset({"solids"})
_SOLID_ASSERTS = ("assert_volume", "assert_true_length")


def test_pre_assert_vocabulary_includes_solid_asserts_only_with_solids_on():
    on = pas.build_assert_vocabulary_block(features=SOLIDS)
    for name in _SOLID_ASSERTS:
        assert f"def {name}(" in on
        assert f"def {name}(" not in pas.build_assert_vocabulary_block()
    assert pas.build_pre_step_system_prompt(features=SOLIDS) != pas.build_pre_step_system_prompt()
    assert "def assert_volume(" in pas.build_pre_step_system_prompt(features=SOLIDS)


def test_pre_assert_solids_off_vocabulary_and_prompt_are_unchanged():
    from geometry_diagrams.pydsl.stub import generate_stub

    expected = "\n".join(l for l in generate_stub().splitlines() if l.startswith("def assert_"))
    assert pas.build_assert_vocabulary_block() == expected
    assert pas.build_assert_vocabulary_block(features=frozenset()) == expected
    assert pas.build_pre_step_system_prompt(features=frozenset()) == pas.build_pre_step_system_prompt()


def test_pre_filter_api_name_validation_accepts_solid_asserts_only_with_solids_on():
    text = "assert_volume(P, 24)\nassert_true_length(A, B, 5)\n"
    assert paf.find_unknown_assert_names(text) == list(_SOLID_ASSERTS)
    assert paf.find_unknown_assert_names(text, features=SOLIDS) == []
    assert "assert_volume" in paf.build_name_correction_message(["assert_x"], features=SOLIDS)
    assert "assert_volume" not in paf.build_name_correction_message(["assert_x"])
    parsed = pas.parse_proposal_text("assert_volume(P, 24)\n", features=SOLIDS)
    assert parsed.checks[0].unresolved_name is None
    assert pas.parse_proposal_text("assert_volume(P, 24)\n").checks[0].unresolved_name == "assert_volume"


@pytest.mark.asyncio
async def test_propose_and_filter_checks_uses_the_enabled_features_end_to_end():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="assert_volume(P, 24)\n"))
    with patch("geometry_diagrams.strategies.pre_assert_step.get_chat_model", return_value=llm):
        result = await pas.propose_and_filter_checks(
            "a 2 by 3 by 4 box", "anthropic:claude-sonnet-4-6", features=SOLIDS,
        )
    assert result.retried is False  # assert_volume is a real name with solids on
    system_prompt = llm.ainvoke.call_args.args[0][0].content
    assert "def assert_volume(" in str(system_prompt)


@pytest.mark.asyncio
async def test_python_full_pre_assert_node_passes_the_strategy_features():
    from geometry_diagrams.strategies import python_full

    fake = pas.PreAssertProposalResult(
        raw_response="", retried=False, filtered_checks=[], unparsed_lines=[], advisory_text="",
    )
    with patch.object(python_full, "propose_and_filter_checks", new=AsyncMock(return_value=fake)) as m:
        await python_full._pre_assert_step_node({
            "prompt": "a box", "model_id": "anthropic:claude-sonnet-4-6",
            "metadata": MagicMock(), "features": SOLIDS,
        })
    assert m.await_args.kwargs.get("features") == SOLIDS


# --- D: unit_cubes prisms: guidance says draw the prism id; warn when not -----

_FACES = [ir.Draw(obj=f"P_{f}") for f in ("front", "right", "top")]


def _unit_cubes_warnings(render, **prism_overrides) -> list[str]:
    warnings: list[str] = []
    diagram = _diagram(prism=_prism(**prism_overrides), render=render)
    lower_render(effective_diagram(diagram), warnings)
    return [w for w in warnings if "unit_cubes" in w]


@pytest.mark.asyncio
async def test_unit_cubes_prism_drawn_face_by_face_warns_through_the_pipeline():
    diagram = _diagram(prism=_prism(unit_cubes=True), render=list(_FACES))
    result = await run_ir_pipeline(diagram, SVGRenderer())
    matching = [w for w in result.warnings if "unit_cubes" in w]
    assert len(matching) == 1
    assert "'P'" in matching[0] and "draw the prism id" in matching[0]
    assert "gridlines" in matching[0]


def test_unit_cubes_never_drawn_warns_in_lower_render():
    assert len(_unit_cubes_warnings(list(_FACES), unit_cubes=True)) == 1
    assert len(_unit_cubes_warnings([], unit_cubes=True)) == 1


def test_no_unit_cubes_warning_when_the_prism_id_is_drawn_or_not_unit_cubes():
    assert _unit_cubes_warnings([ir.Draw(obj="P")], unit_cubes=True) == []
    assert _unit_cubes_warnings([ir.Draw(obj="P"), *_FACES], unit_cubes=True) == []
    assert _unit_cubes_warnings(list(_FACES)) == []
    assert _unit_cubes_warnings([]) == []


def _solids_prompts() -> dict[str, str]:
    from geometry_diagrams.recipe.catalog import dsl_docs_for
    from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions
    from geometry_diagrams.strategies.instructions_structured import build_structured_instructions

    return {
        "recipe": dsl_docs_for(SOLIDS),
        "python_full": build_python_full_instructions(features=SOLIDS),
        "structured": build_structured_instructions(SOLIDS),
    }


@pytest.mark.parametrize("surface", ["recipe", "python_full", "structured"])
def test_solids_guidance_says_unit_cubes_prisms_draw_the_prism_id(surface):
    text = " ".join(_solids_prompts()[surface].replace("`", "").split())  # unwrap lines
    assert "For unit_cubes prisms, draw the prism id" in text
    assert "gridlines" in text
    assert "non-unit-cube" in text

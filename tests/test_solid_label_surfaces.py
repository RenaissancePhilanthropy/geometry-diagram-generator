"""Recipe, python and structured surfaces for the solid label fields
(prism length/width/height/base_area labels, stack count_label) and the
gated guidance that teaches them (solid-labels ticket 04)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.pydsl.stub import generate_stub
from geometry_diagrams.recipe.catalog import DSL_DOCS, PRISM_EXAMPLES, STACK_EXAMPLES, dsl_docs_for
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.recipe.lower import lower_to_ir
from geometry_diagrams.strategies import instructions_python_full as ipf
from geometry_diagrams.strategies import instructions_structured as ins
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from geometry_diagrams.strategies.structured import StructureStrategy

SOLIDS = frozenset({"solids"})
TESTS = Path(__file__).parent
PRISM_FIELDS = ("length_label", "width_label", "height_label", "base_area_label")
TEXTS = {"length_label": "4 ft", "width_label": "3 ft", "height_label": "2 ft",
         "base_area_label": "12 sq ft"}


def _run(ir_diagram):
    return asyncio.run(run_ir_pipeline(ir_diagram, SVGRenderer()))


def _count(svg: str, text: str) -> int:
    return svg.count(f'data-label-text="{text}"')


# --- recipe ------------------------------------------------------------------------

def _recipe(op: dict) -> RecipeDSL:
    return RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]}, op],
        "annotations": {}, "checks": []})


PRISM_OP = {"op": "prism", "id": "P", "origin": "O", "length": 4, "width": 3, "height": 2}
STACK_OP = {"op": "stack", "id": "S", "origin": "O", "heights": [[1, 2], [3, 0]]}


def test_recipe_prism_fields_lower_into_the_ir_definition():
    d = lower_to_ir(_recipe({**PRISM_OP, **TEXTS}))
    p = next(x for x in d.define if isinstance(x, ir.RectangularPrism))
    for f in PRISM_FIELDS:
        assert getattr(p, f) == TEXTS[f]


def test_recipe_stack_count_label_lowers_into_the_ir_definition():
    d = lower_to_ir(_recipe({**STACK_OP, "count_label": "6 cubes"}))
    s = next(x for x in d.define if isinstance(x, ir.BlockStack))
    assert s.count_label == "6 cubes"


def test_recipe_fields_default_to_none():
    p = next(x for x in lower_to_ir(_recipe(PRISM_OP)).define if isinstance(x, ir.RectangularPrism))
    s = next(x for x in lower_to_ir(_recipe(STACK_OP)).define if isinstance(x, ir.BlockStack))
    assert all(getattr(p, f) is None for f in PRISM_FIELDS) and s.count_label is None


@pytest.mark.parametrize("op,field", [(PRISM_OP, f) for f in PRISM_FIELDS] + [(STACK_OP, "count_label")])
def test_recipe_empty_label_is_rejected(op, field):
    with pytest.raises(Exception, match=rf"(?s){field}.*at least 1 character"):
        _recipe({**op, field: ""})


def test_recipe_prism_op_alone_auto_draws_and_labels_once():
    res = _run(lower_to_ir(_recipe({**PRISM_OP, **TEXTS})))
    for f in PRISM_FIELDS:
        assert _count(res.svg, TEXTS[f]) == 1, f
    assert res.warnings == []


def test_recipe_stack_op_alone_auto_draws_and_labels_once():
    res = _run(lower_to_ir(_recipe({**STACK_OP, "count_label": "6 cubes"})))
    assert _count(res.svg, "6 cubes") == 1


# --- pydsl -------------------------------------------------------------------------

def _script(body: str):
    res = run_script(body, timeout_seconds=90, features=SOLIDS)
    assert res.error is None, res.error
    return res


def test_python_prism_fields_label_once_through_the_sandbox():
    res = _script(
        'o = point(0, 0)\n'
        'box = prism(o, 4, 3, 2, length_label="4 ft", width_label="3 ft", '
        'height_label="2 ft", base_area_label="12 sq ft")\n'
        'draw(box)\n')
    out = _run(res.diagram_ir)
    for f in PRISM_FIELDS:
        assert _count(out.svg, TEXTS[f]) == 1, f


def test_python_prism_without_a_draw_has_no_labels():
    res = _script('o = point(0, 0)\nbox = prism(o, 4, 3, 2, length_label="4 ft")\n'
                  'draw_points(point(1, 1))\n')
    assert _count(_run(res.diagram_ir).svg, "4 ft") == 0


def test_python_stack_count_label_labels_once_through_the_sandbox():
    res = _script('o = point(0, 0)\ns = stack(o, heights=[[1, 2], [3, 0]], count_label="6 cubes")\n'
                  'draw(s)\n')
    assert _count(_run(res.diagram_ir).svg, "6 cubes") == 1


@pytest.mark.parametrize("call,field", [
    ("prism(o, 4, 3, 2, length_label=\"\")", "length_label"),
    ("prism(o, 4, 3, 2, width_label=\"\")", "width_label"),
    ("prism(o, 4, 3, 2, height_label=\"\")", "height_label"),
    ("prism(o, 4, 3, 2, base_area_label=\"\")", "base_area_label"),
    ("stack(o, heights=[[1]], count_label=\"\")", "count_label"),
])
def test_python_empty_label_is_a_script_error_naming_the_argument(call, field):
    res = run_script(f"o = point(0, 0)\nx = {call}\n", timeout_seconds=90, features=SOLIDS)
    assert res.error and field in res.error, res.error


def test_python_stub_lists_the_fields_only_with_solids_on():
    on = generate_stub(features=SOLIDS)
    for f in (*PRISM_FIELDS, "count_label"):
        assert f in on, f
    off = generate_stub()
    for f in (*PRISM_FIELDS, "count_label"):
        assert f not in off, f


# --- structured --------------------------------------------------------------------

def _structured_ir() -> ir.DiagramIR:
    return ir.DiagramIR.model_validate({
        "canvas": {"xmin": -1, "xmax": 12, "ymin": -1, "ymax": 8},
        "define": [
            {"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
            {"kind": "rectangular_prism", "id": "P", "origin": "O", "length": 4, "width": 3,
             "height": 2, **TEXTS},
            {"kind": "point_fixed", "id": "O2", "x": 7, "y": 0},
            {"kind": "block_stack", "id": "S", "origin": "O2", "heights": [[1, 2], [3, 0]],
             "count_label": "6 cubes"},
        ],
        "checks": [],
        "render": [{"kind": "draw", "obj": "P"}, {"kind": "draw", "obj": "S"}],
    })


def _raw(diagram) -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 1, "output_tokens": 1}}
    return {"raw": raw, "parsed": diagram, "parsing_error": None}


@pytest.mark.asyncio
async def test_structured_response_with_fields_renders_each_label_once():
    structured = MagicMock()
    structured.ainvoke = AsyncMock(side_effect=[_raw(_structured_ir())])
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        res = await StructureStrategy(features=SOLIDS).run("a box", renderer=SVGRenderer())
    assert res.retries == 0
    for text in (*TEXTS.values(), "6 cubes"):
        assert _count(res.svg, text) == 1, text


# --- the label-dimension warning ----------------------------------------------------

def test_warning_fires_for_a_wrong_number_in_a_field_and_a_manual_label_on_the_wrong_edge():
    field = lower_to_ir(_recipe({**PRISM_OP, "length_label": "9 ft"}))
    assert any("does not match its true length" in w for w in _run(field).warnings)
    manual = RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]}, PRISM_OP],
        "annotations": {"labels": [{"kind": "label_segment", "endpoints": ["P_v000", "P_v100"], "text": "3"}]},
        "checks": []})
    d = lower_to_ir(manual)
    assert any("does not match its true length" in w for w in _run(d).warnings)


# --- gating: solids off ---------------------------------------------------------------

def test_stored_ir_with_fields_compiles_and_renders_with_solids_off():
    res = _run(_structured_ir())
    assert _count(res.svg, "4 ft") == 1 and _count(res.svg, "6 cubes") == 1


def test_solids_off_texts_are_unchanged_and_mention_no_field():
    pre = {n: json.loads((TESTS / f"{n}_prompt_pre_solids.json").read_text())
           for n in ("structured", "recipe", "python_full")}
    assert ins.build_structured_instructions() == pre["structured"]["system"]
    assert dsl_docs_for() == DSL_DOCS
    for text in (DSL_DOCS, ins.build_structured_instructions(), ipf.build_python_full_instructions()):
        for f in (*PRISM_FIELDS, "count_label"):
            assert f not in text, f


# --- guidance ---------------------------------------------------------------------------

def _gated():
    return {
        "recipe": dsl_docs_for(SOLIDS),
        "structured": ins.build_structured_instructions(SOLIDS),
        "python_full": ipf.build_python_full_instructions(features=SOLIDS),
    }


@pytest.mark.parametrize("surface", ["recipe", "structured", "python_full"])
def test_guidance_names_the_fields_and_the_rules(surface):
    text = " ".join(_gated()[surface].split())
    text = text.replace("One label per dimension", "one label per dimension")
    for needle in (*PRISM_FIELDS, "count_label", "one label per dimension",
                   ("label_segment" if surface != "python_full" else ".label(text)"),
                   "label_free_text" if surface != "python_full" else "label_text",
                   "verbatim", "6 ft", "silhouette", "draw the solid once", "hidden"):
        assert needle in text, (surface, needle)
    assert "wireframe" in text and "base_area_label" in text


def test_python_guidance_says_scripts_must_draw_and_prefers_count_label():
    text = " ".join(_gated()["python_full"].split())
    assert "does not draw by itself" in text
    assert "count_label=" in text and "preferred" in text


def test_executable_examples_use_the_fields():
    assert "length_label" in json.dumps(PRISM_EXAMPLES)
    assert "count_label" in json.dumps(STACK_EXAMPLES)
    assert "length_label" in json.dumps(ins.PRISM_EXAMPLE_IR)
    assert "count_label" in json.dumps(ins.STACK_EXAMPLE_IR)
    assert "length_label=" in ipf.PRISM_EXAMPLE_SCRIPT
    assert "count_label=" in ipf.STACK_EXAMPLE_SCRIPT


def test_prism_examples_render_each_label_once():
    ex = PRISM_EXAMPLES["labels_op"]
    d = lower_to_ir(_recipe(ex))
    res = _run(d)
    for f in PRISM_FIELDS:
        if ex.get(f):
            assert _count(res.svg, ex[f]) == 1, f
    s = lower_to_ir(_recipe(STACK_EXAMPLES["count_label_op"]))
    assert _count(_run(s).svg, STACK_EXAMPLES["count_label_op"]["count_label"]) == 1


# --- review fixes: the trigger claim and the fragment-level pin ----------------------------

import re  # noqa: E402


@pytest.mark.parametrize("surface", ["recipe", "structured", "python_full"])
def test_guidance_never_says_a_fill_of_the_solid_id_triggers_labels(surface):
    text = " ".join(_gated()[surface].split())
    assert not re.search(r"(any|or) [`]?(draw|fill)[`]?(\(\.\.\.\)[`]?)?( or [`]?fill[`]?(\(\.\.\.\)[`]?)?)? of (the )?(prism id|[`]box[`])", text)
    assert "draw or fill of the prism id" not in text and "`fill` of the prism id" not in text
    assert "fill(...)` of `box`" not in text
    # the accurate claim is present
    assert "faces" in text and "triggers all of them" in text


def test_fill_of_a_face_id_does_trigger_the_labels_and_the_docstrings_agree():
    d = lower_to_ir(RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]},
                         {**PRISM_OP, "length_label": "4 ft", "visible": False}],
        "annotations": {"auto_draw_all": False, "draws": []}, "checks": []}))
    d.render.append(ir.Fill(obj="P_front"))
    assert _count(_run(d).svg, "4 ft") == 1
    from geometry_diagrams.pydsl import api
    assert "fill the prism" not in api.prism.__doc__ and "draw/fill of one of its faces" in api.prism.__doc__
    assert "draw/fill of one of its column top faces" in api.stack.__doc__


def test_structured_example_description_matches_the_example():
    text = ins.build_structured_instructions(SOLIDS)
    assert "with dimension label fields, a face label and checks" in text
    assert "with an edge label" not in text


def test_python_full_fragment_itself_carries_the_one_label_rule():
    frag = " ".join(ipf._SOLIDS_FRAGMENT.split())
    assert "One label per dimension" in frag
    assert "`length_label=`" in frag and "draw the solid once" in frag
    assert "does not draw by itself" in frag

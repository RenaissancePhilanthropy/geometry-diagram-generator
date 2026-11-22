"""query_geometry_diagram and verify_geometry_diagram work from DiagramResult.diagram_ir,
so a python_full (or structured) result can be queried and verified with no model call and
no sandbox rerun."""
from __future__ import annotations

import asyncio
import copy
import json

import pytest

from geometry_diagrams import query_geometry_diagram, verify_geometry_diagram
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

# Right angle at B, legs 6 and 8, so the hypotenuse is 10 and the angle at C is 36.87 degrees.
SCRIPT = """
canvas((-2, 12), (-2, 10))
a = point(0, 6); b = point(0, 0); c = point(8, 0)
t = triangle(a, b, c); draw(t)
a.label("A"); b.label("B"); c.label("C")
assert_distance(t.side(a, b), 6)
assert_distance(t.side(b, c), 8)
mark_right_angle(t.angle_at(b))
"""


def _ir_dict(script: str = SCRIPT) -> dict:
    """What DiagramResult.diagram_ir holds: the pipeline's serialized DiagramIR."""
    built = run_script(script, timeout_seconds=60)
    assert built.error is None, built.error
    return asyncio.run(run_ir_pipeline(built.diagram_ir, SVGRenderer())).diagram_ir.model_dump()


@pytest.fixture(scope="module")
def ir_dict() -> dict:
    return _ir_dict()


def _point_id(ir_dict: dict, label: str) -> str:
    return next(op["p"] for op in ir_dict["render"] if op["kind"] == "label_point" and op["text"] == label)


# --- query ---------------------------------------------------------------------------

def test_list_objects_includes_the_opaque_pydsl_ids(ir_dict):
    objects = json.loads(query_geometry_diagram(None, "list_objects", diagram_ir=ir_dict))
    assert {_point_id(ir_dict, n) for n in "ABC"} <= set(objects)
    assert objects[_point_id(ir_dict, "A")] == "Point"


def test_points_can_be_named_by_their_label(ir_dict):
    ac = json.loads(query_geometry_diagram(None, "distance", {"a": "A", "b": "C"}, diagram_ir=ir_dict))
    assert ac["distance"] == pytest.approx(10.0, abs=1e-6)
    angle = json.loads(query_geometry_diagram(None, "angle", {"a": "A", "vertex": "C", "b": "B"}, diagram_ir=ir_dict))
    assert angle["angle_degrees"] == pytest.approx(36.87, abs=0.01)
    coord = json.loads(query_geometry_diagram(None, "coordinate", {"point": "C"}, diagram_ir=ir_dict))
    assert (coord["x"], coord["y"]) == pytest.approx((8.0, 0.0))


def test_raw_ids_still_work_and_an_unknown_name_is_an_error(ir_dict):
    a, c = _point_id(ir_dict, "A"), _point_id(ir_dict, "C")
    assert json.loads(query_geometry_diagram(None, "distance", {"a": a, "b": c}, diagram_ir=ir_dict))["distance"] \
        == pytest.approx(10.0, abs=1e-6)
    assert "error" in json.loads(query_geometry_diagram(None, "coordinate", {"point": "Z"}, diagram_ir=ir_dict))


def test_a_label_on_several_points_is_ambiguous():
    twice = _ir_dict(SCRIPT + 'd = point(3, 3); d.label("A")')
    result = json.loads(query_geometry_diagram(None, "coordinate", {"point": "A"}, diagram_ir=twice))
    assert "several points" in result["error"]


def test_query_needs_exactly_one_source(ir_dict):
    with pytest.raises(ValueError, match="exactly one"):
        query_geometry_diagram(None, "list_objects")
    with pytest.raises(ValueError, match="exactly one"):
        query_geometry_diagram({"construction": []}, "list_objects", diagram_ir=ir_dict)


def test_query_reports_a_bad_ir_as_error_json():
    assert "error" in json.loads(query_geometry_diagram(None, "list_objects", diagram_ir={"nonsense": 1}))


def test_query_still_works_from_a_recipe_dsl():
    from geometry_diagrams.recipe.catalog import load_recipe

    result = json.loads(query_geometry_diagram(load_recipe("altitude").example, "list_objects"))
    assert "error" not in result and result


# --- verify -----------------------------------------------------------------------------

def test_verify_a_clean_figure_reports_the_scripts_own_asserts(ir_dict):
    report = verify_geometry_diagram(ir_dict)
    assert report["ok"] is True and report["angle_findings"] == [] and report["invalid_angle_triples"] == []
    assert [(c["kind"], c["passed"], c["level"]) for c in report["checks"]] == [("distance_equals", True, "must")] * 2


def test_verify_reports_a_failing_check(ir_dict):
    broken = copy.deepcopy(ir_dict)
    broken["checks"][0]["expected"] = 7  # no longer holds
    report = verify_geometry_diagram(broken)
    assert report["ok"] is False
    (failed,) = [c for c in report["checks"] if not c["passed"]]
    assert failed["message"] and failed["level"] == "must"


def test_verify_reports_an_angle_mark_that_contradicts_the_drawing():
    labeled = _ir_dict(SCRIPT + 't.angle_at(c).label("50°")')
    report = verify_geometry_diagram(labeled)
    assert report["ok"] is False
    (finding,) = report["angle_findings"]
    assert finding["kind"] == "angle_label" and finding["stated_deg"] == 50
    assert finding["drawn_deg"] == pytest.approx(36.87, abs=0.01)
    assert finding["angle"][1] == _point_id(labeled, "C")  # the vertex
    assert any("50°" in w for w in report["warnings"])


def test_verify_reports_an_uncompilable_ir_as_error():
    report = verify_geometry_diagram({"nonsense": 1})
    assert report["ok"] is False and report["error"]


def test_the_report_is_json_serializable(ir_dict):
    json.dumps(verify_geometry_diagram(ir_dict))

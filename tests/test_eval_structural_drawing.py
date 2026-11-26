"""The drawing-reading structural eval checks (evals/structural_drawing.py) and grid_point_at,
on small synthetic figures: pass on a correct one, fail on a wrong one, skip where specified,
resolve names through labels when the ids are opaque, and reject malformed args at load."""
from __future__ import annotations

import pytest

from evals import check_types as ct
from evals import scenarios as sc
from evals.gate import collect_check_outcomes
from evals.run import _run_structural_checks
from evals.sympy_checks import _validate_properties_sympy

NEW_TYPES = {
    "dashed", "shaded", "concentric_circles", "line_name", "mark_group", "polygon_drawn",
    "object_exists", "length_ratios", "object_count",
}


def pt(i, x, y):
    return {"id": i, "kind": "point_fixed", "x": x, "y": y}


def draw(obj, style=None):
    return {"kind": "draw", "obj": obj, **({"style": style} if style else {})}


def label(p, text=None):
    return {"kind": "label_point", "p": p, "text": text or p}


def triangle_figure(**extra):
    """Right triangle A(0,0) B(4,0) C(0,3), drawn as a triangle def, with labels."""
    d = {
        "define": [pt("A", 0, 0), pt("B", 4, 0), pt("C", 0, 3),
                   {"id": "t", "kind": "triangle", "a": "A", "b": "B", "c": "C"}],
        "render": [draw("t"), label("A"), label("B"), label("C")],
        "checks": [],
    }
    d["define"] += extra.pop("define", [])
    d["render"] += extra.pop("render", [])
    d.update(extra)
    return d


def run(ctype, args, diagram, variable_ids=None):
    (result,) = _run_structural_checks(
        [{"name": "c", "type": ctype, "args": args}], diagram, None, variable_ids=variable_ids
    ).values()
    return result


def opaque(diagram):
    """The same figure with every def id replaced by ``__pydsl_pt_N`` (the name stays only as
    its point label), the way python_full authors it."""
    ids = {d["id"]: f"__pydsl_pt_{n}" for n, d in enumerate(diagram["define"])}

    def walk(o):
        if isinstance(o, dict):
            return {k: (v if k in ("text", "kind") else walk(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(x) for x in o]
        return ids.get(o, o) if isinstance(o, str) else o

    return walk(diagram)


def test_registry_has_the_ten_types():
    assert NEW_TYPES <= ct.structural_type_names()
    assert ct.property_type("grid_point_at").dimension == 0
    for name in NEW_TYPES:
        assert ct.structural_type(name).validate_args is not None


# --- dashed -------------------------------------------------------------------------------

def test_dashed_passes_on_dashed_segment_and_fails_on_solid():
    d = triangle_figure(
        define=[{"id": "s", "kind": "segment", "a": "A", "b": "C"}], render=[draw("s", "dashed_segment")]
    )
    assert run("dashed", {"points": ["A", "C"]}, d)["passed"] is True
    assert run("dashed", {"points": ["A", "B"]}, d)["passed"] is False  # drawn solid


def test_dashed_by_style_property_and_piecewise():
    d = triangle_figure(
        define=[{"id": "m", "kind": "point_fixed", "x": 2, "y": 0},
                {"id": "s1", "kind": "segment", "a": "A", "b": "m"},
                {"id": "s2", "kind": "segment", "a": "m", "b": "B"}],
        render=[draw("s1", "s_a"), draw("s2", "s_a")],
        styles={"s_a": {"dashed": True}},
    )
    assert run("dashed", {"points": ["A", "B"]}, d)["passed"] is True


def test_dashed_fails_on_unknown_point_and_skips_without_ir():
    assert "'Q'" in run("dashed", {"points": ["A", "Q"]}, triangle_figure())["message"]
    assert run("dashed", {"points": ["A", "Q"]}, triangle_figure())["resolution"] == "unresolved"
    assert run("dashed", {"points": ["A", "B"]}, None)["passed"] is None


# --- shaded -------------------------------------------------------------------------------

def test_shaded_any_order_and_exact_corners():
    d = triangle_figure(render=[{"kind": "fill", "obj": "t", "opacity": 0.3}])
    assert run("shaded", {"points": ["C", "A", "B"]}, d)["passed"] is True
    quad = triangle_figure(define=[pt("D", 4, 3)])
    assert run("shaded", {"points": ["A", "B", "C"]}, quad)["passed"] is False  # no fill at all
    d2 = triangle_figure(render=[{"kind": "fill", "obj": "t"}], define=[pt("D", 4, 3)])
    assert run("shaded", {"points": ["A", "B", "D"]}, d2)["passed"] is False  # another polygon


# --- concentric circles -------------------------------------------------------------------

def circles(*radii, center="A"):
    return triangle_figure(
        define=[{"id": f"k{n}", "kind": "circle_center_radius", "center": center, "radius": r}
                for n, r in enumerate(radii)],
        render=[draw(f"k{n}") for n in range(len(radii))],
    )


def test_concentric_circles():
    assert run("concentric_circles", {"center": "A", "count": 2}, circles(1, 2))["passed"] is True
    assert run("concentric_circles", {"center": "A", "count": 2}, circles(1, 1))["passed"] is False
    assert run("concentric_circles", {"center": "B", "count": 2}, circles(1, 2))["passed"] is False
    assert run("concentric_circles", {"center": "A", "count": 2}, None)["passed"] is None


# --- line_name ----------------------------------------------------------------------------

def test_line_name_near_and_far():
    near = triangle_figure(render=[{"kind": "label_free_text", "text": "$m$", "at": [2, -0.3]}])
    far = triangle_figure(render=[{"kind": "label_free_text", "text": "m", "at": [30, 30]}])
    assert run("line_name", {"points": ["A", "B"], "name": "m"}, near)["passed"] is True
    assert run("line_name", {"points": ["A", "B"], "name": "m"}, far)["passed"] is False
    assert run("line_name", {"points": ["A", "B"], "name": "q"}, near)["passed"] is False  # other text


# --- mark_group ---------------------------------------------------------------------------

def marked():
    return triangle_figure(
        define=[{"id": "ab", "kind": "segment", "a": "A", "b": "B"},
                {"id": "ac", "kind": "segment", "a": "A", "b": "C"},
                {"id": "bc", "kind": "segment", "a": "B", "b": "C"}],
        render=[{"kind": "mark_segments", "segs": ["ab", "ac"], "group": "tick1"},
                {"kind": "mark_segments", "segs": ["bc"], "group": "tick2"},
                {"kind": "mark_segments", "segs": ["ab", "bc"], "group": "parallel1"},
                {"kind": "mark_angles", "group": "arc2",
                 "angles": [{"a": "B", "o": "A", "b": "C"}, {"a": "A", "o": "B", "b": "C"}]}],
    )


def test_mark_group_tick_parallel_angle():
    d = marked()
    assert run("mark_group", {"mark": "tick", "members": [["A", "B"], ["C", "A"]]}, d)["passed"] is True
    assert run("mark_group", {"mark": "tick", "members": [["A", "B"], ["B", "C"]]}, d)["passed"] is False
    assert run("mark_group", {"mark": "tick", "members": [["A", "C"], ["B", "C"]]}, d)["passed"] is False
    assert run("mark_group", {"mark": "parallel", "members": [["A", "B"], ["B", "C"]]}, d)["passed"] is True
    assert run("mark_group", {"mark": "parallel", "members": [["A", "C"], ["B", "C"]]}, d)["passed"] is False
    assert run("mark_group", {"mark": "angle", "members": [["B", "A", "C"], ["A", "B", "C"]]}, d)["passed"] is True
    assert run("mark_group", {"mark": "angle", "members": [["B", "A", "C"], ["A", "C", "B"]]}, d)["passed"] is False
    one = run("mark_group", {"mark": "tick", "members": [["B", "C"]]}, d)
    assert one["passed"] is True  # a single member passes with any mark


def test_mark_group_angle_sides_and_arm_points_along_a_ray():
    d = marked()
    ok = {"mark": "angle", "members": [["B", "A", "C"]], "sides": ["interior"]}
    assert run("mark_group", ok, d)["passed"] is True
    assert run("mark_group", {**ok, "sides": ["reflex"]}, d)["passed"] is False
    far = triangle_figure(define=[pt("E", 8, 0)])  # E lies along the ray A->B
    far["define"] += marked()["define"][4:]
    far["render"] += marked()["render"][4:]
    assert run("mark_group", {"mark": "angle", "members": [["E", "A", "C"]]}, far)["passed"] is True


# --- polygon_drawn ------------------------------------------------------------------------

def test_polygon_drawn_by_def_by_segments_and_missing_side():
    assert run("polygon_drawn", {"points": ["A", "B", "C"]}, triangle_figure())["passed"] is True
    segs = {
        "define": [pt("A", 0, 0), pt("B", 4, 0), pt("C", 0, 3)]
        + [{"id": f"s{n}", "kind": "segment", "a": a, "b": b} for n, (a, b) in enumerate([("A", "B"), ("B", "C")])],
        "render": [draw("s0"), draw("s1"), label("A"), label("B"), label("C")], "checks": [],
    }
    res = run("polygon_drawn", {"points": ["A", "B", "C"]}, segs)
    assert res["passed"] is False and "CA" in res["message"]


# --- object_exists ------------------------------------------------------------------------

def test_object_exists_segment_circle_and_kind_not_enforced():
    d = circles(5)  # circle about A radius 5 passes through B? |AB| = 4: no; through none
    assert run("object_exists", {"object": "segment", "points": ["A", "B"]}, d)["passed"] is True
    assert run("object_exists", {"object": "ray", "points": ["A", "B"]}, d)["passed"] is True
    assert run("object_exists", {"object": "circle", "points": ["A"]}, d)["passed"] is True
    assert run("object_exists", {"object": "circle", "points": ["A", "B"]}, d)["passed"] is False
    assert run("object_exists", {"object": "circle", "points": ["A", "B"]}, circles(4))["passed"] is True
    assert run("object_exists", {"object": "circle", "points": ["B"]}, circles(4))["passed"] is False
    gone = triangle_figure()
    gone["define"][3] = {"id": "t", "kind": "segment", "a": "A", "b": "B"}
    assert run("object_exists", {"object": "segment", "points": ["A", "C"]}, gone)["passed"] is False


# --- length_ratios ------------------------------------------------------------------------

def test_length_ratios_scale_free_and_names_the_stray():
    args = {"segments": [["A", "B"], ["A", "C"], ["B", "C"]], "values": [4, 3, 5]}
    assert run("length_ratios", args, triangle_figure())["passed"] is True
    args2 = {"segments": [["A", "B"], ["A", "C"], ["B", "C"]], "values": [8, 6, 10]}
    assert run("length_ratios", args2, triangle_figure())["passed"] is True  # any common scale
    bad = {"segments": [["A", "B"], ["A", "C"], ["B", "C"]], "values": [4, 3, 9]}
    res = run("length_ratios", bad, triangle_figure())
    assert res["passed"] is False and "BC" in res["message"]
    assert run("length_ratios", {"segments": [["A", "B"], ["A", "C"]], "values": [4, 3]}, None)["passed"] is None


# --- object_count -------------------------------------------------------------------------

def test_object_count_extras_omissions_and_runs_counted_once():
    assert run("object_count", {"circle": [0, 0], "straight": [3, 3]}, triangle_figure())["passed"] is True
    extra = run("object_count", {"circle": [0, 0], "straight": [3, 3]}, circles(1))
    assert extra["passed"] is False and "circle: 1 drawn, at most 0" in extra["message"]
    miss = run("object_count", {"circle": [1, 1], "straight": [3, 3]}, triangle_figure())
    assert miss["passed"] is False and "at least 1" in miss["message"]
    pieces = {
        "define": [pt("A", 0, 0), pt("M", 2, 0), pt("B", 4, 0),
                   {"id": "s1", "kind": "segment", "a": "A", "b": "M"},
                   {"id": "s2", "kind": "segment", "a": "M", "b": "B"}],
        "render": [draw("s1"), draw("s2")], "checks": [],
    }
    assert run("object_count", {"circle": [0, 0], "straight": [1, 2]}, pieces)["passed"] is True
    hidden = {**pieces, "render": [draw("s1")]}  # s2 defined, never drawn: not counted
    assert run("object_count", {"circle": [0, 0], "straight": [1, 1]}, hidden)["passed"] is True


# --- names ----------------------------------------------------------------------------------

@pytest.mark.parametrize("ctype,args", [
    ("polygon_drawn", {"points": ["A", "B", "C"]}),
    ("object_exists", {"object": "segment", "points": ["B", "C"]}),
    ("length_ratios", {"segments": [["A", "B"], ["A", "C"]], "values": [4, 3]}),
])
def test_names_resolve_through_labels_when_ids_are_opaque(ctype, args):
    d = opaque(triangle_figure())
    assert "A" not in {x["id"] for x in d["define"]}
    assert run(ctype, args, d)["passed"] is True


def test_names_resolve_through_variable_ids_and_report_the_resolution():
    d = opaque(triangle_figure())
    d["render"] = [op for op in d["render"] if op["kind"] != "label_point"]  # no labels at all
    args = {"points": ["A", "B", "C"]}
    res = run("polygon_drawn", args, d)
    assert res["passed"] is False and res["resolution"] == "unresolved"
    ids = {"A": "__pydsl_pt_0", "B": "__pydsl_pt_1", "C": "__pydsl_pt_2"}
    res = run("polygon_drawn", args, d, variable_ids=ids)
    assert res["passed"] is True and res["resolved_names"] == ids


def test_ambiguous_name_is_reported_and_gates_apart_from_a_geometry_failure():
    d = triangle_figure()
    d["render"].append(label("C", "A"))  # a second point labelled A, and A's own id is also "A"
    res = run("polygon_drawn", {"points": ["A", "B", "C"]}, d)
    assert res["passed"] is False and res["resolution"] == "ambiguous"
    failures, _, _ = collect_check_outcomes({"structural_checks": {"x": res}})
    assert failures == ["structural:x:ambiguous"]
    geometry = run("dashed", {"points": ["A", "B"]}, triangle_figure())
    failures, _, _ = collect_check_outcomes({"structural_checks": {"x": geometry}})
    assert failures == ["structural:x"]


def test_skip_is_a_soft_pass_not_a_failure():
    res = run("dashed", {"points": ["A", "B"]}, None)
    failures, skipped, _ = collect_check_outcomes({"structural_checks": {"x": res}})
    assert failures == [] and skipped == ["structural:x"]


# --- load-time validation -------------------------------------------------------------------

@pytest.mark.parametrize("ctype,args", [
    ("dashed", {"points": ["A"]}),
    ("dashed", {"points": ["A", "B"], "object": "arc"}),
    ("dashed", {"points": ["A", "B"], "bogus": 1}),
    ("shaded", {"points": ["A", "B"]}),
    ("concentric_circles", {"center": "O", "count": 1}),
    ("concentric_circles", {"center": "", "count": 2}),
    ("line_name", {"points": ["A", "B"], "name": " "}),
    ("mark_group", {"mark": "dot", "members": [["A", "B"]]}),
    ("mark_group", {"mark": "angle", "members": [["A", "B"]]}),
    ("mark_group", {"mark": "tick", "members": [["A", "B"]], "sides": ["interior"]}),
    ("mark_group", {"mark": "angle", "members": [["A", "B", "C"]], "sides": ["exterior"]}),
    ("polygon_drawn", {"points": ["A", "B"]}),
    ("object_exists", {"object": "arc", "points": ["A", "B"]}),
    ("object_exists", {"object": "segment", "points": ["A"]}),
    ("length_ratios", {"segments": [["A", "B"]], "values": [1]}),
    ("length_ratios", {"segments": [["A", "B"], ["B", "C"]], "values": [1, 0]}),
    ("length_ratios", {"segments": [["A", "B"], ["B", "C"]], "values": [1]}),
    ("object_count", {"circle": [0, 0]}),
    ("object_count", {"circle": [2, 1], "straight": [1, 1]}),
    ("object_count", {"circle": [0, 0], "straight": [1.5, 2]}),
])
def test_loader_rejects_malformed_args(ctype, args):
    with pytest.raises(ValueError, match=ctype):
        sc._validate_scenarios([{
            "id": "s", "prompt": "p", "structural_checks": [{"name": "c", "type": ctype, "args": args}],
        }], strict=True)


def test_loader_accepts_well_formed_args():
    checks = [
        ("dashed", {"points": ["A", "B"], "object": "ray"}),
        ("shaded", {"points": ["A", "B", "C"]}),
        ("concentric_circles", {"center": "O", "count": 2}),
        ("line_name", {"points": ["A", "D"], "name": "m"}),
        ("mark_group", {"mark": "angle", "members": [["A", "B", "C"]], "sides": ["reflex"]}),
        ("polygon_drawn", {"points": ["A", "B", "C"]}),
        ("object_exists", {"object": "circle", "points": ["O"]}),
        ("length_ratios", {"segments": [["A", "B"], ["B", "C"]], "values": [3.0, 4]}),
        ("object_count", {"circle": [1, 1], "straight": [3, 5]}),
    ]
    (s,) = sc._validate_scenarios([{
        "id": "s", "prompt": "p",
        "structural_checks": [{"name": f"c{n}", "type": t, "args": a} for n, (t, a) in enumerate(checks)],
    }], strict=True)
    assert not any(c.get("unsupported") for c in s["structural_checks"])


# --- grid_point_at ----------------------------------------------------------------------------

def grid(args, points=None, **extra):
    points = {"T": (3.05, 2.0), "U": (1.0, 1.0)} if points is None else points
    prop = {"name": "g", "type": "grid_point_at", "args": args, **extra}
    (r,) = _validate_properties_sympy([prop], points)
    return r


def test_grid_point_at_pass_fail_and_per_axis_tolerance():
    assert grid(["T", 3.0, 2.0, 0.12, 0.12])["passed"] is True
    assert grid(["T", 3.0, 2.0, 0.01, 0.12])["passed"] is False  # x off by 0.05 > 0.01
    assert grid(["T", 3.0, 2.5, 0.12, 0.6])["passed"] is True  # each axis has its own tolerance
    assert grid(["T", 3.0, 2.5, 0.12, 0.12])["passed"] is False


def test_grid_point_at_unknown_point_fails_and_empty_table_skips():
    missing = grid(["Q", 3, 2, 0.1, 0.1])
    assert missing["passed"] is False and "Q" in missing["message"]
    evaluate = ct.property_type("grid_point_at").evaluate
    assert evaluate(["T", 3, 2, 0.1, 0.1], ct.GeometryContext({}, 0.0))[0] is None
    with pytest.raises(KeyError):  # called without the resolver, an unknown id is an error
        evaluate(["Q", 3, 2, 0.1, 0.1], ct.GeometryContext({"T": (3, 2)}, 0.0))


def test_grid_point_at_tol_is_ignored_and_rel_tol_refused():
    assert grid(["T", 3.0, 2.0, 0.01, 0.12], tol=5)["passed"] is False  # tol does not widen it
    base = {"id": "s", "prompt": "p"}
    props = [{"name": "g", "type": "grid_point_at", "args": ["T", 3, 2, 0.1, 0.1], "rel_tol": 0.1}]
    with pytest.raises(ValueError, match="rel_tol"):
        sc._validate_scenarios([{**base, "expected_properties": props}])


@pytest.mark.parametrize("args", [
    ["T", 3, 2, 0.1], ["T", 3, 2, 0.1, 0], ["T", "3", 2, 0.1, 0.1], [" ", 3, 2, 0.1, 0.1],
    ["T", 3, 2, 0.1, True], ["T", float("nan"), 2, 0.1, 0.1],
])
def test_grid_point_at_loader_rejects_malformed_args(args):
    with pytest.raises(ValueError, match="grid_point_at"):
        sc._validate_scenarios([{
            "id": "s", "prompt": "p",
            "expected_properties": [{"name": "g", "type": "grid_point_at", "args": args}],
        }])

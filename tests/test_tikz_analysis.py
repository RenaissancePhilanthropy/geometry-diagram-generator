"""
Unit tests for util/tikz_analysis.py.
No Docker or renderer required — pure Python logic.
"""

import pytest

from geometry_diagrams.util.tikz_analysis import (
    extract_canvas_features,
    extract_defined_points,
    extract_computed_points,
    extract_draw_commands,
    extract_labels,
    extract_marks,
    resolve_all_coordinates,
    validate_geometric_property,
    validate_expected_points,
    validate_required_canvas,
    validate_required_labels,
    validate_required_entities,
)


# ---------------------------------------------------------------------------
# extract_defined_points
# ---------------------------------------------------------------------------

def test_extract_single_point():
    tikz = r"\tkzDefPoint(0,0){A}"
    pts = extract_defined_points(tikz)
    assert pts == {"A": (0.0, 0.0)}


def test_extract_multiple_points():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(1.5,2.6){C}
"""
    pts = extract_defined_points(tikz)
    assert pts["A"] == (0.0, 0.0)
    assert pts["B"] == (3.0, 0.0)
    assert pts["C"] == (1.5, 2.6)


def test_extract_point_with_spaces():
    tikz = r"\tkzDefPoint( 0 , 0 ){A}"
    pts = extract_defined_points(tikz)
    assert "A" in pts
    assert pts["A"] == (0.0, 0.0)


def test_extract_point_negative_coords():
    tikz = r"\tkzDefPoint(-1.5, -2.0){P}"
    pts = extract_defined_points(tikz)
    assert pts["P"] == (-1.5, -2.0)


def test_extract_empty_tikz_returns_empty():
    assert extract_defined_points("") == {}


# ---------------------------------------------------------------------------
# extract_computed_points
# ---------------------------------------------------------------------------

def test_extract_midpoint_command():
    tikz = r"\tkzDefMidPoint(A,B) \tkzGetPoint{M}"
    computed = extract_computed_points(tikz)
    assert "M" in computed
    assert computed["M"]["type"] == "midpoint"
    assert computed["M"]["args"] == ["A", "B"]


def test_extract_circumcenter_command():
    tikz = r"\tkzCircumCenter(A,B,C) \tkzGetPoint{O}"
    computed = extract_computed_points(tikz)
    assert "O" in computed
    assert computed["O"]["type"] == "circumcenter"
    assert computed["O"]["args"] == ["A", "B", "C"]


def test_extract_inter_ll_command():
    tikz = r"\tkzInterLL(A,B)(C,D) \tkzGetPoint{P}"
    computed = extract_computed_points(tikz)
    assert "P" in computed
    assert computed["P"]["type"] == "inter_ll"
    assert computed["P"]["args"] == ["A", "B", "C", "D"]


# ---------------------------------------------------------------------------
# extract_draw_commands
# ---------------------------------------------------------------------------

def test_extract_polygon():
    tikz = r"\tkzDrawPolygon(A,B,C)"
    cmds = extract_draw_commands(tikz)
    assert len(cmds) == 1
    c = cmds[0]
    assert c["type"] == "polygon"
    assert c["points"] == ["A", "B", "C"]
    assert ("A", "B") in c["edges"]
    assert ("B", "C") in c["edges"]
    assert ("C", "A") in c["edges"]


def test_extract_segment():
    tikz = r"\tkzDrawSegment(A,B)"
    cmds = extract_draw_commands(tikz)
    assert any(c["type"] == "segment" and c["from"] == "A" and c["to"] == "B" for c in cmds)


def test_extract_circle():
    tikz = r"\tkzDrawCircle(O,A)"
    cmds = extract_draw_commands(tikz)
    assert any(c["type"] == "circle" and c["center"] == "O" and c["through"] == "A" for c in cmds)


def test_extract_segment_with_options():
    tikz = r"\tkzDrawSegment[dashed](A,B)"
    cmds = extract_draw_commands(tikz)
    assert any(c["type"] == "segment" and c["from"] == "A" for c in cmds)


# ---------------------------------------------------------------------------
# extract_marks
# ---------------------------------------------------------------------------

def test_extract_right_angle_mark():
    tikz = r"\tkzMarkRightAngle(A,B,C)"
    marks = extract_marks(tikz)
    ra = [m for m in marks if m["type"] == "right_angle"]
    assert len(ra) == 1
    assert ra[0]["from"] == "A"
    assert ra[0]["vertex"] == "B"
    assert ra[0]["to"] == "C"


def test_extract_angle_mark():
    tikz = r"\tkzMarkAngle[size=0.5](B,A,C)"
    marks = extract_marks(tikz)
    angles = [m for m in marks if m["type"] == "angle"]
    assert len(angles) == 1


def test_extract_segment_mark():
    tikz = r"\tkzMarkSegment[mark=|](A,B)"
    marks = extract_marks(tikz)
    sm = [m for m in marks if m["type"] == "segment_mark"]
    assert len(sm) == 1
    assert sm[0]["from"] == "A"
    assert sm[0]["to"] == "B"


# ---------------------------------------------------------------------------
# extract_labels
# ---------------------------------------------------------------------------

def test_extract_label_points():
    tikz = r"\tkzLabelPoints[below](A,B)"
    labels = extract_labels(tikz)
    lp = [l for l in labels if l["type"] == "label_points"]
    assert len(lp) == 1
    assert "A" in lp[0]["points"]
    assert "B" in lp[0]["points"]


def test_extract_label_point_with_text():
    tikz = r"\tkzLabelPoint[right](A){$A$}"
    labels = extract_labels(tikz)
    lp = [l for l in labels if l["type"] == "label_point"]
    assert len(lp) == 1
    assert lp[0]["point"] == "A"
    assert lp[0]["text"] == "$A$"


# ---------------------------------------------------------------------------
# resolve_all_coordinates
# ---------------------------------------------------------------------------

def test_resolve_explicit_points_only():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
"""
    coords = resolve_all_coordinates(tikz)
    assert coords["A"] == (0.0, 0.0)
    assert coords["B"] == (4.0, 0.0)


def test_resolve_midpoint():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefMidPoint(A,B) \tkzGetPoint{M}
"""
    coords = resolve_all_coordinates(tikz)
    assert "M" in coords
    assert coords["M"] == pytest.approx((2.0, 0.0))


def test_resolve_circumcenter():
    # Right triangle with vertices at (0,0), (4,0), (0,3)
    # Circumcenter of right triangle is midpoint of hypotenuse
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(0,3){C}
\tkzCircumCenter(A,B,C) \tkzGetPoint{O}
"""
    coords = resolve_all_coordinates(tikz)
    assert "O" in coords
    assert coords["O"] == pytest.approx((2.0, 1.5))


def test_resolve_line_intersection():
    # Lines: A(0,0)-B(2,2) and C(0,2)-D(2,0) intersect at (1,1)
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(2,2){B}
\tkzDefPoint(0,2){C}
\tkzDefPoint(2,0){D}
\tkzInterLL(A,B)(C,D) \tkzGetPoint{P}
"""
    coords = resolve_all_coordinates(tikz)
    assert "P" in coords
    assert coords["P"] == pytest.approx((1.0, 1.0))


def test_resolve_chained_derived_points():
    """Derived point that depends on another derived point."""
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefMidPoint(A,B) \tkzGetPoint{M}
\tkzDefPoint(0,4){C}
\tkzDefMidPoint(M,C) \tkzGetPoint{N}
"""
    coords = resolve_all_coordinates(tikz)
    assert coords["M"] == pytest.approx((2.0, 0.0))
    assert coords["N"] == pytest.approx((1.0, 2.0))


# ---------------------------------------------------------------------------
# validate_geometric_property
# ---------------------------------------------------------------------------

def test_validate_right_angle_true():
    # B at corner — BA and BC are perpendicular
    coords = {"A": (0.0, 0.0), "B": (3.0, 0.0), "C": (3.0, 2.0)}
    result = validate_geometric_property(coords, "right_angle", ["A", "B", "C"])
    assert result is True


def test_validate_right_angle_false():
    # Acute triangle — no right angle at B
    coords = {"A": (0.0, 0.0), "B": (3.0, 0.0), "C": (1.5, 2.6)}
    result = validate_geometric_property(coords, "right_angle", ["A", "B", "C"])
    assert result is False


def test_validate_midpoint_true():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "M": (2.0, 0.0)}
    result = validate_geometric_property(coords, "midpoint", ["M", "A", "B"])
    assert result is True


def test_validate_midpoint_false():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "M": (1.0, 0.0)}
    result = validate_geometric_property(coords, "midpoint", ["M", "A", "B"])
    assert result is False


def test_validate_centroid_true():
    coords = {
        "A": (0.0, 0.0),
        "B": (6.0, 0.0),
        "C": (3.0, 6.0),
        "G": (3.0, 2.0),
    }
    result = validate_geometric_property(coords, "centroid", ["G", "A", "B", "C"])
    assert result is True


def test_validate_centroid_false():
    coords = {
        "A": (0.0, 0.0),
        "B": (6.0, 0.0),
        "C": (3.0, 6.0),
        "G": (3.0, 3.0),  # incenter-like, not the centroid
    }
    result = validate_geometric_property(coords, "centroid", ["G", "A", "B", "C"])
    assert result is False


def test_validate_centroid_irrational_triangle():
    # Equilateral with vertices at unit-scale irrational coordinates;
    # check that floating-point rounding stays within the default tolerance.
    import math
    coords = {
        "A": (1.0, 0.0),
        "B": (math.cos(2 * math.pi / 3), math.sin(2 * math.pi / 3)),
        "C": (math.cos(4 * math.pi / 3), math.sin(4 * math.pi / 3)),
        "G": (0.0, 0.0),
    }
    result = validate_geometric_property(coords, "centroid", ["G", "A", "B", "C"])
    assert result is True


def test_validate_collinear_true():
    coords = {"A": (0.0, 0.0), "B": (1.0, 1.0), "C": (2.0, 2.0)}
    result = validate_geometric_property(coords, "collinear", ["A", "B", "C"])
    assert result is True


def test_validate_collinear_false():
    coords = {"A": (0.0, 0.0), "B": (1.0, 0.0), "C": (0.0, 1.0)}
    result = validate_geometric_property(coords, "collinear", ["A", "B", "C"])
    assert result is False


def test_validate_equal_lengths_true():
    # Equilateral triangle
    import math
    h = math.sqrt(3) / 2 * 2
    coords = {"A": (0.0, 0.0), "B": (2.0, 0.0), "C": (1.0, h)}
    result = validate_geometric_property(
        coords, "equal_lengths", [["A", "B"], ["B", "C"], ["C", "A"]]
    )
    assert result is True


def test_validate_equal_lengths_false():
    coords = {"A": (0.0, 0.0), "B": (3.0, 0.0), "C": (3.0, 2.0)}
    result = validate_geometric_property(
        coords, "equal_lengths", [["A", "B"], ["B", "C"]]
    )
    assert result is False


def test_validate_parallel_true():
    # Horizontal lines: y=0 and y=2
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "C": (1.0, 2.0), "D": (5.0, 2.0)}
    result = validate_geometric_property(
        coords, "parallel", [["A", "B"], ["C", "D"]]
    )
    assert result is True


def test_validate_parallel_false():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "C": (0.0, 0.0), "D": (0.0, 4.0)}
    result = validate_geometric_property(
        coords, "parallel", [["A", "B"], ["C", "D"]]
    )
    assert result is False


def test_validate_perpendicular_true():
    # Horizontal and vertical lines
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "C": (2.0, 0.0), "D": (2.0, 4.0)}
    result = validate_geometric_property(
        coords, "perpendicular", [["A", "B"], ["C", "D"]]
    )
    assert result is True


def test_validate_missing_coordinate_returns_none():
    coords = {"A": (0.0, 0.0)}  # B is missing
    result = validate_geometric_property(coords, "right_angle", ["A", "B", "C"])
    assert result is None


def test_validate_unknown_property_returns_none():
    coords = {"A": (0.0, 0.0), "B": (1.0, 0.0)}
    result = validate_geometric_property(coords, "nonexistent_property", ["A", "B"])
    assert result is None


# ---------------------------------------------------------------------------
# point_on_line
# ---------------------------------------------------------------------------

def test_validate_point_on_line_true():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "P": (2.0, 0.0)}
    assert validate_geometric_property(coords, "point_on_line", ["P", "A", "B"]) is True


def test_validate_point_on_line_false():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "P": (2.0, 1.0)}
    assert validate_geometric_property(coords, "point_on_line", ["P", "A", "B"]) is False


def test_validate_point_on_line_outside_segment_still_true():
    # point_on_line does not require P to be between A and B
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "P": (10.0, 0.0)}
    assert validate_geometric_property(coords, "point_on_line", ["P", "A", "B"]) is True


# ---------------------------------------------------------------------------
# point_on_segment
# ---------------------------------------------------------------------------

def test_validate_point_on_segment_true():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "P": (2.0, 0.0)}
    assert validate_geometric_property(coords, "point_on_segment", ["P", "A", "B"]) is True


def test_validate_point_on_segment_false_outside():
    # Collinear but beyond B
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "P": (6.0, 0.0)}
    assert validate_geometric_property(coords, "point_on_segment", ["P", "A", "B"]) is False


def test_validate_point_on_segment_false_off_line():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0), "P": (2.0, 1.0)}
    assert validate_geometric_property(coords, "point_on_segment", ["P", "A", "B"]) is False


# ---------------------------------------------------------------------------
# point_on_circle
# ---------------------------------------------------------------------------

def test_validate_point_on_circle_true():
    # Circle centered at O(0,0), radius 5 (through R=(5,0)), P=(0,5) is on it
    coords = {"O": (0.0, 0.0), "R": (5.0, 0.0), "P": (0.0, 5.0)}
    assert validate_geometric_property(coords, "point_on_circle", ["P", "O", "R"]) is True


def test_validate_point_on_circle_false():
    coords = {"O": (0.0, 0.0), "R": (5.0, 0.0), "P": (3.0, 0.0)}
    assert validate_geometric_property(coords, "point_on_circle", ["P", "O", "R"]) is False


# ---------------------------------------------------------------------------
# tangent
# ---------------------------------------------------------------------------

def test_validate_tangent_true():
    # Circle center O(0,0), tangent point T(0,5), tangent line is horizontal through T
    # Line defined by L1=(-1, 5) and L2=(1, 5); OT is vertical, line is horizontal → perpendicular
    coords = {
        "O": (0.0, 0.0),
        "T": (0.0, 5.0),
        "L1": (-1.0, 5.0),
        "L2": (1.0, 5.0),
    }
    assert validate_geometric_property(coords, "tangent", [["L1", "L2"], "O", "T"]) is True


def test_validate_tangent_false_not_perpendicular():
    # Line L1L2 is not perpendicular to OT
    coords = {
        "O": (0.0, 0.0),
        "T": (0.0, 5.0),
        "L1": (0.0, 5.0),
        "L2": (1.0, 6.0),  # diagonal, not horizontal
    }
    assert validate_geometric_property(coords, "tangent", [["L1", "L2"], "O", "T"]) is False


def test_validate_tangent_false_t_not_on_line():
    # T is not on line L1L2
    coords = {
        "O": (0.0, 0.0),
        "T": (3.0, 5.0),   # off the horizontal line y=0
        "L1": (-1.0, 0.0),
        "L2": (1.0, 0.0),
    }
    assert validate_geometric_property(coords, "tangent", [["L1", "L2"], "O", "T"]) is False


# ---------------------------------------------------------------------------
# angle_equal
# ---------------------------------------------------------------------------

def test_validate_angle_equal_true():
    # Two right angles should be equal
    coords = {
        "A": (0.0, 1.0), "B": (0.0, 0.0), "C": (1.0, 0.0),  # ∠ABC = 90°
        "D": (0.0, 2.0), "E": (0.0, 0.0), "F": (2.0, 0.0),  # ∠DEF = 90°
    }
    assert validate_geometric_property(
        coords, "angle_equal", [["A", "B", "C"], ["D", "E", "F"]]
    ) is True


def test_validate_angle_equal_false():
    # 60° vs 90°
    import math
    coords = {
        "A": (1.0, 0.0), "B": (0.0, 0.0), "C": (0.5, math.sqrt(3) / 2),  # ≈ 60°
        "D": (0.0, 1.0), "E": (0.0, 0.0), "F": (1.0, 0.0),               # 90°
    }
    assert validate_geometric_property(
        coords, "angle_equal", [["A", "B", "C"], ["D", "E", "F"]]
    ) is False


# ---------------------------------------------------------------------------
# angle_bisector
# ---------------------------------------------------------------------------

def test_validate_angle_bisector_true():
    # ∠BAC where A=(0,0), B=(1,0), C=(0,1). Bisector direction is (1,1).
    # D = (1,1) lies on the bisector of ∠BAC
    coords = {
        "A": (0.0, 0.0),
        "B": (1.0, 0.0),
        "C": (0.0, 1.0),
        "D": (1.0, 1.0),
    }
    assert validate_geometric_property(coords, "angle_bisector", ["D", "A", "B", "C"]) is True


def test_validate_angle_bisector_false():
    # D = (2,1) does not bisect ∠BAC (not on bisector ray from A)
    coords = {
        "A": (0.0, 0.0),
        "B": (1.0, 0.0),
        "C": (0.0, 1.0),
        "D": (2.0, 1.0),
    }
    assert validate_geometric_property(coords, "angle_bisector", ["D", "A", "B", "C"]) is False


# ---------------------------------------------------------------------------
# intersects
# ---------------------------------------------------------------------------

def test_validate_intersects_true():
    # Lines A(0,0)-B(2,2) and C(0,2)-D(2,0) meet at P(1,1)
    coords = {
        "A": (0.0, 0.0), "B": (2.0, 2.0),
        "C": (0.0, 2.0), "D": (2.0, 0.0),
        "P": (1.0, 1.0),
    }
    assert validate_geometric_property(
        coords, "intersects", [["A", "B"], ["C", "D"], "P"]
    ) is True


def test_validate_intersects_false_wrong_point():
    coords = {
        "A": (0.0, 0.0), "B": (2.0, 2.0),
        "C": (0.0, 2.0), "D": (2.0, 0.0),
        "P": (0.0, 0.0),  # wrong point
    }
    assert validate_geometric_property(
        coords, "intersects", [["A", "B"], ["C", "D"], "P"]
    ) is False


def test_validate_intersects_parallel_lines():
    # Parallel lines never intersect
    coords = {
        "A": (0.0, 0.0), "B": (4.0, 0.0),
        "C": (0.0, 1.0), "D": (4.0, 1.0),
        "P": (2.0, 0.5),
    }
    assert validate_geometric_property(
        coords, "intersects", [["A", "B"], ["C", "D"], "P"]
    ) is False


# ---------------------------------------------------------------------------
# label_present
# ---------------------------------------------------------------------------

def test_validate_label_present_batch():
    tikz = r"\tkzLabelPoints[below](A,B,C)"
    coords: dict = {}
    assert validate_geometric_property(coords, "label_present", ["A"], tikz=tikz) is True
    assert validate_geometric_property(coords, "label_present", ["B"], tikz=tikz) is True
    assert validate_geometric_property(coords, "label_present", ["D"], tikz=tikz) is False


def test_validate_label_present_individual():
    tikz = r"\tkzLabelPoint[right](M){$M$}"
    coords: dict = {}
    assert validate_geometric_property(coords, "label_present", ["M"], tikz=tikz) is True
    assert validate_geometric_property(coords, "label_present", ["A"], tikz=tikz) is False


def test_validate_label_present_no_tikz_returns_none():
    coords: dict = {}
    assert validate_geometric_property(coords, "label_present", ["A"]) is None


# ---------------------------------------------------------------------------
# mark_present
# ---------------------------------------------------------------------------

def test_validate_mark_present_right_angle():
    tikz = r"\tkzMarkRightAngle(A,B,C)"
    coords: dict = {}
    assert validate_geometric_property(coords, "mark_present", ["right_angle", "B"], tikz=tikz) is True


def test_validate_mark_present_missing():
    tikz = r"\tkzMarkRightAngle(A,B,C)"
    coords: dict = {}
    assert validate_geometric_property(coords, "mark_present", ["right_angle", "X"], tikz=tikz) is False


def test_validate_mark_present_no_tikz_returns_none():
    coords: dict = {}
    assert validate_geometric_property(coords, "mark_present", ["right_angle", "B"]) is None


# ---------------------------------------------------------------------------
# validate_required_labels
# ---------------------------------------------------------------------------

def test_validate_required_labels_all_present():
    tikz = r"\tkzLabelPoints[below](A,B,C)"
    result = validate_required_labels(tikz, ["A", "B", "C"])
    assert result["passed"] is True
    assert result["missing"] == []


def test_validate_required_labels_some_missing():
    tikz = r"\tkzLabelPoints[below](A,B)"
    result = validate_required_labels(tikz, ["A", "B", "C"])
    assert result["passed"] is False
    assert "C" in result["missing"]


def test_validate_required_labels_empty_required():
    tikz = r""
    result = validate_required_labels(tikz, [])
    assert result["passed"] is True


def test_validate_required_labels_mixed_commands():
    tikz = r"""
\tkzLabelPoints[below](A,B)
\tkzLabelPoint[right](C){$C$}
"""
    result = validate_required_labels(tikz, ["A", "B", "C"])
    assert result["passed"] is True


def test_validate_required_labels_coordinate_style_label():
    tikz = r"\tkzLabelPoint[below](A){$A\,(0,0)$}"
    result = validate_required_labels(tikz, ["A"])
    assert result["passed"] is True


# ---------------------------------------------------------------------------
# validate_required_entities
# ---------------------------------------------------------------------------

def test_validate_required_entities_circle_found():
    tikz = r"\tkzDrawCircle(O,A)"
    result = validate_required_entities(tikz, [{"type": "circle"}])
    assert result["passed"] is True
    assert result["missing"] == []


def test_validate_required_entities_missing():
    tikz = r"\tkzDrawSegment(A,B)"
    result = validate_required_entities(tikz, [{"type": "circle"}])
    assert result["passed"] is False
    assert len(result["missing"]) == 1


def test_validate_required_entities_with_args_match():
    tikz = r"\tkzDrawCircle(O,A)"
    result = validate_required_entities(tikz, [{"type": "circle", "args": {"center": "O"}}])
    assert result["passed"] is True


def test_validate_required_entities_with_args_no_match():
    tikz = r"\tkzDrawCircle(O,A)"
    result = validate_required_entities(tikz, [{"type": "circle", "args": {"center": "X"}}])
    assert result["passed"] is False


def test_validate_required_entities_empty_required():
    tikz = r""
    result = validate_required_entities(tikz, [])
    assert result["passed"] is True


# ---------------------------------------------------------------------------
# New computed point extraction tests
# ---------------------------------------------------------------------------

def test_extract_coordinate_command():
    tikz = r"\coordinate (P) at (1.5, 2.5)"
    from geometry_diagrams.util.tikz_analysis import extract_defined_points
    pts = extract_defined_points(tikz)
    assert "P" in pts
    assert pts["P"] == pytest.approx((1.5, 2.5))


def test_extract_orthocenter_command():
    tikz = r"\tkzOrthoCenter(A,B,C) \tkzGetPoint{H}"
    computed = extract_computed_points(tikz)
    assert "H" in computed
    assert computed["H"]["type"] == "orthocenter"
    assert computed["H"]["args"] == ["A", "B", "C"]


def test_extract_centroid_command():
    tikz = r"\tkzCentroid(A,B,C) \tkzGetPoint{G}"
    computed = extract_computed_points(tikz)
    assert "G" in computed
    assert computed["G"]["type"] == "centroid"
    assert computed["G"]["args"] == ["A", "B", "C"]


def test_extract_triangle_center_in():
    tikz = r"\tkzDefTriangleCenter[in](A,B,C) \tkzGetPoint{I}"
    computed = extract_computed_points(tikz)
    assert "I" in computed
    assert computed["I"]["type"] == "incenter"
    assert computed["I"]["args"] == ["A", "B", "C"]


def test_extract_triangle_center_ortho():
    tikz = r"\tkzDefTriangleCenter[ortho](A,B,C) \tkzGetPoint{H}"
    computed = extract_computed_points(tikz)
    assert "H" in computed
    assert computed["H"]["type"] == "orthocenter"


def test_extract_projection_command():
    tikz = r"\tkzDefPointBy[projection=onto A--B](C) \tkzGetPoint{H}"
    computed = extract_computed_points(tikz)
    assert "H" in computed
    assert computed["H"]["type"] == "projection"
    assert computed["H"]["args"] == ["C", "A", "B"]


def test_extract_symmetry_command():
    tikz = r"\tkzDefPointBy[symmetry=center M](A) \tkzGetPoint{Ap}"
    computed = extract_computed_points(tikz)
    assert "Ap" in computed
    assert computed["Ap"]["type"] == "symmetry"
    assert computed["Ap"]["args"] == ["A", "M"]


# ---------------------------------------------------------------------------
# New coordinate resolution tests
# ---------------------------------------------------------------------------

def test_resolve_centroid():
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(6,0){B}
\tkzDefPoint(3,6){C}
\tkzCentroid(A,B,C) \tkzGetPoint{G}
"""
    coords = resolve_all_coordinates(tikz)
    assert "G" in coords
    assert coords["G"] == pytest.approx((3.0, 2.0))


def test_resolve_orthocenter():
    # Right triangle: A(0,0), B(4,0), C(0,3) → orthocenter at A(0,0)
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(0,3){C}
\tkzOrthoCenter(A,B,C) \tkzGetPoint{H}
"""
    coords = resolve_all_coordinates(tikz)
    assert "H" in coords
    assert coords["H"] == pytest.approx((0.0, 0.0), abs=1e-6)


def test_resolve_projection_foot_of_altitude():
    # C(0,3) projected onto AB where A(0,0), B(4,0) → foot at (0,0)
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(0,3){C}
\tkzDefPointBy[projection=onto A--B](C) \tkzGetPoint{H}
"""
    coords = resolve_all_coordinates(tikz)
    assert "H" in coords
    assert coords["H"] == pytest.approx((0.0, 0.0), abs=1e-6)


def test_resolve_projection_onto_diagonal():
    # Project P(0,1) onto line from A(0,0) to B(2,2)
    # Projection of (0,1) onto y=x: t = (0*2 + 1*2)/(4+4) = 2/8 = 0.25 → (0.5, 0.5)
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(2,2){B}
\tkzDefPoint(0,1){P}
\tkzDefPointBy[projection=onto A--B](P) \tkzGetPoint{F}
"""
    coords = resolve_all_coordinates(tikz)
    assert "F" in coords
    assert coords["F"] == pytest.approx((0.5, 0.5), abs=1e-6)


def test_resolve_incenter():
    # Equilateral triangle: incenter = centroid = (2, 2*sqrt(3)/3)
    # Using 3-4-5 right triangle A(0,0), B(4,0), C(0,3): incenter at (1,1)
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(0,3){C}
\tkzDefTriangleCenter[in](A,B,C) \tkzGetPoint{I}
"""
    coords = resolve_all_coordinates(tikz)
    assert "I" in coords
    # For 3-4-5 triangle: sides are 3, 4, 5. Inradius = (3+4-5)/2 = 1. Incenter at (1,1).
    assert coords["I"] == pytest.approx((1.0, 1.0), abs=1e-6)


def test_resolve_symmetry():
    # Reflection of A(1,0) across M(3,0) → (5,0)
    tikz = r"""
\tkzDefPoint(1,0){A}
\tkzDefPoint(3,0){M}
\tkzDefPointBy[symmetry=center M](A) \tkzGetPoint{Ap}
"""
    coords = resolve_all_coordinates(tikz)
    assert "Ap" in coords
    assert coords["Ap"] == pytest.approx((5.0, 0.0))


# ---------------------------------------------------------------------------
# equidistant_from_sides check
# ---------------------------------------------------------------------------

def test_equidistant_from_sides_incenter():
    # 3-4-5 right triangle, incenter at (1,1)
    coords = {
        "I": (1.0, 1.0),
        "A": (0.0, 0.0),
        "B": (4.0, 0.0),
        "C": (0.0, 3.0),
    }
    result = validate_geometric_property(coords, "equidistant_from_sides", ["I", "A", "B", "C"])
    assert result is True


def test_equidistant_from_sides_wrong_point():
    # Centroid is NOT equidistant from all sides in a non-equilateral triangle
    coords = {
        "G": (4/3, 1.0),  # centroid of 3-4-5 triangle
        "A": (0.0, 0.0),
        "B": (4.0, 0.0),
        "C": (0.0, 3.0),
    }
    result = validate_geometric_property(coords, "equidistant_from_sides", ["G", "A", "B", "C"])
    assert result is False


def test_equidistant_missing_coordinate_returns_none():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0)}
    result = validate_geometric_property(coords, "equidistant_from_sides", ["I", "A", "B", "C"])
    assert result is None


# ---------------------------------------------------------------------------
# Hardening pass §4.5 — pgfmath macro + trig coordinate evaluation
# ---------------------------------------------------------------------------
# Real LLM outputs frequently use \pgfmathsetmacro to define helpers like
# \side, then place points at \tkzDefPoint({\side*cos(-35)},{\side*sin(-35)}).
# The literal-only point extractor silently skips these, leading to
# soft_pass on every downstream check that references those points.

def test_extract_def_point_with_pgfmath_expression():
    tikz = r"""
\pgfmathsetmacro{\side}{6}
\tkzDefPoint(0,0){A}
\tkzDefPoint({\side*cos(-35)},{\side*sin(-35)}){B}
"""
    pts = extract_defined_points(tikz)
    import math
    assert "A" in pts
    assert "B" in pts
    assert pts["B"][0] == pytest.approx(6 * math.cos(math.radians(-35)), abs=1e-6)
    assert pts["B"][1] == pytest.approx(6 * math.sin(math.radians(-35)), abs=1e-6)


def test_extract_def_point_chained_macros():
    tikz = r"""
\pgfmathsetmacro{\s}{0.5}
\pgfmathsetmacro{\side}{6*\s}
\tkzDefPoint({\side*cos(0)},{\side*sin(0)}){B}
"""
    pts = extract_defined_points(tikz)
    assert pts["B"] == pytest.approx((3.0, 0.0), abs=1e-6)


def test_extract_def_point_with_addition_expression():
    tikz = r"""
\pgfmathsetmacro{\side}{6}
\tkzDefPoint(0,0){A}
\tkzDefPoint({\side*cos(-35)+\side*cos(35)},{\side*sin(-35)+\side*sin(35)}){C}
"""
    pts = extract_defined_points(tikz)
    import math
    expected_x = 6 * math.cos(math.radians(-35)) + 6 * math.cos(math.radians(35))
    expected_y = 6 * math.sin(math.radians(-35)) + 6 * math.sin(math.radians(35))
    assert pts["C"][0] == pytest.approx(expected_x, abs=1e-6)
    assert pts["C"][1] == pytest.approx(expected_y, abs=1e-6)


def test_extract_def_point_unsupported_expression_skipped():
    # Expression with an unsupported function: should silently skip rather
    # than crash or return a guess.
    tikz = r"""
\tkzDefPoint(0,0){A}
\tkzDefPoint({undefined_macro+1},0){B}
"""
    pts = extract_defined_points(tikz)
    assert "A" in pts
    assert "B" not in pts


def test_extract_def_point_expression_does_not_break_literal():
    # Literal coordinates must continue to parse even when expression-style
    # points appear elsewhere in the source.
    tikz = r"""
\pgfmathsetmacro{\side}{4}
\tkzDefPoint(1.5,2.5){A}
\tkzDefPoint({\side*cos(0)},{\side*sin(0)}){B}
"""
    pts = extract_defined_points(tikz)
    assert pts["A"] == pytest.approx((1.5, 2.5))
    assert pts["B"] == pytest.approx((4.0, 0.0), abs=1e-6)


def test_resolve_rhombus_via_expressions_passes_parallel_check():
    # Real-LLM TikZ shape (modeled on tpl-t2-rh-ABCD-s6-70). After hardening,
    # the parallel sides of the rhombus should be detected.
    tikz = r"""
\pgfmathsetmacro{\side}{6}
\tkzDefPoint(0,0){A}
\tkzDefPoint({\side*cos(-35)},{\side*sin(-35)}){B}
\tkzDefPoint({\side*cos(35)},{\side*sin(35)}){D}
\tkzDefPoint({\side*cos(-35)+\side*cos(35)},{\side*sin(-35)+\side*sin(35)}){C}
"""
    coords = resolve_all_coordinates(tikz)
    for n in ("A", "B", "C", "D"):
        assert n in coords, n
    assert validate_geometric_property(coords, "parallel", [["A", "B"], ["D", "C"]]) is True
    assert validate_geometric_property(coords, "parallel", [["B", "C"], ["A", "D"]]) is True
    assert validate_geometric_property(
        coords, "equal_lengths", [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]]
    ) is True


# ---------------------------------------------------------------------------
# Hardening pass §4.5 — circle-circle and line-circle intersections
# ---------------------------------------------------------------------------
# Real LLM outputs use \tkzInterCC and \tkzInterLC followed by \tkzGetPoints
# (plural) to capture the two intersection candidates. Without resolving these,
# every downstream property check (point_on_circle, equal_lengths involving
# the intersection points) is silently skipped → soft_pass instead of strict.

def test_extract_inter_cc_command():
    tikz = r"\tkzInterCC(O,A)(C,B) \tkzGetPoints{P}{Q}"
    computed = extract_computed_points(tikz)
    assert "P" in computed
    assert "Q" in computed
    assert computed["P"]["type"] == "inter_cc"
    assert computed["P"]["args"] == ["O", "A", "C", "B"]
    assert computed["P"]["which"] == 0
    assert computed["Q"]["type"] == "inter_cc"
    assert computed["Q"]["args"] == ["O", "A", "C", "B"]
    assert computed["Q"]["which"] == 1


def test_extract_inter_lc_command():
    tikz = r"\tkzInterLC(A,B)(O,T) \tkzGetPoints{X}{Y}"
    computed = extract_computed_points(tikz)
    assert "X" in computed
    assert "Y" in computed
    assert computed["X"]["type"] == "inter_lc"
    assert computed["X"]["args"] == ["A", "B", "O", "T"]
    assert computed["X"]["which"] == 0
    assert computed["Y"]["which"] == 1


def test_resolve_inter_cc_two_unit_circles():
    # Two unit circles centered at (0,0) and (2,0) → intersect at (1, ±√3·0.5...)
    # Actually: r1=r2=1, distance=2 → tangent at (1,0). Use radius = 1.5 instead.
    # Centers (0,0), (2,0) and r1 = r2 = 1.5 → x = 1; y = ±√(2.25 - 1) = ±√1.25
    tikz = r"""
\tkzDefPoint(0,0){O}
\tkzDefPoint(1.5,0){A}
\tkzDefPoint(2,0){C}
\tkzDefPoint(0.5,0){B}
\tkzInterCC(O,A)(C,B) \tkzGetPoints{P}{Q}
"""
    coords = resolve_all_coordinates(tikz)
    import math
    expected_y = math.sqrt(1.25)
    assert "P" in coords
    assert "Q" in coords
    # P (which=0) gets the lower-y solution by convention; Q gets upper.
    assert coords["P"][0] == pytest.approx(1.0, abs=1e-6)
    assert coords["Q"][0] == pytest.approx(1.0, abs=1e-6)
    assert {round(coords["P"][1], 4), round(coords["Q"][1], 4)} == {
        round(-expected_y, 4),
        round(expected_y, 4),
    }


def test_resolve_inter_cc_intersection_points_satisfy_both_circles():
    # The intersection points P,Q must lie on both circles regardless of
    # the lower/upper convention. This is the property our verifier needs.
    tikz = r"""
\tkzDefPoint(0,0){O}
\tkzDefPoint(2,0){A}
\tkzDefPoint(3,0){C}
\tkzDefPoint(5,0){B}
\tkzInterCC(O,A)(C,B) \tkzGetPoints{P}{Q}
"""
    coords = resolve_all_coordinates(tikz)
    # Circle 1: center O(0,0), radius |OA| = 2
    # Circle 2: center C(3,0), radius |CB| = 2
    import math
    for name in ("P", "Q"):
        d_to_O = math.dist(coords[name], (0, 0))
        d_to_C = math.dist(coords[name], (3, 0))
        assert d_to_O == pytest.approx(2.0, abs=1e-6), name
        assert d_to_C == pytest.approx(2.0, abs=1e-6), name


def test_resolve_inter_cc_non_intersecting_circles_omitted():
    # Two circles too far apart to intersect — should leave P, Q unresolved
    # rather than producing imaginary coordinates.
    tikz = r"""
\tkzDefPoint(0,0){O}
\tkzDefPoint(1,0){A}
\tkzDefPoint(10,0){C}
\tkzDefPoint(11,0){B}
\tkzInterCC(O,A)(C,B) \tkzGetPoints{P}{Q}
"""
    coords = resolve_all_coordinates(tikz)
    assert "P" not in coords
    assert "Q" not in coords


def test_resolve_inter_lc_secant_line():
    # Line y=0 cuts unit circle at (-1,0) and (1,0)
    tikz = r"""
\tkzDefPoint(-3,0){A}
\tkzDefPoint(3,0){B}
\tkzDefPoint(0,0){O}
\tkzDefPoint(1,0){T}
\tkzInterLC(A,B)(O,T) \tkzGetPoints{X}{Y}
"""
    coords = resolve_all_coordinates(tikz)
    assert "X" in coords
    assert "Y" in coords
    xs = sorted([coords["X"][0], coords["Y"][0]])
    assert xs[0] == pytest.approx(-1.0, abs=1e-6)
    assert xs[1] == pytest.approx(1.0, abs=1e-6)
    for name in ("X", "Y"):
        assert coords[name][1] == pytest.approx(0.0, abs=1e-6)


def test_resolve_inter_lc_tangent_line_returns_double_point():
    # Tangent line y=1 to unit circle at (0,1) — both X and Y should be the
    # tangent point.
    tikz = r"""
\tkzDefPoint(-2,1){A}
\tkzDefPoint(2,1){B}
\tkzDefPoint(0,0){O}
\tkzDefPoint(1,0){T}
\tkzInterLC(A,B)(O,T) \tkzGetPoints{X}{Y}
"""
    coords = resolve_all_coordinates(tikz)
    assert coords["X"] == pytest.approx((0.0, 1.0), abs=1e-6)
    assert coords["Y"] == pytest.approx((0.0, 1.0), abs=1e-6)


def test_resolve_inter_lc_non_intersecting_omitted():
    tikz = r"""
\tkzDefPoint(-2,5){A}
\tkzDefPoint(2,5){B}
\tkzDefPoint(0,0){O}
\tkzDefPoint(1,0){T}
\tkzInterLC(A,B)(O,T) \tkzGetPoints{X}{Y}
"""
    coords = resolve_all_coordinates(tikz)
    assert "X" not in coords
    assert "Y" not in coords


def test_inter_cc_then_point_on_circle_check_passes():
    # End-to-end: real-LLM-shape TikZ (modeled on tpl-t3-2cir-OC-PQ-5-5)
    # → intersection points should pass `point_on_circle` checks.
    tikz = r"""
\tkzDefPoint(0,0){O}
\tkzDefPoint(2,0){C}
\tkzDefPoint(2,0){A}
\tkzDefPoint(4,0){B}
\tkzInterCC(O,A)(C,B) \tkzGetPoints{P}{Q}
"""
    coords = resolve_all_coordinates(tikz)
    # P on circle (center=O, radius=|OA|): args=[P, O, A]
    assert validate_geometric_property(coords, "point_on_circle", ["P", "O", "A"]) is True
    assert validate_geometric_property(coords, "point_on_circle", ["Q", "O", "A"]) is True
    assert validate_geometric_property(coords, "point_on_circle", ["P", "C", "B"]) is True
    assert validate_geometric_property(coords, "point_on_circle", ["Q", "C", "B"]) is True


# ---------------------------------------------------------------------------
# Canvas feature extraction / validation
# ---------------------------------------------------------------------------

def test_extract_canvas_features_tkz_grid_and_axes():
    tikz = r"""
\tkzInit[xmin=-1,xmax=5,ymin=-1,ymax=5]
\tkzGrid
\tkzAxeXY
"""
    features = extract_canvas_features(tikz)
    assert features == {"grid": True, "axes": True}


def test_extract_canvas_features_raw_tikz_grid_and_axes():
    tikz = r"""
\draw[step=1cm,gray!40] (-2,-2) grid (2,2);
\draw[->] (-2,0) -- (2,0);
\draw[->] (0,-2) -- (0,2);
"""
    features = extract_canvas_features(tikz)
    assert features == {"grid": True, "axes": True}


def test_validate_required_canvas_missing_axes():
    tikz = r"\tkzGrid"
    result = validate_required_canvas(tikz, {"grid": True, "axes": True})
    assert result["passed"] is False
    assert result["missing"] == ["axes"]


# ---------------------------------------------------------------------------
# Expected-point validation
# ---------------------------------------------------------------------------

def test_validate_expected_points_passes():
    coords = {"A": (0.0, 0.0), "B": (4.0, 0.0)}
    result = validate_expected_points(coords, {"A": [0, 0], "B": [4, 0]}, tolerance=1e-4)
    assert result["passed"] is True
    assert result["missing"] == []
    assert result["mismatches"] == {}


def test_validate_expected_points_reports_missing_and_mismatch():
    coords = {"A": (0.0, 0.0), "B": (4.1, 0.0)}
    result = validate_expected_points(coords, {"A": [0, 0], "B": [4, 0], "C": [1, 1]}, tolerance=1e-4)
    assert result["passed"] is False
    assert result["missing"] == ["C"]
    assert "B" in result["mismatches"]


# ---------------------------------------------------------------------------
# not_between
# ---------------------------------------------------------------------------

def test_not_between_beyond_endpoint():
    # D is beyond C on line BC — not between B and C
    coords = {"B": (0.0, 0.0), "C": (2.0, 0.0), "D": (3.0, 0.0)}
    assert validate_geometric_property(coords, "not_between", ["D", "B", "C"]) is True


def test_not_between_before_start():
    # D is before B on line BC — not between B and C
    coords = {"B": (1.0, 0.0), "C": (3.0, 0.0), "D": (-1.0, 0.0)}
    assert validate_geometric_property(coords, "not_between", ["D", "B", "C"]) is True


def test_not_between_fails_when_strictly_between():
    # M is the midpoint of BC — is between B and C
    coords = {"B": (0.0, 0.0), "C": (4.0, 0.0), "M": (2.0, 0.0)}
    assert validate_geometric_property(coords, "not_between", ["M", "B", "C"]) is False


def test_not_between_off_line():
    # D is not collinear with B and C — trivially not between them
    coords = {"B": (0.0, 0.0), "C": (2.0, 0.0), "D": (1.0, 1.0)}
    assert validate_geometric_property(coords, "not_between", ["D", "B", "C"]) is True


def test_not_between_missing_coord_returns_none():
    coords = {"B": (0.0, 0.0), "C": (2.0, 0.0)}
    assert validate_geometric_property(coords, "not_between", ["D", "B", "C"]) is None


# ---------------------------------------------------------------------------
# opposite_side
# ---------------------------------------------------------------------------

def test_opposite_side_passes():
    # G1 is above line BC, A is below line BC
    coords = {
        "B": (0.0, 0.0), "C": (4.0, 0.0),
        "A": (2.0, -2.0),   # below BC (y < 0)
        "G1": (2.0, 2.0),   # above BC (y > 0)
    }
    assert validate_geometric_property(coords, "opposite_side", ["G1", "A", "B", "C"]) is True


def test_opposite_side_fails_same_side():
    # Both A and G are above BC
    coords = {
        "B": (0.0, 0.0), "C": (4.0, 0.0),
        "A": (2.0, 1.0),
        "G": (1.0, 3.0),
    }
    assert validate_geometric_property(coords, "opposite_side", ["G", "A", "B", "C"]) is False


def test_opposite_side_on_line_returns_none():
    # G lies exactly on line BC — ambiguous
    coords = {
        "B": (0.0, 0.0), "C": (4.0, 0.0),
        "A": (2.0, -1.0),
        "G": (2.0, 0.0),
    }
    assert validate_geometric_property(coords, "opposite_side", ["G", "A", "B", "C"]) is None


def test_opposite_side_missing_coord_returns_none():
    coords = {"B": (0.0, 0.0), "C": (4.0, 0.0), "A": (2.0, -1.0)}
    assert validate_geometric_property(coords, "opposite_side", ["G", "A", "B", "C"]) is None

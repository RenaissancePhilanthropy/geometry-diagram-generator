"""
Unit tests for util/tikz_analysis.py.
No Docker or renderer required — pure Python logic.
"""

import pytest

from util.tikz_analysis import (
    extract_defined_points,
    extract_computed_points,
    extract_draw_commands,
    extract_labels,
    extract_marks,
    resolve_all_coordinates,
    validate_geometric_property,
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

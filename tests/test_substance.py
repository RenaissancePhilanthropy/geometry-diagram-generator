"""Tests for ir.to_substance — converting the JSON IR to Penrose substance strings."""

import pytest

from ir import Constructor, Diagram, GeoObject, Predicate, to_substance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def lines(substance: str) -> list[str]:
    """Split substance into non-empty lines for easier assertion."""
    return [l for l in substance.splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# 1. Empty diagram
# ---------------------------------------------------------------------------

def test_empty_diagram():
    diagram = Diagram()
    assert to_substance(diagram) == ""


# ---------------------------------------------------------------------------
# 2. Bare point declarations
# ---------------------------------------------------------------------------

def test_bare_points():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="A"),
            GeoObject(type="Point", name="B"),
            GeoObject(type="Point", name="C"),
        ]
    )
    result = to_substance(diagram)
    assert result == "Point A, B, C"


def test_bare_mixed_types():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="A"),
            GeoObject(type="Point", name="B"),
            GeoObject(type="Plane", name="p"),
        ]
    )
    ls = lines(to_substance(diagram))
    assert "Point A, B" in ls
    assert "Plane p" in ls


# ---------------------------------------------------------------------------
# 3. Constructor declarations
# ---------------------------------------------------------------------------

def test_line_constructor():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="A"),
            GeoObject(type="Point", name="B"),
            GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
        ]
    )
    ls = lines(to_substance(diagram))
    assert "Point A, B" in ls
    assert "Line L1 := Line(A, B)" in ls


def test_interior_angle_constructor():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="A"),
            GeoObject(type="Point", name="B"),
            GeoObject(type="Point", name="C"),
            GeoObject(
                type="Angle",
                name="ABC",
                constructor=Constructor(name="InteriorAngle", args=["A", "B", "C"]),
            ),
        ]
    )
    ls = lines(to_substance(diagram))
    assert "Angle ABC := InteriorAngle(A, B, C)" in ls


def test_circle_constructor():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="O"),
            GeoObject(type="Point", name="R"),
            GeoObject(
                type="Circle",
                name="c",
                constructor=Constructor(name="CircleR", args=["O", "R"]),
            ),
        ]
    )
    ls = lines(to_substance(diagram))
    assert "Circle c := CircleR(O, R)" in ls


# ---------------------------------------------------------------------------
# 4. Predicates — object-only
# ---------------------------------------------------------------------------

def test_predicate_parallel():
    diagram = Diagram(
        objects=[
            GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
            GeoObject(type="Line", name="L2", constructor=Constructor(name="Line", args=["C", "D"])),
        ],
        predicates=[Predicate(name="Parallel", args=["L1", "L2"])],
    )
    ls = lines(to_substance(diagram))
    assert "Parallel(L1, L2)" in ls


def test_predicate_equilateral():
    diagram = Diagram(
        objects=[
            GeoObject(type="Triangle", name="T", constructor=Constructor(name="Triangle", args=["A", "B", "C"])),
        ],
        predicates=[Predicate(name="Equilateral", args=["T"])],
    )
    ls = lines(to_substance(diagram))
    assert "Equilateral(T)" in ls


# ---------------------------------------------------------------------------
# 5. Numeric predicate formatting
# ---------------------------------------------------------------------------

def test_numeric_integer_formatting():
    """Whole-number floats should render without decimal point."""
    diagram = Diagram(
        objects=[GeoObject(type="Point", name="A")],
        predicates=[
            Predicate(name="SetX", args=["A", -200.0]),
            Predicate(name="SetY", args=["A", 100.0]),
        ],
    )
    ls = lines(to_substance(diagram))
    assert "SetX(A, -200)" in ls
    assert "SetY(A, 100)" in ls


def test_numeric_float_formatting():
    """Non-integer floats keep their decimal representation."""
    diagram = Diagram(
        objects=[
            GeoObject(type="Angle", name="ang", constructor=Constructor(name="InteriorAngle", args=["A", "B", "C"])),
        ],
        predicates=[Predicate(name="SetAngle", args=["ang", 0.75])],
    )
    ls = lines(to_substance(diagram))
    assert "SetAngle(ang, 0.75)" in ls


# ---------------------------------------------------------------------------
# 6. AutoLabel
# ---------------------------------------------------------------------------

def test_auto_label():
    diagram = Diagram(
        objects=[GeoObject(type="Point", name="A"), GeoObject(type="Point", name="B")],
        auto_label=["A", "B"],
    )
    ls = lines(to_substance(diagram))
    assert "AutoLabel A, B" in ls


def test_no_auto_label_when_empty():
    diagram = Diagram(objects=[GeoObject(type="Point", name="A")])
    assert "AutoLabel" not in to_substance(diagram)


# ---------------------------------------------------------------------------
# 7. Ordering: bare declarations before constructor declarations
# ---------------------------------------------------------------------------

def test_ordering_bare_before_constructors():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="A"),
            GeoObject(type="Point", name="B"),
            GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
        ]
    )
    substance = to_substance(diagram)
    bare_pos = substance.index("Point A, B")
    constructor_pos = substance.index("Line L1 :=")
    assert bare_pos < constructor_pos


# ---------------------------------------------------------------------------
# 8. Full parallel-lines-with-transversal example (matches main.js substance)
# ---------------------------------------------------------------------------

PARALLEL_LINES_DIAGRAM = Diagram(
    objects=[
        GeoObject(type="Point", name="A"),
        GeoObject(type="Point", name="B"),
        GeoObject(type="Point", name="C"),
        GeoObject(type="Point", name="D"),
        GeoObject(type="Point", name="E"),
        GeoObject(type="Point", name="F"),
        GeoObject(type="Point", name="G"),
        GeoObject(type="Point", name="H"),
        GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
        GeoObject(type="Line", name="L2", constructor=Constructor(name="Line", args=["C", "D"])),
        GeoObject(type="Line", name="T", constructor=Constructor(name="Line", args=["G", "H"])),
        GeoObject(type="Angle", name="AEF", constructor=Constructor(name="InteriorAngle", args=["A", "E", "F"])),
        GeoObject(type="Angle", name="DFE", constructor=Constructor(name="InteriorAngle", args=["D", "F", "E"])),
        GeoObject(type="Angle", name="BEF", constructor=Constructor(name="InteriorAngle", args=["B", "E", "F"])),
        GeoObject(type="Angle", name="CFE", constructor=Constructor(name="InteriorAngle", args=["C", "F", "E"])),
    ],
    predicates=[
        Predicate(name="SetX", args=["A", -200.0]),
        Predicate(name="SetX", args=["B", 200.0]),
        Predicate(name="SetY", args=["A", -100.0]),
        Predicate(name="SetX", args=["C", -200.0]),
        Predicate(name="SetX", args=["D", 200.0]),
        Predicate(name="SetY", args=["C", 100.0]),
        Predicate(name="SetY", args=["H", -150.0]),
        Predicate(name="SetY", args=["G", 150.0]),
        Predicate(name="Parallel", args=["L1", "L2"]),
        Predicate(name="Horizontal", args=["L1"]),
        Predicate(name="EqualLength", args=["L1", "L2"]),
        Predicate(name="On", args=["E", "L1"]),
        Predicate(name="On", args=["F", "L2"]),
        Predicate(name="On", args=["E", "T"]),
        Predicate(name="On", args=["F", "T"]),
        Predicate(name="EqualAngleMarker", args=["AEF", "DFE"]),
        Predicate(name="EqualAngleMarker", args=["BEF", "CFE"]),
        Predicate(name="SetAngle", args=["AEF", 0.75]),
    ],
    auto_label=["A", "B", "C", "D", "E", "F", "G", "H"],
)


def test_parallel_lines_contains_all_declarations():
    ls = lines(to_substance(PARALLEL_LINES_DIAGRAM))
    assert "Point A, B, C, D, E, F, G, H" in ls


def test_parallel_lines_line_constructors():
    ls = lines(to_substance(PARALLEL_LINES_DIAGRAM))
    assert "Line L1 := Line(A, B)" in ls
    assert "Line L2 := Line(C, D)" in ls
    assert "Line T := Line(G, H)" in ls


def test_parallel_lines_angle_constructors():
    ls = lines(to_substance(PARALLEL_LINES_DIAGRAM))
    assert "Angle AEF := InteriorAngle(A, E, F)" in ls
    assert "Angle DFE := InteriorAngle(D, F, E)" in ls
    assert "Angle BEF := InteriorAngle(B, E, F)" in ls
    assert "Angle CFE := InteriorAngle(C, F, E)" in ls


def test_parallel_lines_predicates():
    ls = lines(to_substance(PARALLEL_LINES_DIAGRAM))
    assert "SetX(A, -200)" in ls
    assert "SetX(B, 200)" in ls
    assert "SetY(A, -100)" in ls
    assert "Parallel(L1, L2)" in ls
    assert "Horizontal(L1)" in ls
    assert "EqualLength(L1, L2)" in ls
    assert "On(E, L1)" in ls
    assert "On(F, L2)" in ls
    assert "EqualAngleMarker(AEF, DFE)" in ls
    assert "EqualAngleMarker(BEF, CFE)" in ls
    assert "SetAngle(AEF, 0.75)" in ls


def test_parallel_lines_auto_label():
    ls = lines(to_substance(PARALLEL_LINES_DIAGRAM))
    assert "AutoLabel A, B, C, D, E, F, G, H" in ls


# ---------------------------------------------------------------------------
# 9. Simple triangle
# ---------------------------------------------------------------------------

def test_simple_triangle():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="A"),
            GeoObject(type="Point", name="B"),
            GeoObject(type="Point", name="C"),
            GeoObject(
                type="Triangle",
                name="T",
                constructor=Constructor(name="Triangle", args=["A", "B", "C"]),
            ),
        ],
        predicates=[Predicate(name="Equilateral", args=["T"])],
        auto_label=["A", "B", "C"],
    )
    ls = lines(to_substance(diagram))
    assert "Point A, B, C" in ls
    assert "Triangle T := Triangle(A, B, C)" in ls
    assert "Equilateral(T)" in ls
    assert "AutoLabel A, B, C" in ls


# ---------------------------------------------------------------------------
# 10. Circle with OnCircle predicate
# ---------------------------------------------------------------------------

def test_circle_with_on_circle():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="O"),
            GeoObject(type="Point", name="R"),
            GeoObject(type="Point", name="P"),
            GeoObject(
                type="Circle",
                name="c",
                constructor=Constructor(name="CircleR", args=["O", "R"]),
            ),
        ],
        predicates=[Predicate(name="OnCircle", args=["c", "P"])],
        auto_label=["O", "R", "P"],
    )
    ls = lines(to_substance(diagram))
    assert "Circle c := CircleR(O, R)" in ls
    assert "OnCircle(c, P)" in ls
    assert "AutoLabel O, R, P" in ls

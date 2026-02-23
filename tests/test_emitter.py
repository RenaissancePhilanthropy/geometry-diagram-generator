"""Tests verifying PenroseEmitter works with both static and dynamic models."""
import pytest

from ir import PenroseEmitter, to_substance
from ir.domain import build_diagram_model, parse_domain
from ir.models import Diagram, GeoObject, Constructor, Predicate, StringLiteral

MINIMAL_DOMAIN = """
type Shape
type Point <: Shape
type Linelike <: Shape
type Line <: Linelike
type Segment <: Linelike

constructor Line(Point p, Point q)
constructor Segment(Point p, Point q)

symmetric predicate Parallel(Linelike, Linelike)
predicate SetX(Point, Number)
predicate Orientation(Linelike, String)
"""

# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def DomainModel():
    return build_diagram_model(parse_domain(MINIMAL_DOMAIN))


@pytest.fixture
def static_diagram():
    """Generates a static Diagram instance, i.e. one that is not built from a dynamic model, but directly constructed as a Python object."""
    return Diagram(
        objects=[
            GeoObject(type="Point", name="A"),
            GeoObject(type="Point", name="B"),
            GeoObject(type="Point", name="C"),
            GeoObject(type="Point", name="D"),
            GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
            GeoObject(type="Line", name="L2", constructor=Constructor(name="Line", args=["C", "D"])),
        ],
        predicates=[Predicate(name="Parallel", args=["L1", "L2"])],
        auto_label=["A", "B", "C", "D"],
    )


@pytest.fixture
def dynamic_diagram(DomainModel):
    """Generates a dynamic diagram model, i.e. a DomainModel instance that is constructed from a dictionary representation of the diagram, simulating what would be produced by a dynamic frontend."""
    return DomainModel(
        objects=[
            {"type": "Point", "name": "A"},
            {"type": "Point", "name": "B"},
            {"type": "Point", "name": "C"},
            {"type": "Point", "name": "D"},
            {"type": "Line", "name": "L1", "constructor": {"name": "Line", "args": ["A", "B"]}},
            {"type": "Line", "name": "L2", "constructor": {"name": "Line", "args": ["C", "D"]}},
        ],
        predicates=[{"name": "Parallel", "args": ["L1", "L2"]}],
        auto_label=["A", "B", "C", "D"],
    )


EXPECTED_OUTPUT = (
    "Point A, B, C, D\n"
    "Line L1 := Line(A, B)\n"
    "Line L2 := Line(C, D)\n"
    "Parallel(L1, L2)\n"
    "AutoLabel A, B, C, D"
)


# ── PenroseEmitter with static Diagram ──────────────────────────────────────────

class TestPenroseEmitterStatic:
    def test_emit_matches_expected(self, static_diagram):
        """Does PenroseEmitter.emit produce the expected substance string when given a static Diagram instance?"""
        assert PenroseEmitter().emit(static_diagram) == EXPECTED_OUTPUT

    def test_to_substance_wrapper_matches(self, static_diagram):
        """Does to_substance produce the expected substance string when given a static Diagram instance?"""
        assert to_substance(static_diagram) == EXPECTED_OUTPUT

    def test_number_arg(self):
        """Does to_substance correctly handle numeric arguments in predicates when given a static Diagram instance?"""
        d = Diagram(
            objects=[GeoObject(type="Point", name="A")],
            predicates=[Predicate(name="SetX", args=["A", -200.0])],
        )
        assert 'SetX(A, -200)' in to_substance(d)

    def test_string_literal_arg(self):
        """Does to_substance correctly handle string literal arguments in predicates when given a static Diagram instance?"""
        d = Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Line", name="L", constructor=Constructor(name="Line", args=["A", "B"])),
            ],
            predicates=[Predicate(name="Orientation", args=["L", StringLiteral(value="horizontal")])],
        )
        assert 'Orientation(L, "horizontal")' in to_substance(d)

    def test_empty_diagram(self):
        """Does to_substance produce an empty string when given an empty Diagram instance?"""
        assert to_substance(Diagram()) == ""

# ── PenroseEmitter with dynamic model ───────────────────────────────────────────

class TestPenroseEmitterDynamic:
    def test_emit_matches_expected(self, dynamic_diagram):
        """Does PenroseEmitter.emit produce the expected substance string when given a dynamic diagram model?"""
        assert PenroseEmitter().emit(dynamic_diagram) == EXPECTED_OUTPUT

    def test_to_substance_wrapper_matches(self, dynamic_diagram):
        """Does to_substance produce the expected substance string when given a dynamic diagram model?"""
        assert to_substance(dynamic_diagram) == EXPECTED_OUTPUT

    def test_output_identical_to_static(self, static_diagram, dynamic_diagram):
        """Does to_substance produce the same output for both static and dynamic diagrams representing the same content?"""
        assert to_substance(dynamic_diagram) == to_substance(static_diagram)

    def test_number_arg(self, DomainModel):
        """Does to_substance correctly handle numeric arguments in predicates when given a dynamic diagram model?"""
        d = DomainModel(
            objects=[{"type": "Point", "name": "A"}],
            predicates=[{"name": "SetX", "args": ["A", -200.0]}],
        )
        assert 'SetX(A, -200)' in to_substance(d)

    def test_string_literal_arg(self, DomainModel):
        """Does to_substance correctly handle string literal arguments in predicates when given a dynamic diagram model?"""
        d = DomainModel(
            objects=[
                {"type": "Point", "name": "A"},
                {"type": "Point", "name": "B"},
                {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["A", "B"]}},
            ],
            predicates=[{"name": "Orientation", "args": ["L", {"value": "horizontal"}]}],
        )
        assert 'Orientation(L, "horizontal")' in to_substance(d)

    def test_empty_diagram(self, DomainModel):
        """Does to_substance produce an empty string when given an empty diagram model?"""
        assert to_substance(DomainModel()) == ""


# ── DiagramLike protocol ─────────────────────────────────────────────────────────

class TestDiagramLikeProtocol:
    def test_static_diagram_satisfies_protocol(self, static_diagram):
        from ir.emitter import DiagramLike
        assert isinstance(static_diagram, DiagramLike)

    def test_dynamic_diagram_satisfies_protocol(self, dynamic_diagram):
        from ir.emitter import DiagramLike
        assert isinstance(dynamic_diagram, DiagramLike)

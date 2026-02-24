"""Tests for ir/domain.py: domain parsing, type hierarchy, and dynamic model building."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from ir.domain import DomainInfo, build_diagram_model, is_subtype, parse_domain
from ir.models import StringLiteral

# ─── Minimal domain used for most unit tests ───

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
predicate On(Point, Linelike)
predicate Collinear(Point, Point, Point)
"""


# ══════════════════════════════════════════════════════════
# parse_domain
# ══════════════════════════════════════════════════════════

class TestParseDomain:
    def test_types_present(self):
        info = parse_domain(MINIMAL_DOMAIN)
        assert {"Shape", "Point", "Linelike", "Line", "Segment"} <= info.types

    def test_type_hierarchy(self):
        info = parse_domain(MINIMAL_DOMAIN)
        assert info.type_parents["Point"] == "Shape"
        assert info.type_parents["Linelike"] == "Shape"
        assert info.type_parents["Line"] == "Linelike"
        assert info.type_parents["Segment"] == "Linelike"
        assert "Shape" not in info.type_parents  # base type has no parent

    def test_constructors_with_named_params(self):
        info = parse_domain(MINIMAL_DOMAIN)
        assert info.constructors["Line"] == ["Point", "Point"]
        assert info.constructors["Segment"] == ["Point", "Point"]

    def test_predicates(self):
        info = parse_domain(MINIMAL_DOMAIN)
        assert info.predicates["Parallel"] == ["Linelike", "Linelike"]
        assert info.predicates["SetX"] == ["Point", "Number"]
        assert info.predicates["Orientation"] == ["Linelike", "String"]
        assert info.predicates["Collinear"] == ["Point", "Point", "Point"]

    def test_functions_treated_as_constructors(self):
        domain = MINIMAL_DOMAIN + "\ntype Angle <: Shape\ntype Ray <: Linelike\nfunction Bisector(Angle) -> Ray\n"
        info = parse_domain(domain)
        assert "Bisector" in info.constructors
        assert info.constructors["Bisector"] == ["Angle"]

    def test_comments_stripped(self):
        domain = "type Shape -- this is the base type\ntype Point <: Shape -- a point\n"
        info = parse_domain(domain)
        assert "Shape" in info.types
        assert "Point" in info.types
        assert info.type_parents["Point"] == "Shape"

    def test_full_geometry_domain(self):
        domain_path = Path("demo-ui/geometry.domain")
        if not domain_path.exists():
            pytest.skip("geometry.domain not found")
        info = parse_domain(domain_path.read_text())
        assert "Point" in info.types
        assert "Triangle" in info.types
        assert "Circle" in info.types
        assert "Line" in info.constructors
        assert info.constructors["InteriorAngle"] == ["Point", "Point", "Point"]
        assert "Bisector" in info.constructors  # came from a function declaration
        assert "Parallel" in info.predicates
        assert "Orientation" in info.predicates


# ══════════════════════════════════════════════════════════
# is_subtype
# ══════════════════════════════════════════════════════════

class TestIsSubtype:
    PARENTS = {"Point": "Shape", "Linelike": "Shape", "Line": "Linelike", "Segment": "Linelike"}

    def test_same_type(self):
        assert is_subtype("Point", "Point", self.PARENTS)
        assert is_subtype("Line", "Line", self.PARENTS)
        assert is_subtype("Shape", "Shape", self.PARENTS)

    def test_direct_parent(self):
        assert is_subtype("Line", "Linelike", self.PARENTS)
        assert is_subtype("Segment", "Linelike", self.PARENTS)
        assert is_subtype("Point", "Shape", self.PARENTS)

    def test_transitive(self):
        assert is_subtype("Line", "Shape", self.PARENTS)
        assert is_subtype("Segment", "Shape", self.PARENTS)

    def test_sibling_is_not_subtype(self):
        assert not is_subtype("Point", "Linelike", self.PARENTS)
        assert not is_subtype("Linelike", "Point", self.PARENTS)

    def test_parent_is_not_subtype_of_child(self):
        assert not is_subtype("Shape", "Point", self.PARENTS)
        assert not is_subtype("Linelike", "Line", self.PARENTS)

    def test_unknown_type(self):
        assert not is_subtype("Unknown", "Shape", self.PARENTS)


# ══════════════════════════════════════════════════════════
# build_diagram_model — field-level name constraints
# ══════════════════════════════════════════════════════════

@pytest.fixture
def Model():
    return build_diagram_model(parse_domain(MINIMAL_DOMAIN))


class TestFieldConstraints:
    def test_valid_type_accepted(self, Model):
        d = Model(objects=[{"type": "Point", "name": "A"}])
        assert d.objects[0].type == "Point"

    def test_invalid_type_rejected(self, Model):
        with pytest.raises(ValidationError):
            Model(objects=[{"type": "FakeType", "name": "X"}])

    def test_valid_constructor_name(self, Model):
        d = Model(objects=[
            {"type": "Point", "name": "A"},
            {"type": "Point", "name": "B"},
            {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["A", "B"]}},
        ])
        assert d.objects[2].constructor.name == "Line"

    def test_invalid_constructor_name_rejected(self, Model):
        with pytest.raises(ValidationError):
            Model(objects=[
                {"type": "Line", "name": "L", "constructor": {"name": "FakeCtor", "args": []}},
            ])

    def test_valid_predicate_name(self, Model):
        d = Model(
            objects=[
                {"type": "Point", "name": "A"},
                {"type": "Point", "name": "B"},
                {"type": "Line", "name": "L1", "constructor": {"name": "Line", "args": ["A", "B"]}},
                {"type": "Point", "name": "C"},
                {"type": "Point", "name": "D"},
                {"type": "Line", "name": "L2", "constructor": {"name": "Line", "args": ["C", "D"]}},
            ],
            predicates=[{"name": "Parallel", "args": ["L1", "L2"]}],
        )
        assert d.predicates[0].name == "Parallel"

    def test_invalid_predicate_name_rejected(self, Model):
        with pytest.raises(ValidationError):
            Model(predicates=[{"name": "NotAPredicate", "args": []}])


# ══════════════════════════════════════════════════════════
# build_diagram_model — cross-field semantic validation
# ══════════════════════════════════════════════════════════

class TestSemanticValidation:
    def test_wrong_arg_count_predicate(self, Model):
        with pytest.raises(ValidationError, match="expects 2 argument"):
            Model(
                objects=[
                    {"type": "Point", "name": "A"},
                    {"type": "Point", "name": "B"},
                    {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["A", "B"]}},
                ],
                predicates=[{"name": "Parallel", "args": ["L"]}],  # needs 2, got 1
            )

    def test_wrong_arg_count_constructor(self, Model):
        with pytest.raises(ValidationError, match="expects 2 argument"):
            Model(objects=[
                {"type": "Point", "name": "A"},
                {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["A"]}},  # needs 2
            ])

    def test_incompatible_arg_type_rejected(self, Model):
        # Parallel expects (Linelike, Linelike); passing Point where Linelike expected
        with pytest.raises(ValidationError, match="Linelike"):
            Model(
                objects=[
                    {"type": "Point", "name": "A"},
                    {"type": "Point", "name": "B"},
                    {"type": "Point", "name": "C"},
                    {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["B", "C"]}},
                ],
                predicates=[{"name": "Parallel", "args": ["A", "L"]}],  # A is Point, not Linelike
            )

    def test_subtype_accepted(self, Model):
        # Line <: Linelike, so Line should be accepted where Linelike is expected
        d = Model(
            objects=[
                {"type": "Point", "name": "A"},
                {"type": "Point", "name": "B"},
                {"type": "Point", "name": "C"},
                {"type": "Point", "name": "D"},
                {"type": "Line", "name": "L1", "constructor": {"name": "Line", "args": ["A", "B"]}},
                {"type": "Line", "name": "L2", "constructor": {"name": "Line", "args": ["C", "D"]}},
            ],
            predicates=[{"name": "Parallel", "args": ["L1", "L2"]}],
        )
        assert len(d.predicates) == 1

    def test_segment_subtype_accepted(self, Model):
        # Segment <: Linelike, so it should also be valid where Linelike expected
        d = Model(
            objects=[
                {"type": "Point", "name": "A"},
                {"type": "Point", "name": "B"},
                {"type": "Segment", "name": "S", "constructor": {"name": "Segment", "args": ["A", "B"]}},
                {"type": "Point", "name": "C"},
                {"type": "Point", "name": "D"},
                {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["C", "D"]}},
            ],
            predicates=[{"name": "Parallel", "args": ["S", "L"]}],
        )
        assert len(d.predicates) == 1

    def test_number_arg_accepted(self, Model):
        d = Model(
            objects=[{"type": "Point", "name": "A"}],
            predicates=[{"name": "SetX", "args": ["A", -200.0]}],
        )
        assert d.predicates[0].args[1] == -200.0

    def test_string_literal_arg_accepted(self, Model):
        d = Model(
            objects=[
                {"type": "Point", "name": "A"},
                {"type": "Point", "name": "B"},
                {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["A", "B"]}},
            ],
            predicates=[{"name": "Orientation", "args": ["L", {"value": "horizontal"}]}],
        )
        assert d.predicates[0].args[1].value == "horizontal"

    def test_plain_string_coerced_to_string_literal(self, Model):
        # LLMs naturally output plain strings; they should be auto-coerced for String params
        d = Model(
            objects=[
                {"type": "Point", "name": "A"},
                {"type": "Point", "name": "B"},
                {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["A", "B"]}},
            ],
            predicates=[{"name": "Orientation", "args": ["L", "horizontal"]}],
        )
        from ir.models import StringLiteral
        assert isinstance(d.predicates[0].args[1], StringLiteral)
        assert d.predicates[0].args[1].value == "horizontal"

    def test_string_literal_where_number_rejected(self, Model):
        # SetX expects (Point, Number); passing StringLiteral where Number expected
        with pytest.raises(ValidationError, match="Number"):
            Model(
                objects=[{"type": "Point", "name": "A"}],
                predicates=[{"name": "SetX", "args": ["A", {"value": "oops"}]}],
            )

    def test_object_ref_where_number_rejected(self, Model):
        # SetX expects (Point, Number); passing another object name where Number expected
        with pytest.raises(ValidationError, match="Number"):
            Model(
                objects=[
                    {"type": "Point", "name": "A"},
                    {"type": "Point", "name": "B"},
                ],
                predicates=[{"name": "SetX", "args": ["A", "B"]}],
            )

    def test_undeclared_object_reference_rejected(self, Model):
        with pytest.raises(ValidationError, match="undeclared"):
            Model(predicates=[{"name": "Parallel", "args": ["L1", "L2"]}])

    def test_duplicate_object_name_rejected(self, Model):
        with pytest.raises(ValidationError, match="Duplicate"):
            Model(objects=[
                {"type": "Point", "name": "A"},
                {"type": "Point", "name": "A"},
            ])

    def test_undeclared_constructor_arg_rejected(self, Model):
        with pytest.raises(ValidationError, match="undeclared"):
            Model(objects=[
                # B is not declared, so Line(A, B) should fail
                {"type": "Point", "name": "A"},
                {"type": "Line", "name": "L", "constructor": {"name": "Line", "args": ["A", "B"]}},
            ])

    def test_undeclared_auto_label_rejected(self, Model):
        with pytest.raises(ValidationError, match="undeclared"):
            Model(
                objects=[{"type": "Point", "name": "A"}],
                auto_label=["A", "Z"],  # Z not declared
            )

    def test_valid_auto_label_accepted(self, Model):
        d = Model(
            objects=[
                {"type": "Point", "name": "A"},
                {"type": "Point", "name": "B"},
            ],
            auto_label=["A", "B"],
        )
        assert d.auto_label == ["A", "B"]

    def test_empty_diagram_valid(self, Model):
        d = Model()
        assert d.objects == []
        assert d.predicates == []
        assert d.auto_label == []

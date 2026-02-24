"""Tests for util/svg_checks.py: check harness, geometry extraction, and check functions."""
import pytest

from ir.models import Diagram, GeoObject, Constructor, Predicate
from util.svg_checks import (
    CheckFn,
    SVGGeometry,
    check_elements_in_bounds,
    check_no_collapsed_points,
    checks_from_diagram,
    extract_geometry,
    run_checks,
)

# ---------------------------------------------------------------------------
# Minimal SVG fixtures
# ---------------------------------------------------------------------------

def _svg(body: str, viewbox: str = "0 0 500 500") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">'
        f'{body}'
        f'</svg>'
    )


def _circle(name: str, cx: float, cy: float) -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="4"><title>`{name}`.icon</title></circle>'


def _line_direct(name: str, x1: float, y1: float, x2: float, y2: float) -> str:
    """Segment-style: title on the <line> itself."""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
        f'<title>`{name}`.icon</title>'
        f'</line>'
    )


def _line_group(name: str, x1: float, y1: float, x2: float, y2: float) -> str:
    """Line-style: title on the parent <g>."""
    return (
        f'<g><title>`{name}`.icon</title>'
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"></line>'
        f'</g>'
    )


# ---------------------------------------------------------------------------
# extract_geometry
# ---------------------------------------------------------------------------

class TestExtractGeometry:
    def test_parses_viewbox(self):
        svg = _svg("")
        geom = extract_geometry(svg)
        assert geom.view_box == (0.0, 0.0, 500.0, 500.0)

    def test_parses_circles(self):
        svg = _svg(_circle("A", 100, 200) + _circle("B", 300, 400))
        geom = extract_geometry(svg)
        assert geom.point_positions["A"] == (100.0, 200.0)
        assert geom.point_positions["B"] == (300.0, 400.0)

    def test_parses_direct_line(self):
        # Segment-style: title on the <line>
        svg = _svg(_line_direct("AB", 10, 20, 30, 40))
        geom = extract_geometry(svg)
        assert geom.line_endpoints["AB"] == (10.0, 20.0, 30.0, 40.0)

    def test_parses_group_line(self):
        # Line-style: title on the parent <g>
        svg = _svg(_line_group("L1", 50, 60, 70, 80))
        geom = extract_geometry(svg)
        assert geom.line_endpoints["L1"] == (50.0, 60.0, 70.0, 80.0)

    def test_missing_viewbox(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
        geom = extract_geometry(svg)
        assert geom.view_box is None

    def test_empty_svg(self):
        geom = extract_geometry(_svg(""))
        assert geom.point_positions == {}
        assert geom.line_endpoints == {}


# ---------------------------------------------------------------------------
# run_checks
# ---------------------------------------------------------------------------

class TestRunChecks:
    def _passing_check(self, svg: str, diagram) -> str | None:
        return None

    def _failing_check(self, svg: str, diagram) -> str | None:
        return "always fails"

    def test_empty_checks_passes(self):
        assert run_checks("", Diagram(), []) == []

    def test_all_passing(self):
        assert run_checks("", Diagram(), [self._passing_check, self._passing_check]) == []

    def test_single_failure(self):
        failures = run_checks("", Diagram(), [self._failing_check])
        assert failures == ["always fails"]

    def test_multiple_failures_collected(self):
        def fail_a(svg, d): return "fail A"
        def fail_b(svg, d): return "fail B"
        failures = run_checks("", Diagram(), [fail_a, fail_b])
        assert "fail A" in failures
        assert "fail B" in failures

    def test_mixed_pass_and_fail(self):
        failures = run_checks("", Diagram(), [self._passing_check, self._failing_check])
        assert len(failures) == 1


# ---------------------------------------------------------------------------
# check_no_collapsed_points
# ---------------------------------------------------------------------------

class TestCheckNoCollapsedPoints:
    def test_distinct_points_pass(self):
        svg = _svg(_circle("A", 100, 100) + _circle("B", 200, 200))
        assert check_no_collapsed_points(svg, Diagram()) is None

    def test_identical_positions_fail(self):
        svg = _svg(_circle("A", 100, 100) + _circle("B", 100, 100))
        result = check_no_collapsed_points(svg, Diagram())
        assert result is not None
        assert "A" in result or "B" in result

    def test_near_identical_within_epsilon_fail(self):
        svg = _svg(_circle("A", 100.0, 100.0) + _circle("B", 100.4, 100.4))
        result = check_no_collapsed_points(svg, Diagram())
        assert result is not None  # 0.57px < 1px epsilon

    def test_single_point_passes(self):
        svg = _svg(_circle("A", 100, 100))
        assert check_no_collapsed_points(svg, Diagram()) is None

    def test_no_circles_passes(self):
        assert check_no_collapsed_points(_svg(""), Diagram()) is None


# ---------------------------------------------------------------------------
# check_elements_in_bounds
# ---------------------------------------------------------------------------

class TestCheckElementsInBounds:
    def test_in_bounds_passes(self):
        svg = _svg(_circle("A", 250, 250))
        assert check_elements_in_bounds(svg, Diagram()) is None

    def test_circle_out_of_bounds_fails(self):
        svg = _svg(_circle("A", 600, 250))  # x=600 > 500
        result = check_elements_in_bounds(svg, Diagram())
        assert result is not None
        assert "A" in result

    def test_line_endpoint_out_of_bounds_fails(self):
        svg = _svg(_line_direct("L", 10, 10, 600, 10))
        result = check_elements_in_bounds(svg, Diagram())
        assert result is not None

    def test_no_viewbox_skips(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="600" cy="600" r="4"><title>`A`.icon</title></circle></svg>'
        assert check_elements_in_bounds(svg, Diagram()) is None


# ---------------------------------------------------------------------------
# checks_from_diagram — Parallel
# ---------------------------------------------------------------------------

class TestChecksFromDiagram:
    def test_no_registered_predicates_returns_empty(self):
        diagram = Diagram(predicates=[Predicate(name="On", args=["A", "L"])])
        assert checks_from_diagram(diagram) == []

    def test_parallel_check_generated(self):
        diagram = Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Point", name="C"),
                GeoObject(type="Point", name="D"),
                GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
                GeoObject(type="Line", name="L2", constructor=Constructor(name="Line", args=["C", "D"])),
            ],
            predicates=[Predicate(name="Parallel", args=["L1", "L2"])],
        )
        checks = checks_from_diagram(diagram)
        assert len(checks) == 1

    def test_parallel_check_passes_for_parallel_lines(self):
        # L1 horizontal, L2 horizontal → parallel
        svg = _svg(
            _circle("A", 100, 200) + _circle("B", 300, 200) +  # horizontal
            _circle("C", 100, 300) + _circle("D", 300, 300)    # horizontal
        )
        diagram = Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Point", name="C"),
                GeoObject(type="Point", name="D"),
                GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
                GeoObject(type="Line", name="L2", constructor=Constructor(name="Line", args=["C", "D"])),
            ],
            predicates=[Predicate(name="Parallel", args=["L1", "L2"])],
        )
        checks = checks_from_diagram(diagram)
        assert run_checks(svg, diagram, checks) == []

    def test_parallel_check_fails_for_non_parallel_lines(self):
        # L1 horizontal, L2 vertical → not parallel (90°)
        svg = _svg(
            _circle("A", 100, 200) + _circle("B", 300, 200) +  # horizontal
            _circle("C", 200, 100) + _circle("D", 200, 400)    # vertical
        )
        diagram = Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Point", name="C"),
                GeoObject(type="Point", name="D"),
                GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
                GeoObject(type="Line", name="L2", constructor=Constructor(name="Line", args=["C", "D"])),
            ],
            predicates=[Predicate(name="Parallel", args=["L1", "L2"])],
        )
        checks = checks_from_diagram(diagram)
        failures = run_checks(svg, diagram, checks)
        assert len(failures) == 1
        assert "Parallel" in failures[0]

    def test_parallel_check_skips_when_points_missing(self):
        # No circles in SVG — can't resolve geometry, should skip gracefully
        diagram = Diagram(
            objects=[
                GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
                GeoObject(type="Line", name="L2", constructor=Constructor(name="Line", args=["C", "D"])),
            ],
            predicates=[Predicate(name="Parallel", args=["L1", "L2"])],
        )
        checks = checks_from_diagram(diagram)
        assert run_checks(_svg(""), diagram, checks) == []


# ---------------------------------------------------------------------------
# Perpendicular predicate check
# ---------------------------------------------------------------------------

class TestPerpendicularCheck:
    def _diagram(self):
        return Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Point", name="C"),
                GeoObject(type="Point", name="D"),
                GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
                GeoObject(type="Line", name="L2", constructor=Constructor(name="Line", args=["C", "D"])),
            ],
            predicates=[Predicate(name="Perpendicular", args=["L1", "L2"])],
        )

    def test_passes_for_perpendicular_lines(self):
        # L1 horizontal, L2 vertical → perpendicular
        svg = _svg(
            _circle("A", 100, 200) + _circle("B", 300, 200) +
            _circle("C", 200, 100) + _circle("D", 200, 400)
        )
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(svg, diagram, checks) == []

    def test_fails_for_parallel_lines(self):
        # Both horizontal → 0° apart, not 90°
        svg = _svg(
            _circle("A", 100, 200) + _circle("B", 300, 200) +
            _circle("C", 100, 300) + _circle("D", 300, 300)
        )
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        failures = run_checks(svg, diagram, checks)
        assert len(failures) == 1
        assert "Perpendicular" in failures[0]

    def test_skips_when_points_missing(self):
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(_svg(""), diagram, checks) == []


# ---------------------------------------------------------------------------
# Collinear predicate check
# ---------------------------------------------------------------------------

class TestCollinearCheck:
    def _diagram(self, p1="A", p2="B", p3="C"):
        return Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Point", name="C"),
            ],
            predicates=[Predicate(name="Collinear", args=[p1, p2, p3])],
        )

    def test_passes_for_collinear_points(self):
        # A, B, C all on y=200 horizontal line
        svg = _svg(_circle("A", 100, 200) + _circle("B", 200, 200) + _circle("C", 300, 200))
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(svg, diagram, checks) == []

    def test_fails_for_non_collinear_points(self):
        # Triangle: A(100,400), B(200,100), C(300,400)
        svg = _svg(_circle("A", 100, 400) + _circle("B", 200, 100) + _circle("C", 300, 400))
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        failures = run_checks(svg, diagram, checks)
        assert len(failures) == 1
        assert "Collinear" in failures[0]

    def test_skips_when_points_missing(self):
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(_svg(""), diagram, checks) == []


# ---------------------------------------------------------------------------
# NonCollinear predicate check
# ---------------------------------------------------------------------------

class TestNonCollinearCheck:
    def _diagram(self, p1="A", p2="B", p3="C"):
        return Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Point", name="C"),
            ],
            predicates=[Predicate(name="NonCollinear", args=[p1, p2, p3])],
        )

    def test_passes_for_non_collinear_points(self):
        # Triangle: A(100,400), B(200,100), C(300,400)
        svg = _svg(_circle("A", 100, 400) + _circle("B", 200, 100) + _circle("C", 300, 400))
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(svg, diagram, checks) == []

    def test_fails_for_collinear_points(self):
        # All on y=200
        svg = _svg(_circle("A", 100, 200) + _circle("B", 200, 200) + _circle("C", 300, 200))
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        failures = run_checks(svg, diagram, checks)
        assert len(failures) == 1
        assert "NonCollinear" in failures[0]

    def test_skips_when_points_missing(self):
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(_svg(""), diagram, checks) == []


# ---------------------------------------------------------------------------
# EqualLength predicate check
# ---------------------------------------------------------------------------

class TestEqualLengthCheck:
    def _diagram(self):
        return Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Point", name="C"),
                GeoObject(type="Point", name="D"),
                GeoObject(type="Segment", name="S1", constructor=Constructor(name="Segment", args=["A", "B"])),
                GeoObject(type="Segment", name="S2", constructor=Constructor(name="Segment", args=["C", "D"])),
            ],
            predicates=[Predicate(name="EqualLength", args=["S1", "S2"])],
        )

    def test_passes_for_equal_length_segments(self):
        # S1: A(100,200)→B(300,200) = 200px; S2: C(100,300)→D(300,300) = 200px
        svg = _svg(
            _circle("A", 100, 200) + _circle("B", 300, 200) +
            _circle("C", 100, 300) + _circle("D", 300, 300)
        )
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(svg, diagram, checks) == []

    def test_fails_for_very_different_lengths(self):
        # S1: 200px, S2: 20px
        svg = _svg(
            _circle("A", 100, 200) + _circle("B", 300, 200) +
            _circle("C", 100, 300) + _circle("D", 120, 300)
        )
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        failures = run_checks(svg, diagram, checks)
        assert len(failures) == 1
        assert "EqualLength" in failures[0]

    def test_passes_for_segments_within_tolerance(self):
        # S1: 200px, S2: 195px → 2.5% difference, within 15% tolerance
        svg = _svg(
            _circle("A", 100, 200) + _circle("B", 300, 200) +
            _circle("C", 100, 300) + _circle("D", 295, 300)
        )
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(svg, diagram, checks) == []

    def test_skips_when_points_missing(self):
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(_svg(""), diagram, checks) == []


# ---------------------------------------------------------------------------
# Horizontal predicate check
# ---------------------------------------------------------------------------

class TestHorizontalCheck:
    def _diagram(self):
        return Diagram(
            objects=[
                GeoObject(type="Point", name="A"),
                GeoObject(type="Point", name="B"),
                GeoObject(type="Line", name="L1", constructor=Constructor(name="Line", args=["A", "B"])),
            ],
            predicates=[Predicate(name="Horizontal", args=["L1"])],
        )

    def test_passes_for_horizontal_line(self):
        svg = _svg(_circle("A", 100, 200) + _circle("B", 300, 200))
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(svg, diagram, checks) == []

    def test_fails_for_vertical_line(self):
        svg = _svg(_circle("A", 200, 100) + _circle("B", 200, 400))
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        failures = run_checks(svg, diagram, checks)
        assert len(failures) == 1
        assert "Horizontal" in failures[0]

    def test_fails_for_diagonal_line(self):
        # 45° diagonal
        svg = _svg(_circle("A", 100, 100) + _circle("B", 300, 300))
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        failures = run_checks(svg, diagram, checks)
        assert len(failures) == 1
        assert "Horizontal" in failures[0]

    def test_skips_when_points_missing(self):
        diagram = self._diagram()
        checks = checks_from_diagram(diagram)
        assert run_checks(_svg(""), diagram, checks) == []

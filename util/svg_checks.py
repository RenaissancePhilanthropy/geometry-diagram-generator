"""
SVG quality check harness for Penrose-rendered diagrams.

Two layers:
  - General checks (static functions): always run regardless of diagram content.
  - Predicate-driven checks (registry): generated from diagram.predicates, so
    checks like Parallel can verify that rendered geometry actually obeys the
    constraint.

Adding a new predicate check:
  1. Write a factory: (pred, diagram) -> CheckFn | None
  2. Register it: PREDICATE_CHECKS["YourPredicate"] = your_factory
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable
from logging import getLogger

from ir.emitter import DiagramLike

logger = getLogger(__name__)

# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

# None = passed, str = failure message
CheckFn = Callable[[str, DiagramLike], "str | None"]
PredicateCheckFactory = Callable[..., "CheckFn | None"]  # (pred, diagram) -> CheckFn | None


def run_checks(svg: str, diagram: DiagramLike, checks: list[CheckFn]) -> list[str]:
    """Run all checks. Returns a list of failure messages (empty = all passed)."""
    failures = []
    for check in checks:
        result = check(svg, diagram)
        if result is not None:
            failures.append(result)
    logger.debug(f"Completed {len(checks)} checks with {len(failures)} failures")
    return failures


# ---------------------------------------------------------------------------
# SVG geometry extraction
# ---------------------------------------------------------------------------

_TITLE_ICON_RE = re.compile(r"^`(.+)`\.icon$")


def _strip_ns(tag: str) -> str:
    return tag.split('}', 1)[-1] if '}' in tag else tag


def _icon_name(element: ET.Element) -> str | None:
    """If element has a child <title> matching `NAME`.icon, return NAME."""
    for child in element:
        if _strip_ns(child.tag) == 'title':
            m = _TITLE_ICON_RE.match((child.text or '').strip())
            return m.group(1) if m else None
    return None


@dataclass
class SVGGeometry:
    """Named element positions extracted from a rendered Penrose SVG."""
    # name → (cx, cy) from <circle title="`NAME`.icon"> elements
    point_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    # name → (x1, y1, x2, y2) from <line title="`NAME`.icon"> elements
    line_endpoints: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    # (min_x, min_y, width, height) or None
    view_box: tuple[float, float, float, float] | None = None


def extract_geometry(svg: str) -> SVGGeometry:
    """Parse a Penrose SVG and extract named element geometry via <title> tags."""
    root = ET.fromstring(svg)
    geom = SVGGeometry()

    vb = root.get('viewBox')
    if vb:
        parts = vb.split()
        if len(parts) == 4:
            geom.view_box = (float(parts[0]), float(parts[1]),
                             float(parts[2]), float(parts[3]))

    for elem in root.iter():
        tag = _strip_ns(elem.tag)
        name = _icon_name(elem)
        if name is None:
            continue
        if tag == 'circle':
            try:
                geom.point_positions[name] = (float(elem.get('cx', 0)),
                                              float(elem.get('cy', 0)))
            except (ValueError, TypeError):
                logger.warning(f"Failed to extract point position for '{name}'")
        elif tag == 'line':
            # Segment pattern: <line title="`NAME`.icon"> directly on the element
            try:
                geom.line_endpoints[name] = (float(elem.get('x1', 0)),
                                             float(elem.get('y1', 0)),
                                             float(elem.get('x2', 0)),
                                             float(elem.get('y2', 0)))
            except (ValueError, TypeError):
                logger.warning(f"Failed to extract line endpoints for '{name}'")
        elif tag == 'g':
            # Line pattern: <g title="`NAME`.icon"><line ...> — title is on the group
            for child in elem:
                if _strip_ns(child.tag) == 'line':
                    try:
                        geom.line_endpoints[name] = (float(child.get('x1', 0)),
                                                     float(child.get('y1', 0)),
                                                     float(child.get('x2', 0)),
                                                     float(child.get('y2', 0)))
                    except (ValueError, TypeError):
                        logger.warning(f"Failed to extract line endpoints for '{name}' in group")
                    break

    return geom


# ---------------------------------------------------------------------------
# General checks
# ---------------------------------------------------------------------------

_COLLAPSED_EPSILON = 1.0  # pixels


def check_no_collapsed_points(svg: str, diagram: DiagramLike) -> str | None:
    """Fail if any two rendered point circles are within epsilon of each other."""
    geom = extract_geometry(svg)
    positions = list(geom.point_positions.items())
    for i, (name_a, (x1, y1)) in enumerate(positions):
        for name_b, (x2, y2) in positions[i + 1:]:
            if math.hypot(x2 - x1, y2 - y1) < _COLLAPSED_EPSILON:
                return (
                    f"Collapsed points: '{name_a}' and '{name_b}' both rendered "
                    f"at ({x1:.1f}, {y1:.1f})"
                )
    return None


def check_elements_in_bounds(svg: str, diagram: DiagramLike) -> str | None:
    """Fail if any circle or line endpoint is outside the SVG viewBox."""
    geom = extract_geometry(svg)
    if geom.view_box is None:
        return None
    min_x, min_y, width, height = geom.view_box
    max_x, max_y = min_x + width, min_y + height

    def oob(x: float, y: float) -> bool:
        return x < min_x or x > max_x or y < min_y or y > max_y

    for name, (cx, cy) in geom.point_positions.items():
        if oob(cx, cy):
            return f"Point '{name}' rendered outside viewBox at ({cx:.1f}, {cy:.1f})"
    for name, (x1, y1, x2, y2) in geom.line_endpoints.items():
        if oob(x1, y1):
            return f"Line '{name}' start outside viewBox at ({x1:.1f}, {y1:.1f})"
        if oob(x2, y2):
            return f"Line '{name}' end outside viewBox at ({x2:.1f}, {y2:.1f})"
    return None


# ---------------------------------------------------------------------------
# Predicate-driven check registry
# ---------------------------------------------------------------------------

PREDICATE_CHECKS: dict[str, PredicateCheckFactory] = {}


def checks_from_diagram(diagram: DiagramLike) -> list[CheckFn]:
    """Walk diagram.predicates and generate registered predicate checks."""
    result = []
    for pred in diagram.predicates:
        factory = PREDICATE_CHECKS.get(pred.name)
        if factory:
            check = factory(pred, diagram)
            if check is not None:
                result.append(check)
    return result


# ---------------------------------------------------------------------------
# Parallel predicate check
# ---------------------------------------------------------------------------

_PARALLEL_ANGLE_TOLERANCE_DEG = 10.0


def _resolve_line_direction(
    line_name: str,
    diagram: DiagramLike,
    geom: SVGGeometry,
) -> tuple[float, float] | None:
    """Return a unit direction vector (dx, dy) for a named Linelike object.

    Tries two sources:
      1. Direct <line> element in the SVG (geom.line_endpoints).
      2. Constructor args — Line(A, B) → use rendered positions of A and B.
    """
    if line_name in geom.line_endpoints:
        x1, y1, x2, y2 = geom.line_endpoints[line_name]
        dx, dy = x2 - x1, y2 - y1
    else:
        # Resolve via constructor
        for obj in diagram.objects:
            if obj.name == line_name and obj.constructor and len(obj.constructor.args) >= 2:
                p1, p2 = obj.constructor.args[0], obj.constructor.args[1]
                if p1 in geom.point_positions and p2 in geom.point_positions:
                    x1, y1 = geom.point_positions[p1]
                    x2, y2 = geom.point_positions[p2]
                    dx, dy = x2 - x1, y2 - y1
                    break
        else:
            return None

    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    return dx / length, dy / length


def _parallel_factory(pred, diagram: DiagramLike) -> CheckFn | None:
    """Generate a check verifying two Linelike objects are parallel."""
    if len(pred.args) < 2:
        return None
    name1, name2 = str(pred.args[0]), str(pred.args[1])

    def check(svg: str, _diagram: DiagramLike) -> str | None:
        geom = extract_geometry(svg)
        d1 = _resolve_line_direction(name1, diagram, geom)
        d2 = _resolve_line_direction(name2, diagram, geom)
        if d1 is None or d2 is None:
            return None  # can't resolve geometry, skip
        # |cross product| = |sin(angle between lines|
        cross = abs(d1[0] * d2[1] - d1[1] * d2[0])
        angle_deg = math.degrees(math.asin(min(cross, 1.0)))
        if angle_deg > _PARALLEL_ANGLE_TOLERANCE_DEG:
            return (
                f"Parallel({name1}, {name2}): lines are {angle_deg:.1f}° apart "
                f"(tolerance {_PARALLEL_ANGLE_TOLERANCE_DEG}°)"
            )
        return None

    return check


PREDICATE_CHECKS["Parallel"] = _parallel_factory


# ---------------------------------------------------------------------------
# Perpendicular predicate check
# ---------------------------------------------------------------------------

def _perpendicular_factory(pred, diagram: DiagramLike) -> CheckFn | None:
    """Generate a check verifying two Linelike objects are perpendicular."""
    if len(pred.args) < 2:
        return None
    name1, name2 = str(pred.args[0]), str(pred.args[1])

    def check(svg: str, _diagram: DiagramLike) -> str | None:
        geom = extract_geometry(svg)
        d1 = _resolve_line_direction(name1, diagram, geom)
        d2 = _resolve_line_direction(name2, diagram, geom)
        if d1 is None or d2 is None:
            return None  # can't resolve geometry, skip
        # cross product magnitude = |sin(angle between lines)|; for 90° this should be ~1
        cross = abs(d1[0] * d2[1] - d1[1] * d2[0])
        angle_deg = math.degrees(math.asin(min(cross, 1.0)))  # angle from parallel, in [0°, 90°]
        angle_from_90_deg = abs(90.0 - angle_deg)
        if angle_from_90_deg > _PARALLEL_ANGLE_TOLERANCE_DEG:
            return (
                f"Perpendicular({name1}, {name2}): lines deviate {angle_from_90_deg:.1f}° "
                f"from perpendicular (tolerance {_PARALLEL_ANGLE_TOLERANCE_DEG}°)"
            )
        return None

    return check


PREDICATE_CHECKS["Perpendicular"] = _perpendicular_factory


# ---------------------------------------------------------------------------
# Collinear / NonCollinear predicate checks
# ---------------------------------------------------------------------------

_COLLINEAR_ANGLE_TOLERANCE_DEG = 10.0
_NONCOLLINEAR_MIN_ANGLE_DEG = 5.0


def _three_point_cross(
    p1: str, p2: str, p3: str, geom: SVGGeometry
) -> tuple[float, float] | None:
    """Return (cross_product, max_edge_length) for points p1, p2, p3, or None if any missing."""
    pos = geom.point_positions
    if p1 not in pos or p2 not in pos or p3 not in pos:
        return None
    ax, ay = pos[p1]
    bx, by = pos[p2]
    cx, cy = pos[p3]
    # Vectors from A
    abx, aby = bx - ax, by - ay
    acx, acy = cx - ax, cy - ay
    cross = abx * acy - aby * acx  # signed cross product
    max_edge = max(math.hypot(abx, aby), math.hypot(acx, acy), math.hypot(cx - bx, cy - by))
    return abs(cross), max_edge


def _collinear_factory(pred, _diagram: DiagramLike) -> CheckFn | None:
    """Generate a check verifying three points are collinear."""
    if len(pred.args) < 3:
        return None
    p1, p2, p3 = str(pred.args[0]), str(pred.args[1]), str(pred.args[2])

    def check(svg: str, _diagram: DiagramLike) -> str | None:
        geom = extract_geometry(svg)
        result = _three_point_cross(p1, p2, p3, geom)
        if result is None:
            return None  # can't resolve, skip
        cross_mag, max_edge = result
        if max_edge < 1e-6:
            return None  # degenerate triangle, skip
        # cross_mag / max_edge ≈ sin(angle of deviation from collinearity)
        angle_deg = math.degrees(math.asin(min(cross_mag / max_edge, 1.0)))
        if angle_deg > _COLLINEAR_ANGLE_TOLERANCE_DEG:
            return (
                f"Collinear({p1}, {p2}, {p3}): points deviate {angle_deg:.1f}° "
                f"from collinear (tolerance {_COLLINEAR_ANGLE_TOLERANCE_DEG}°)"
            )
        return None

    return check


PREDICATE_CHECKS["Collinear"] = _collinear_factory


def _noncollinear_factory(pred, _diagram: DiagramLike) -> CheckFn | None:
    """Generate a check verifying three points are NOT collinear."""
    if len(pred.args) < 3:
        return None
    p1, p2, p3 = str(pred.args[0]), str(pred.args[1]), str(pred.args[2])

    def check(svg: str, _diagram: DiagramLike) -> str | None:
        geom = extract_geometry(svg)
        result = _three_point_cross(p1, p2, p3, geom)
        if result is None:
            return None  # can't resolve, skip
        cross_mag, max_edge = result
        if max_edge < 1e-6:
            return None  # degenerate, skip
        angle_deg = math.degrees(math.asin(min(cross_mag / max_edge, 1.0)))
        if angle_deg < _NONCOLLINEAR_MIN_ANGLE_DEG:
            return (
                f"NonCollinear({p1}, {p2}, {p3}): points are nearly collinear "
                f"(deviation only {angle_deg:.1f}°, minimum {_NONCOLLINEAR_MIN_ANGLE_DEG}°)"
            )
        return None

    return check


PREDICATE_CHECKS["NonCollinear"] = _noncollinear_factory


# ---------------------------------------------------------------------------
# EqualLength predicate check
# ---------------------------------------------------------------------------

_EQUAL_LENGTH_RELATIVE_TOLERANCE = 0.15


def _resolve_line_length(
    line_name: str,
    diagram: DiagramLike,
    geom: SVGGeometry,
) -> float | None:
    """Return the rendered pixel length of a named Linelike object.

    Tries two sources:
      1. Direct <line> element in the SVG (geom.line_endpoints).
      2. Constructor args — Segment(A, B) → use rendered positions of A and B.
    """
    if line_name in geom.line_endpoints:
        x1, y1, x2, y2 = geom.line_endpoints[line_name]
        return math.hypot(x2 - x1, y2 - y1)
    for obj in diagram.objects:
        if obj.name == line_name and obj.constructor and len(obj.constructor.args) >= 2:
            p1, p2 = obj.constructor.args[0], obj.constructor.args[1]
            if p1 in geom.point_positions and p2 in geom.point_positions:
                x1, y1 = geom.point_positions[p1]
                x2, y2 = geom.point_positions[p2]
                return math.hypot(x2 - x1, y2 - y1)
    return None


def _equal_length_factory(pred, diagram: DiagramLike) -> CheckFn | None:
    """Generate a check verifying two Linelike objects have equal rendered length."""
    if len(pred.args) < 2:
        return None
    name1, name2 = str(pred.args[0]), str(pred.args[1])

    def check(svg: str, _diagram: DiagramLike) -> str | None:
        geom = extract_geometry(svg)
        len1 = _resolve_line_length(name1, diagram, geom)
        len2 = _resolve_line_length(name2, diagram, geom)
        if len1 is None or len2 is None:
            return None  # can't resolve, skip
        if len1 < 1e-6 or len2 < 1e-6:
            return None  # degenerate segment, skip
        ratio = abs(len1 - len2) / max(len1, len2)
        if ratio > _EQUAL_LENGTH_RELATIVE_TOLERANCE:
            return (
                f"EqualLength({name1}, {name2}): lengths differ by {ratio * 100:.1f}% "
                f"({len1:.1f}px vs {len2:.1f}px, tolerance {_EQUAL_LENGTH_RELATIVE_TOLERANCE * 100:.0f}%)"
            )
        return None

    return check


PREDICATE_CHECKS["EqualLength"] = _equal_length_factory


# ---------------------------------------------------------------------------
# Horizontal predicate check
# ---------------------------------------------------------------------------

def _horizontal_factory(pred, diagram: DiagramLike) -> CheckFn | None:
    """Generate a check verifying a Linelike object is approximately horizontal."""
    if len(pred.args) < 1:
        return None
    name = str(pred.args[0])

    def check(svg: str, _diagram: DiagramLike) -> str | None:
        geom = extract_geometry(svg)
        direction = _resolve_line_direction(name, diagram, geom)
        if direction is None:
            return None  # can't resolve, skip
        dx, dy = direction
        # Angle from horizontal = atan2(|dy|, |dx|)
        angle_deg = math.degrees(math.atan2(abs(dy), abs(dx)))
        if angle_deg > _PARALLEL_ANGLE_TOLERANCE_DEG:
            return (
                f"Horizontal({name}): line is {angle_deg:.1f}° from horizontal "
                f"(tolerance {_PARALLEL_ANGLE_TOLERANCE_DEG}°)"
            )
        return None

    return check


PREDICATE_CHECKS["Horizontal"] = _horizontal_factory

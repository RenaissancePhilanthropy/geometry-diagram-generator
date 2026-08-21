# geometry_diagrams/pydsl/asserts.py
"""assert_* geometric-invariant predicates for the Python DSL surface.

Each function here is a thin wrapper around an existing `ir.Check` kind:
build the matching `ir.Check` object from the caller's handle ids, force
resolution of any not-yet-materialized point via `Builder._advance_sym()`,
run it through `checks._check_one` (the same dispatcher the JSON/recipe DSL
uses), and raise `GeometricAssertionError` with a message that has every
recognized point id substituted for its resolved `(x.xx, y.yy)` coordinate
string (pydsl ids are opaque auto-generated hidden ids the LLM never wrote,
so a raw id in a failure message is useless to it).

`GeometricAssertionError` is a `ValueError` subclass (defined in
`builder.py`, imported here) so any code that already catches `ValueError`
keeps working unchanged; `retry.py` additionally special-cases it to the
`"geometric_assertion"` failure classification.
"""
from __future__ import annotations

from geometry_diagrams.ir import checks
from geometry_diagrams.ir import ir
from geometry_diagrams.pydsl.builder import Builder, GeometricAssertionError, get_builder
from geometry_diagrams.pydsl.handles import AngleRef, Point, Polygon, Triangle

__all__ = [
    "assert_distinct_points",
    "assert_distinct_objects",
    "assert_not_collinear",
    "assert_collinear",
    "assert_on",
    "assert_not_on",
    "assert_parallel",
    "assert_not_parallel",
    "assert_perpendicular",
    "assert_right_angle",
    "assert_angle_equal",
    "assert_equal_length",
    "assert_distance",
    "assert_ratio_equal",
    "assert_similar_triangles",
    "assert_tangent",
    "assert_opposite_side",
    "assert_same_side",
    "assert_centroid",
    "assert_convex",
    "assert_ccw",
    "assert_min_distance",
    "assert_congruent_triangles",
    "assert_in_canvas",
]


# ---------------------------------------------------------------------------
# Shared dispatch helper
# ---------------------------------------------------------------------------

def _run_assertion(builder: Builder, check: "ir.CheckBase", point_ids: list[str]) -> None:
    """Do the real work for every assert_* mirror.

    Order matters: force resolution of any deferred point first (the same
    path Point.x/Point.y already use), then dispatch through checks.py's
    shared `_check_one`, passing `checks.DEFAULT_TOL` (a concrete float) as
    its `default_tol` positional argument — never the caller's own
    (possibly-None) `tol` override, which lives on the check object's own
    `tol` field instead. On failure, substitute every point id in
    `point_ids` with its resolved "(x.xx, y.yy)" coordinate string before
    raising, since every pydsl id is an opaque hidden id the LLM never
    wrote.
    """
    builder._advance_sym()
    result = checks._check_one(check, builder._sym, checks.DEFAULT_TOL)
    if result.passed:
        return
    msg = result.message
    # Longest id first: hidden ids share a common prefix and an incrementing
    # numeric suffix (e.g. "__pydsl_pt_1" vs "__pydsl_pt_10"), so replacing
    # the shorter one first would corrupt the longer one's occurrences too.
    for pid in sorted(set(point_ids), key=len, reverse=True):
        obj = builder._sym.get(pid)
        if obj is None:
            continue
        try:
            coord = f"({float(obj.x):.2f}, {float(obj.y):.2f})"
        except Exception:
            continue
        # Messages sometimes quote ids via repr() (e.g. "Points 'pid' and...")
        # and sometimes interpolate them bare (e.g. "Angle pid-pid-pid is...")
        # — replace both forms so the substitution is complete either way.
        msg = msg.replace(repr(pid), coord)
        msg = msg.replace(pid, coord)
    raise GeometricAssertionError(msg)


# ---------------------------------------------------------------------------
# Mirror predicates
# ---------------------------------------------------------------------------

def assert_distinct_points(p: Point, q: Point, *, tol: float | None = None) -> None:
    """Assert that points p and q are not coincident."""
    builder = get_builder()
    check = ir.DistinctPoints(a=p.id, b=q.id, tol=tol)
    _run_assertion(builder, check, [p.id, q.id])


def assert_distinct_objects(obj1, obj2, *, tol: float | None = None) -> None:
    """Assert that two geometric objects (points, lines, circles, ...) are not geometrically identical."""
    builder = get_builder()
    check = ir.DistinctObjects(a=obj1.id, b=obj2.id, tol=tol)
    _run_assertion(builder, check, [obj1.id, obj2.id])


def assert_not_collinear(a: Point, b: Point, c: Point, *, tol: float | None = None) -> None:
    """Assert that points a, b, c are not collinear."""
    builder = get_builder()
    check = ir.NonCollinear(a=a.id, b=b.id, c=c.id, tol=tol)
    _run_assertion(builder, check, [a.id, b.id, c.id])


def assert_collinear(*points: Point, tol: float | None = None) -> None:
    """Assert that three or more points are collinear."""
    builder = get_builder()
    ids = [p.id for p in points]
    check = ir.Collinear(points=ids, tol=tol)
    _run_assertion(builder, check, ids)


def assert_on(p: Point, obj, *, tol: float | None = None) -> None:
    """Assert that point p lies on obj (a line/segment/ray/circle/ellipse)."""
    builder = get_builder()
    check = ir.Contains(p=p.id, obj=obj.id, tol=tol)
    _run_assertion(builder, check, [p.id])


def assert_not_on(p: Point, obj, *, tol: float | None = None) -> None:
    """Assert that point p does not lie on obj (a line/segment/ray/circle/ellipse)."""
    builder = get_builder()
    check = ir.NotContains(p=p.id, obj=obj.id, tol=tol)
    _run_assertion(builder, check, [p.id])


def assert_parallel(l1, l2, *, tol: float | None = None) -> None:
    """Assert that two linear objects (Line/Segment/Ray) are parallel."""
    builder = get_builder()
    check = ir.Parallel(l1=l1.id, l2=l2.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_not_parallel(l1, l2, *, tol: float | None = None) -> None:
    """Assert that two linear objects (Line/Segment/Ray) are not parallel."""
    builder = get_builder()
    check = ir.NotParallel(l1=l1.id, l2=l2.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_perpendicular(l1, l2, *, tol: float | None = None) -> None:
    """Assert that two linear objects (Line/Segment/Ray) are perpendicular."""
    builder = get_builder()
    check = ir.Perpendicular(l1=l1.id, l2=l2.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_right_angle(ref: AngleRef, *, tol: float | None = None) -> None:
    """Assert that the angle a-o-b (from an AngleRef, e.g. t.angle_at(v)) is a right angle.

    Known limitation: checks.py's alternative-angle "try: ..." hint search
    (used to suggest a matching right angle elsewhere in the diagram when
    this one fails) filters out every "__"-prefixed point id, and every
    pydsl point id is hidden-prefixed — so that hint never appears for a
    pydsl-originated failure. This is documented, not a bug to fix here.
    """
    builder = get_builder()
    angle = ir.AnglePoints(a=ref.a.id, o=ref.o.id, b=ref.b.id)
    check = ir.RightAngle(angle=angle, tol=tol)
    _run_assertion(builder, check, [ref.a.id, ref.o.id, ref.b.id])


def assert_angle_equal(ref1: AngleRef, ref2: AngleRef, *, tol: float | None = None) -> None:
    """Assert that two angles (from AngleRefs, e.g. t.angle_at(v)) are equal.

    Known limitation: same as assert_right_angle's — checks.py's
    alternative-angle "try: ..." hints are always empty for pydsl-originated
    checks, since every pydsl point id is hidden-prefixed and the hint
    search filters those out. Documented, not a bug.
    """
    builder = get_builder()
    a1 = ir.AnglePoints(a=ref1.a.id, o=ref1.o.id, b=ref1.b.id)
    a2 = ir.AnglePoints(a=ref2.a.id, o=ref2.o.id, b=ref2.b.id)
    check = ir.AngleEqual(a1=a1, a2=a2, tol=tol)
    _run_assertion(
        builder, check,
        [ref1.a.id, ref1.o.id, ref1.b.id, ref2.a.id, ref2.o.id, ref2.b.id],
    )


def assert_equal_length(*segs, tol: float | None = None) -> None:
    """Assert that two or more segments all have equal length."""
    builder = get_builder()
    ids = [s.id for s in segs]
    check = ir.EqualLength(segs=ids, tol=tol)
    _run_assertion(builder, check, [])


def assert_distance(seg, expected: float, *, tol: float | None = None) -> None:
    """Assert that a segment has a specific expected length."""
    builder = get_builder()
    check = ir.DistanceEquals(seg=seg.id, expected=expected, tol=tol)
    _run_assertion(builder, check, [])


def assert_ratio_equal(s1, s2, s3, s4, *, tol: float | None = None) -> None:
    """Assert the ratio equality |s1|/|s2| == |s3|/|s4| between four segments."""
    builder = get_builder()
    check = ir.RatioEqual(s1=s1.id, s2=s2.id, s3=s3.id, s4=s4.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_similar_triangles(t1: Triangle, t2: Triangle, *, tol: float | None = None) -> None:
    """Assert that two triangles are similar (matching sorted angle sets)."""
    builder = get_builder()
    check = ir.SimilarTriangles(t1=t1.id, t2=t2.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_tangent(line, circle, *, tol: float | None = None) -> None:
    """Assert that a line/segment/ray is tangent to a circle."""
    builder = get_builder()
    check = ir.Tangent(line=line.id, circle=circle.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_opposite_side(
    p: Point, q: Point, line_a: Point, line_b: Point, *, tol: float | None = None,
) -> None:
    """Assert that points p and q are on opposite sides of the line through line_a and line_b."""
    builder = get_builder()
    check = ir.OppositeSide(p=p.id, q=q.id, line_a=line_a.id, line_b=line_b.id, tol=tol)
    _run_assertion(builder, check, [p.id, q.id, line_a.id, line_b.id])


def assert_same_side(
    p: Point, q: Point, line_a: Point, line_b: Point, *, tol: float | None = None,
) -> None:
    """Assert that points p and q are on the same side of the line through line_a and line_b."""
    builder = get_builder()
    check = ir.SameSide(p=p.id, q=q.id, line_a=line_a.id, line_b=line_b.id, tol=tol)
    _run_assertion(builder, check, [p.id, q.id, line_a.id, line_b.id])


def assert_centroid(g: Point, a: Point, b: Point, c: Point, *, tol: float | None = None) -> None:
    """Assert that point g is the centroid of triangle a-b-c."""
    builder = get_builder()
    check = ir.Centroid(g=g.id, a=a.id, b=b.id, c=c.id, tol=tol)
    _run_assertion(builder, check, [g.id, a.id, b.id, c.id])


# ---------------------------------------------------------------------------
# New predicates (ticket 04): convex / ccw / min-distance / congruent triangles
# ---------------------------------------------------------------------------

def assert_convex(polygon: Polygon, *, tol: float | None = None) -> None:
    """Assert that a polygon's (or triangle's) vertices form a convex shape."""
    builder = get_builder()
    check = ir.Convex(polygon=polygon.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_ccw(polygon: Polygon, *, tol: float | None = None) -> None:
    """Assert that a polygon's (or triangle's) vertices are wound counter-clockwise."""
    builder = get_builder()
    check = ir.CCW(polygon=polygon.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_min_distance(p: Point, q: Point, min_dist: float, *, tol: float | None = None) -> None:
    """Assert that points p and q are at least min_dist apart."""
    builder = get_builder()
    check = ir.MinDistance(a=p.id, b=q.id, min_dist=min_dist, tol=tol)
    _run_assertion(builder, check, [p.id, q.id])


def assert_congruent_triangles(t1: Triangle, t2: Triangle, *, tol: float | None = None) -> None:
    """Assert that two triangles are congruent (SSS: matching sorted side
    lengths, no required vertex correspondence)."""
    builder = get_builder()
    check = ir.CongruentTriangles(t1=t1.id, t2=t2.id, tol=tol)
    _run_assertion(builder, check, [])


def assert_in_canvas(p: Point) -> None:
    """Assert that point p lies within the diagram's canvas bounds.

    Not backed by an ir.Check kind (see the pydsl-asserts spec's
    Implementation Decisions) — this reads `builder._canvas` directly,
    falling back to `ir.Canvas()`'s defaults ([-5, 5] x [-5, 5]) if
    `canvas()` hasn't been called yet.

    Ordering hazard, documented not hidden: `canvas()` can be called
    anywhere in a script, and this function reflects the canvas as
    configured at the point it is called — not whatever the script sets
    later. Call this *after* your script's own `canvas(...)` call if you
    rely on custom bounds; called before it, this validates against
    `ir.Canvas()`'s default bounds instead.
    """
    builder = get_builder()
    builder._advance_sym()
    x, y = p.x, p.y
    canvas = builder._canvas or ir.Canvas()
    if not (canvas.xmin <= x <= canvas.xmax and canvas.ymin <= y <= canvas.ymax):
        raise GeometricAssertionError(
            f"Point ({x:.2f}, {y:.2f}) is outside canvas bounds "
            f"[{canvas.xmin:.2f}, {canvas.xmax:.2f}] x [{canvas.ymin:.2f}, {canvas.ymax:.2f}]"
        )

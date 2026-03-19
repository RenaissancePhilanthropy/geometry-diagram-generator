"""
Instantiate DiagramIR for the eval scenarios to confirm expressiveness.
Run: python -m ir.test_scenarios
"""
from __future__ import annotations
import math
import sys
from ir.ir import (
    DiagramIR,
    PointFixed, PointFree, PointOn, PointMidpoint, PointRotate,
    PointTriangleCenter, PointIntersection,
    Segment, Ray,
    LineThrough, LineParallelThrough, LinePerpendicularThrough,
    LineAngleBisector, LineTangent,
    CircleCenterPoint, CircleCenterRadius, CircleThrough3,
    Triangle, Polygon, PolygonExterior,
    PointOnParam, PointOnRandom,
    PickOnObject, PickIndex, PickClosestTo,
    Collinear, EqualLength, RightAngle, Tangent,
    NonCollinear, Contains, Parallel, Perpendicular,
    AngleEqual, SimilarTriangles,
    AnglePoints,
    Draw, DrawPoints, Fill, MarkAngles, MarkRightAngles, MarkSegments,
    LabelPoint, LabelAngle, LabelSegment,
)

results: list[tuple[str, str]] = []
SCENARIOS: list[tuple[str, DiagramIR]] = []


def _test(scenario_id: str, ir: DiagramIR) -> None:
    json_str = ir.model_dump_json()
    DiagramIR.model_validate_json(json_str)
    results.append((scenario_id, "OK"))
    SCENARIOS.append((scenario_id, ir))


# ---------------------------------------------------------------------------
# Tier 1 — Basic
# ---------------------------------------------------------------------------

# 1. right-triangle
_test("right-triangle", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=2),
        PointFixed(id="B", x=0, y=0),
        PointFixed(id="C", x=3, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
    ],
    checks=[
        RightAngle(angle=AnglePoints(a="A", o="B", b="C")),
    ],
    render=[
        Draw(obj="T"),
        MarkRightAngles(angles=[AnglePoints(a="A", o="B", b="C")]),
        DrawPoints(points=["A", "B", "C"]),
        LabelPoint(p="A", pos="left"),
        LabelPoint(p="B", pos="below"),
        LabelPoint(p="C", pos="right"),
    ],
))

# 2. midpoint
_test("midpoint", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        Segment(id="s_AB", a="A", b="B"),
        PointMidpoint(id="M", p="A", q="B"),
    ],
    render=[
        Draw(obj="s_AB"),
        DrawPoints(points=["A", "B", "M"]),
        LabelPoint(p="A", pos="below"),
        LabelPoint(p="B", pos="below"),
        LabelPoint(p="M", pos="above"),
    ],
))

# 3. equilateral-triangle — A=(0,0), B=(2,0), C=(1, √3)
_test("equilateral-triangle", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=2, y=0),
        PointFixed(id="C", x=1, y=round(math.sqrt(3), 4)),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="s_AB", a="A", b="B"),
        Segment(id="s_BC", a="B", b="C"),
        Segment(id="s_CA", a="C", b="A"),
    ],
    checks=[
        EqualLength(segs=["s_AB", "s_BC", "s_CA"]),
    ],
    render=[
        Draw(obj="T"),
        MarkSegments(segs=["s_AB", "s_BC", "s_CA"]),
        DrawPoints(points=["A", "B", "C"]),
        LabelPoint(p="A", pos="left"),
        LabelPoint(p="B", pos="right"),
        LabelPoint(p="C", pos="above"),
    ],
))

# 4. isosceles-triangle — AB = AC; A=(2,3), B=(0,0), C=(4,0)
_test("isosceles-triangle", DiagramIR(
    define=[
        PointFixed(id="A", x=2, y=3),
        PointFixed(id="B", x=0, y=0),
        PointFixed(id="C", x=4, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="s_AB", a="A", b="B"),
        Segment(id="s_AC", a="A", b="C"),
    ],
    checks=[
        EqualLength(segs=["s_AB", "s_AC"]),
    ],
    render=[
        Draw(obj="T"),
        MarkSegments(segs=["s_AB", "s_AC"]),
        DrawPoints(points=["A", "B", "C"]),
        LabelPoint(p="A", pos="above"),
        LabelPoint(p="B", pos="left"),
        LabelPoint(p="C", pos="right"),
    ],
))

# 5. square ABCD
_test("square", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=3, y=0),
        PointFixed(id="C", x=3, y=3),
        PointFixed(id="D", x=0, y=3),
        Polygon(id="sq", points=["A", "B", "C", "D"]),
        Segment(id="s_AB", a="A", b="B"),
        Segment(id="s_BC", a="B", b="C"),
        Segment(id="s_CD", a="C", b="D"),
        Segment(id="s_DA", a="D", b="A"),
    ],
    checks=[
        RightAngle(angle=AnglePoints(a="D", o="A", b="B")),
        RightAngle(angle=AnglePoints(a="A", o="B", b="C")),
        RightAngle(angle=AnglePoints(a="B", o="C", b="D")),
        RightAngle(angle=AnglePoints(a="C", o="D", b="A")),
        EqualLength(segs=["s_AB", "s_BC", "s_CD", "s_DA"]),
    ],
    render=[
        Draw(obj="sq"),
        MarkRightAngles(angles=[
            AnglePoints(a="D", o="A", b="B"),
            AnglePoints(a="A", o="B", b="C"),
            AnglePoints(a="B", o="C", b="D"),
            AnglePoints(a="C", o="D", b="A"),
        ]),
        MarkSegments(segs=["s_AB", "s_BC", "s_CD", "s_DA"]),
        DrawPoints(points=["A", "B", "C", "D"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="D"),
    ],
))

# 6. perpendicular-bisector
_test("perpendicular-bisector", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        Segment(id="s_AB", a="A", b="B"),
        LineThrough(id="l_AB", p="A", q="B"),
        PointMidpoint(id="M", p="A", q="B"),
        LinePerpendicularThrough(id="perp", through="M", to_line="l_AB"),
    ],
    render=[
        Draw(obj="s_AB"),
        Draw(obj="perp"),
        DrawPoints(points=["A", "B", "M"]),
        LabelPoint(p="A", pos="below"),
        LabelPoint(p="B", pos="below"),
        LabelPoint(p="M", pos="above"),
    ],
))

# ---------------------------------------------------------------------------
# Tier 2 — Intermediate
# ---------------------------------------------------------------------------

# 7. circumscribed-circle
_test("circumscribed-circle", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=1, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
        PointTriangleCenter(id="O", tri="T", which="circumcenter"),
        CircleCenterPoint(id="circ", center="O", through="A"),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="circ"),
        DrawPoints(points=["A", "B", "C", "O"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="O"),
    ],
))

# 8. inscribed-circle — incenter + incircle via perpendicular foot
_test("inscribed-circle", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=1.5, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
        LineThrough(id="l_AB", p="A", q="B"),
        PointTriangleCenter(id="I", tri="T", which="incenter"),
        LinePerpendicularThrough(id="perp_I", through="I", to_line="l_AB"),
        PointIntersection(id="T_foot", obj1="perp_I", obj2="l_AB"),
        CircleCenterPoint(id="incircle", center="I", through="T_foot"),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="incircle"),
        DrawPoints(points=["A", "B", "C", "I"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="I"),
    ],
))

# 9. angle-bisector
_test("angle-bisector", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=3),
        PointFixed(id="B", x=-2, y=0),
        PointFixed(id="C", x=2, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
        LineThrough(id="l_BC", p="B", q="C"),
        LineAngleBisector(id="bisect", a="B", vertex="A", b="C"),
        Segment(id="s_AD_line", a="A", b="C"),  # placeholder; D defined via intersection
        PointIntersection(id="D", obj1="bisect", obj2="l_BC"),
        Segment(id="s_AD", a="A", b="D"),
    ],
    checks=[
        Contains(p="D", obj="l_BC"),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="s_AD"),
        DrawPoints(points=["A", "B", "C", "D"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="D"),
    ],
))

# 10. altitude — foot H of perpendicular from C to AB
_test("altitude", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=1, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
        LineThrough(id="l_AB", p="A", q="B"),
        LinePerpendicularThrough(id="alt", through="C", to_line="l_AB"),
        PointIntersection(id="H", obj1="alt", obj2="l_AB"),
        Segment(id="s_CH", a="C", b="H"),
    ],
    checks=[
        RightAngle(angle=AnglePoints(a="C", o="H", b="A")),
        Contains(p="H", obj="l_AB"),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="s_CH"),
        MarkRightAngles(angles=[AnglePoints(a="C", o="H", b="A")]),
        DrawPoints(points=["A", "B", "C", "H"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="H"),
    ],
))

# 11. median
_test("median", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=3),
        PointFixed(id="B", x=-2, y=0),
        PointFixed(id="C", x=2, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
        PointMidpoint(id="M", p="B", q="C"),
        Segment(id="s_AM", a="A", b="M"),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="s_AM"),
        DrawPoints(points=["A", "B", "C", "M"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="M"),
    ],
))

# 12. transversal-parallel
_test("transversal-parallel", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=2),
        PointFixed(id="B", x=4, y=2),
        PointFixed(id="C", x=0, y=0),
        PointFixed(id="D", x=4, y=0),
        LineThrough(id="l1", p="A", q="B"),
        LineThrough(id="l2", p="C", q="D"),
        PointFixed(id="P", x=-1, y=3),   # transversal defined by two points
        PointFixed(id="Q", x=5, y=-1),
        LineThrough(id="l_trans", p="P", q="Q"),
        PointIntersection(id="E", obj1="l_trans", obj2="l1"),
        PointIntersection(id="F", obj1="l_trans", obj2="l2"),
    ],
    checks=[
        Parallel(l1="l1", l2="l2"),
    ],
    render=[
        Draw(obj="l1"),
        Draw(obj="l2"),
        Draw(obj="l_trans"),
        DrawPoints(points=["A", "B", "C", "D"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="D"),
    ],
))

# 13. exterior-angle — D beyond C on ray from B through C
_test("exterior-angle", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=2),
        PointFixed(id="B", x=-1, y=0),
        PointFixed(id="C", x=2, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
        Ray(id="ray_BC", a="B", b="C"),
        PointOn(id="D", on="ray_BC", how=PointOnParam(t=1.5)),
        Segment(id="s_CD", a="C", b="D"),
    ],
    checks=[
        Collinear(points=["B", "C", "D"]),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="s_CD"),
        DrawPoints(points=["A", "B", "C", "D"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="D"),
    ],
))

# ---------------------------------------------------------------------------
# Tier 3 — Advanced
# ---------------------------------------------------------------------------

# 14. triangle-proportionality — D on AB, E on AC, DE ∥ BC
_test("triangle-proportionality", DiagramIR(
    define=[
        PointFixed(id="A", x=2, y=4),
        PointFixed(id="B", x=0, y=0),
        PointFixed(id="C", x=4, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="s_AB", a="A", b="B"),
        Segment(id="s_AC", a="A", b="C"),
        LineThrough(id="l_BC", p="B", q="C"),
        PointOn(id="D", on="s_AB", how=PointOnParam(t=0.5)),
        PointOn(id="E", on="s_AC", how=PointOnParam(t=0.5)),
        LineThrough(id="l_DE", p="D", q="E"),
        Segment(id="s_DE", a="D", b="E"),
    ],
    checks=[
        Parallel(l1="l_DE", l2="l_BC"),
        Contains(p="D", obj="s_AB"),
        Contains(p="E", obj="s_AC"),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="s_DE"),
        DrawPoints(points=["A", "B", "C", "D", "E"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"),
        LabelPoint(p="D"), LabelPoint(p="E"),
    ],
))

# 15. similar-triangles — two separate triangles, all PointFixed
_test("similar-triangles", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=2, y=0),
        PointFixed(id="C", x=1, y=2),
        Triangle(id="T1", a="A", b="B", c="C"),
        PointFixed(id="D", x=3, y=0),
        PointFixed(id="E", x=6, y=0),
        PointFixed(id="F", x=4.5, y=3),
        Triangle(id="T2", a="D", b="E", c="F"),
    ],
    checks=[
        SimilarTriangles(t1="T1", t2="T2", correspond=[("A","D"),("B","E"),("C","F")]),
    ],
    render=[
        Draw(obj="T1"),
        Draw(obj="T2"),
        DrawPoints(points=["A","B","C","D","E","F"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"),
        LabelPoint(p="D"), LabelPoint(p="E"), LabelPoint(p="F"),
    ],
))

# 16. tangent-to-circle — circle O, external point P, tangent at T
_test("tangent-to-circle", DiagramIR(
    define=[
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="circ", center="O", radius=1.5),
        PointFixed(id="P", x=4, y=0),
        LineTangent(id="tang", point="P", circle="circ", pick=PickIndex(k=0)),
        PointIntersection(id="T", obj1="tang", obj2="circ", pick=PickClosestTo(p="P")),
        Segment(id="s_OT", a="O", b="T"),
        Segment(id="s_PT", a="P", b="T"),
    ],
    checks=[
        Tangent(line="tang", circle="circ"),
        RightAngle(angle=AnglePoints(a="O", o="T", b="P")),
    ],
    render=[
        Draw(obj="circ"),
        Draw(obj="s_OT"),
        Draw(obj="s_PT"),
        DrawPoints(points=["O","P","T"]),
        LabelPoint(p="O"), LabelPoint(p="P"), LabelPoint(p="T"),
    ],
))

# 17. pythagorean-theorem — right triangle at C; squares on each side via PolygonExterior
_test("pythagorean-theorem", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=3),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=0, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
        PolygonExterior(id="sq_AB", a="A", b="B", ref="C", sides=4),
        PolygonExterior(id="sq_AC", a="A", b="C", ref="B", sides=4),
        PolygonExterior(id="sq_BC", a="B", b="C", ref="A", sides=4),
    ],
    checks=[
        RightAngle(angle=AnglePoints(a="A", o="C", b="B")),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="sq_AB"),
        Draw(obj="sq_AC"),
        Draw(obj="sq_BC"),
        Fill(obj="sq_AB", opacity=0.15),
        Fill(obj="sq_AC", opacity=0.15),
        Fill(obj="sq_BC", opacity=0.15),
        MarkRightAngles(angles=[AnglePoints(a="A", o="C", b="B")]),
        DrawPoints(points=["A","B","C"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"),
    ],
))

# 18. cyclic-quadrilateral — four points on circle, polygon inscribed
_test("cyclic-quadrilateral", DiagramIR(
    define=[
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="circ", center="O", radius=3),
        PointOn(id="A", on="circ", how=PointOnParam(t=0.5)),
        PointOn(id="B", on="circ", how=PointOnParam(t=1.5)),
        PointOn(id="C", on="circ", how=PointOnParam(t=2.8)),
        PointOn(id="D", on="circ", how=PointOnParam(t=4.5)),
        Polygon(id="quad", points=["A","B","C","D"]),
    ],
    checks=[
        Contains(p="A", obj="circ"),
        Contains(p="B", obj="circ"),
        Contains(p="C", obj="circ"),
        Contains(p="D", obj="circ"),
    ],
    render=[
        Draw(obj="circ"),
        Draw(obj="quad"),
        DrawPoints(points=["A","B","C","D","O"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"),
        LabelPoint(p="D"), LabelPoint(p="O"),
    ],
))

# 19. euler-line — circumcenter O, centroid G, orthocenter H
_test("euler-line", DiagramIR(
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=6, y=0),
        PointFixed(id="C", x=2, y=4),
        Triangle(id="T", a="A", b="B", c="C"),
        PointTriangleCenter(id="O", tri="T", which="circumcenter"),
        PointTriangleCenter(id="G", tri="T", which="centroid"),
        PointTriangleCenter(id="H", tri="T", which="orthocenter"),
        LineThrough(id="euler", p="O", q="G"),
    ],
    checks=[
        Collinear(points=["O","G","H"]),
    ],
    render=[
        Draw(obj="T"),
        Draw(obj="euler"),
        DrawPoints(points=["A","B","C","O","G","H"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"),
        LabelPoint(p="O"), LabelPoint(p="G"), LabelPoint(p="H"),
    ],
))

# 20. transversal-angles — two parallel lines, transversal, label angle arcs
_test("transversal-angles", DiagramIR(
    define=[
        PointFixed(id="A", x=-2, y=2),
        PointFixed(id="B", x=4, y=2),
        PointFixed(id="C", x=-2, y=0),
        PointFixed(id="D", x=4, y=0),
        LineThrough(id="l1", p="A", q="B"),
        LineThrough(id="l2", p="C", q="D"),
        PointFixed(id="P", x=0, y=4),
        PointFixed(id="Q", x=2, y=-2),
        LineThrough(id="l_trans", p="P", q="Q"),
        PointIntersection(id="E", obj1="l_trans", obj2="l1"),
        PointIntersection(id="F", obj1="l_trans", obj2="l2"),
    ],
    checks=[
        Parallel(l1="l1", l2="l2"),
    ],
    render=[
        Draw(obj="l1"),
        Draw(obj="l2"),
        Draw(obj="l_trans"),
        # Four angles at E
        MarkAngles(angles=[AnglePoints(a="A", o="E", b="P")], group="alpha"),
        MarkAngles(angles=[AnglePoints(a="P", o="E", b="B")], group="beta"),
        LabelAngle(angle=AnglePoints(a="A", o="E", b="P"), text=r"\alpha"),
        LabelAngle(angle=AnglePoints(a="P", o="E", b="B"), text=r"\beta"),
        # Four angles at F
        MarkAngles(angles=[AnglePoints(a="C", o="F", b="Q")], group="alpha"),
        MarkAngles(angles=[AnglePoints(a="Q", o="F", b="D")], group="beta"),
        LabelAngle(angle=AnglePoints(a="C", o="F", b="Q"), text=r"\alpha"),
        LabelAngle(angle=AnglePoints(a="Q", o="F", b="D"), text=r"\beta"),
        DrawPoints(points=["A","B","C","D","E","F"]),
        LabelPoint(p="A"), LabelPoint(p="B"), LabelPoint(p="C"), LabelPoint(p="D"),
    ],
))

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

passed = [s for s, r in results if r == "OK"]
failed = [s for s, r in results if r != "OK"]

for scenario_id, result in results:
    status = "✓" if result == "OK" else "✗"
    print(f"  {status} {scenario_id}: {result}")

print()
print(f"Passed: {len(passed)}/{len(results)}")
if failed:
    print(f"Failed: {failed}")
    sys.exit(1)

"""Structural eval checks that read the DRAWING (what the authored DiagramIR draws), not
just point coordinates: ``dashed``, ``shaded``, ``concentric_circles``, ``line_name``,
``mark_group``, ``polygon_drawn``, ``object_exists``, ``length_ratios`` and ``object_count``.

Eval-only: they are registered in the check-type registry (evals/check_types.py) so a
scenario file can use them; nothing here is shown to a generating model.

``read_drawing`` turns an authored diagram into a ``DrawingView``: the compiled point table,
the drawn straight objects (each with its dashed flag), circles, filled polygons, the
tick/parallel/angle marks and the free and segment labels. Every check judges coincidence by
``view.tolerance``, 1% of the figure's extent (the largest distance between two compiled
points), so a figure drawn at any scale is judged the same way.

"Drawn is drawn": the view reads the LOWERED render list (``derived.lower_render`` over the
effective diagram, the list both renderers draw) and dispatches each draw on the type of the
COMPILED object, not on the definition kind, so a construction counts as what it draws:
a triangle, polygon (also a regular polygon or ``polygon_on_edge``) or ``ordered_polygon``
contributes its sides; a segment, ray or line one straight object; an open polyline
(``polyline_open``) a chain of straight objects (an open chain is not a polygon); a circle
(``circle_center_*``, ``circle_through3``, a tangent circle) one circle. Arcs, sectors and
ellipses are never circles, and a sector's radii are straight only when drawn as segments. A
rectangular prism draws as its wireframe edges (hidden ones dashed; a ``unit_cubes`` prism
adds its gridlines) and a block stack as its painted cube edges merged into runs, so on a
solid ``object_count`` counts those edges (use ``solid_count`` and the ``prism_*``/``stack_*``
properties for solids), and a stack never draws a dashed edge. An object defined but not
drawn is not counted.

Names: the point names of a check's arguments are resolved to figure ids by the runner
(``resolve_check_args``, using evals/property_names.py) before an evaluator runs, so an
evaluator reads ids. Called directly with a name that is not an id, ``DrawingView.point``
falls back to the same resolver (label text, primed spellings; no ``variable_ids``).

Every evaluator is ``(args, diagram_ir, tikz_code) -> {"passed", "message"}``; a check with
nothing to test is a skip: ``{"passed": None, "skipped": True, ...}``, never a pass. Each
``_validate_*`` runs when a scenario file loads.
"""
from __future__ import annotations

import functools
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Sequence

import sympy.geometry as spg

from evals.check_types import register_structural_type
from evals.property_names import NameResolutionError, NameResolver

Point = tuple[float, float]

LINE_TOLERANCE = 0.01  # of the figure's extent: how far off a line a point may sit
LENGTH_TOLERANCE = 0.03  # relative: a written length's ratio to the other written lengths
ANGLE_TOLERANCE_DEG = 2.0  # directions of an angle mark's arms
COVER_SAMPLES = 24  # points tried along a span to see it is drawn
MAX_ARCS = 3  # an angle mark has at most this many arcs
LINE_NAME_REACH_FRACTION = 0.15  # how far from its line a printed line name may sit
# Spans are one run when collinear within this many degrees (the upper count bound) ...
RUN_DIRECTION_TOLERANCE_DEG = 1.5
# ... and, for the LOWER bound, only when they lie (all but) exactly on one line, so a
# recreation gets the benefit of the doubt on both sides: an omission leaving pieces between
# the two rules still reaches ``low`` and is not caught (an accepted limit).
OMISSION_MERGE_DEG = 0.25
OMISSION_OFFSET_SCALE = 0.5

OBJECT_KINDS = frozenset({"segment", "ray", "line"})
EXISTENCE_OBJECTS = frozenset({"circle", *OBJECT_KINDS})
MARK_FAMILIES = ("tick", "parallel", "angle")
ANGLE_SIDES = frozenset({"interior", "reflex"})
COUNT_KEYS = ("circle", "straight")
_GROUP_NOUN = {"tick": "tick count", "parallel": "parallel group", "angle": "arc count"}
_TICK_GROUP = re.compile(r"^(?:tick)?(\d+)$")
_ARC_GROUP = re.compile(r"^(?:arc)?(\d+)$")
_PRIMES = str.maketrans({
    0x2032: "'", 0x2033: "''", 0x2034: "'''", 0x2019: "'", 0x2018: "'", 0x02B9: "'", 0x00B4: "'",
})


def _skip(message: str) -> dict:
    return {"passed": None, "skipped": True, "message": message}


def _result(passed: bool, message: str = "") -> dict:
    return {"passed": passed, "message": message}


def _bare(text: str) -> str:
    """A label text without math delimiters and spaces, every prime as ASCII ``'``."""
    return text.replace("$", "").replace(" ", "").translate(_PRIMES)


# ---------------------------------------------------------------------------
# Reading the drawing
# ---------------------------------------------------------------------------

@dataclass
class _Straight:
    """A drawn straight object: the span of line it covers."""
    a: Point
    b: Point
    kind: str  # "segment" | "ray" | "line"
    dashed: bool


@dataclass(frozen=True)
class _SegmentMark:
    """One ``MarkSegments`` entry: the span, its family and the group it belongs to
    (``key``: a tick count, else the group string)."""
    a: Point
    b: Point
    family: str  # "tick" | "parallel"
    key: int | str


@dataclass(frozen=True)
class _AngleMark:
    """One ``MarkAngles`` entry: the vertex, the two arms, the arc count, the side."""
    vertex: Point
    arms: tuple[Point, Point]
    count: int
    which: str


def _tick_key(group: str | None, ticks: int | None) -> int | str:
    if ticks is not None:
        return ticks
    found = _TICK_GROUP.match(group or "")
    return int(found[1]) if found else group or ""


def _arc_count(group: str | None) -> int:
    found = _ARC_GROUP.match(group or "")
    return min(int(found[1]), MAX_ARCS) if found else 1


def _is_dashed(styles: dict, style: object) -> bool:
    """Whether a draw op's style is dashed: a style named so, or one whose own ``dashed``
    property is set (python_full names its styles ``__pydsl_style_N``; a prism's hidden edges
    use the reserved style ``__{id}_hidden``). ``styles`` is the lowered view's style table."""
    name = str(style or "")
    return "dashed" in name or bool((styles.get(name) or {}).get("dashed", False))


def _xy(p) -> Point:
    return (float(p.x), float(p.y))


class DrawingView:
    """A diagram read by the figure's compiled points and the objects it draws."""

    def __init__(self, diagram, sym: dict):
        from geometry_diagrams.ir.derived import effective_diagram, lower_render
        from geometry_diagrams.ir.to_sympy import float_point_table
        self.diagram = diagram  # the AUTHORED diagram
        points = float_point_table(sym)
        self.points = points
        self._resolver = NameResolver(points, diagram)
        self.straights: list[_Straight] = []
        self.circles: list[tuple[Point, float]] = []
        self.shaded: list[list[Point]] = []
        self.segment_marks: list[_SegmentMark] = []
        self.angle_marks: list[_AngleMark] = []
        self.free_texts: list[tuple[str, Point]] = []
        self.segment_labels: list[tuple[str, str]] = []  # (text, segment id)
        # every compiled line/segment/ray: id -> (p1, p2, kind), and the ids drawn directly
        self.linear: dict[str, tuple[Point, Point, str]] = {}
        self.drawn: set[str] = set()
        pts = list(points.values())
        # the figure's extent: every compiled point counts, hidden helpers included
        self.scale = max((math.dist(p, q) for p in pts for q in pts), default=1.0) or 1.0

        # The lowered view is what the renderers draw (a prism or stack draw is already
        # replaced by edges / ordered polygons); it is read per op, never dumped.
        lowered = lower_render(effective_diagram(diagram), sym, [])
        styles = lowered.styles
        for op in lowered.render:
            kind = op.kind
            if kind == "draw":
                self._read_draw(op, sym, styles)
            elif kind == "ordered_polygon":
                corners = [points[i] for i in op.points if i in points]
                if len(corners) == len(op.points):
                    self._add_sides(corners, False)
            elif kind == "fill":
                obj = sym.get(op.obj)
                if isinstance(obj, spg.Polygon):
                    self.shaded.append([_xy(v) for v in obj.vertices])
            elif kind == "label_free_text" and op.at is not None and len(op.at) == 2:
                self.free_texts.append((str(op.text), (float(op.at[0]), float(op.at[1]))))
            elif kind == "label_segment":
                self.segment_labels.append((str(op.text), op.seg))
        for oid, obj in sym.items():
            if isinstance(obj, (spg.Segment, spg.Ray, spg.Line)):
                kind = "segment" if isinstance(obj, spg.Segment) else "ray" if isinstance(obj, spg.Ray) else "line"
                self.linear[oid] = (_xy(obj.p1), _xy(obj.p2), kind)
        defs = {d.id: d.model_dump() for d in diagram.define}
        self._read_marks(diagram, defs, points)

    def _add_sides(self, corners: list[Point], dashed: bool, closed: bool = True) -> None:
        n = len(corners)
        for i in range(n if closed else n - 1):
            self.straights.append(_Straight(corners[i], corners[(i + 1) % n], "segment", dashed))

    def _read_draw(self, op, sym: dict, styles: dict) -> None:
        obj = sym.get(op.obj)
        self.drawn.add(op.obj)
        dashed = _is_dashed(styles, op.style)
        if isinstance(obj, spg.Polygon):  # also Triangle
            self._add_sides([_xy(v) for v in obj.vertices], dashed)
        elif isinstance(obj, list):  # an open polyline: a chain of straights, no closing side
            chain = [_xy(v) for v in obj if isinstance(v, spg.Point)]
            if len(chain) == len(obj):
                self._add_sides(chain, dashed, closed=False)
        elif isinstance(obj, (spg.Segment, spg.Ray, spg.Line)):
            kind = "segment" if isinstance(obj, spg.Segment) else "ray" if isinstance(obj, spg.Ray) else "line"
            self.straights.append(_Straight(_xy(obj.p1), _xy(obj.p2), kind, dashed))
        elif isinstance(obj, spg.Circle):  # not an ellipse, arc or sector
            self.circles.append((_xy(obj.center), float(obj.radius)))

    def _read_marks(self, diagram, defs: dict[str, dict], points: dict[str, Point]) -> None:
        ends: dict[str, tuple[Point, Point]] = {}
        for did, m in defs.items():
            pair = (m["p"], m["q"]) if m["kind"] == "line_through" else (
                (m["a"], m["b"]) if m["kind"] in ("segment", "ray") else None
            )
            if pair and pair[0] in points and pair[1] in points:
                ends[did] = (points[pair[0]], points[pair[1]])
        for op in diagram.render:
            data = op.model_dump()
            if data["kind"] == "mark_segments":
                group, ticks = data.get("group"), data.get("ticks")
                parallel = ticks is None and str(group or "").startswith("parallel")
                for s in data["segs"]:
                    if s in ends:
                        self.segment_marks.append(_SegmentMark(
                            *ends[s], "parallel" if parallel else "tick",
                            str(group) if parallel else _tick_key(group, ticks),
                        ))
            elif data["kind"] == "mark_angles":
                count = _arc_count(data.get("group"))
                for ang in data["angles"]:
                    if all(ang[k] in points for k in "aob"):
                        self.angle_marks.append(_AngleMark(
                            points[ang["o"]], (points[ang["a"]], points[ang["b"]]),
                            count, str(data.get("which", "interior")),
                        ))

    @property
    def tolerance(self) -> float:
        return LINE_TOLERANCE * self.scale

    def point(self, name: str) -> Point | None:
        found = self.points.get(name)
        if found is not None:
            return found
        try:
            return self.points.get(self._resolver.resolve(name))
        except NameResolutionError:
            return None

    def segment_label_names_line(self, name: str, a: Point, b: Point) -> bool:
        """Whether a ``label_segment`` reading ``name`` targets a drawn line, segment or ray
        that both ``a`` and ``b`` lie on (within the tolerance of the infinite line). Drawn
        means a draw of the object itself, or, for a segment only, its span covered by drawn
        straight objects (a prism edge is drawn as part of a face outline)."""
        for text, seg in self.segment_labels:
            found = self.linear.get(seg)
            if found is None or _bare(text) != _bare(name):
                continue
            p1, p2, kind = found
            drawn = seg in self.drawn or (kind == "segment" and _span_is_drawn(self, p1, p2))
            if drawn and all(_distance_to_line(p, p1, p2) <= self.tolerance for p in (a, b)):
                return True
        return False

    def segment_mark_keys(self, family: str, a: Point, b: Point) -> set[int | str]:
        """Group keys of the ``family`` marks on the span a-b (either order)."""
        tol = self.tolerance
        return {
            m.key for m in self.segment_marks
            if m.family == family and (
                (math.dist(m.a, a) <= tol and math.dist(m.b, b) <= tol)
                or (math.dist(m.a, b) <= tol and math.dist(m.b, a) <= tol)
            )
        }

    def angle_mark_counts(self, a: Point, o: Point, b: Point, which: str | None = None) -> set[int]:
        """Arc counts marked on the angle a-o-b: vertex within tolerance, arms matched by
        direction (any point along a ray will do); ``which`` limits to interior/reflex."""
        found: set[int] = set()
        want = [_direction(o, a), _direction(o, b)]
        for m in self.angle_marks:
            if math.dist(m.vertex, o) > self.tolerance or (which is not None and m.which != which):
                continue
            have = [_direction(o, m.arms[0]), _direction(o, m.arms[1])]
            if None in want or None in have:
                continue
            if (_same_ray(want[0], have[0]) and _same_ray(want[1], have[1])) or (
                _same_ray(want[0], have[1]) and _same_ray(want[1], have[0])
            ):
                found.add(m.count)
        return found


_VIEW_CACHE: dict[str, tuple[Any, dict]] = {}


def read_drawing(diagram_ir: dict) -> DrawingView:
    """The authored IR (a dict) read as a ``DrawingView``; the last one is cached (on the
    authored dict), because a scenario runs several checks on one figure. Raises what
    compiling or lowering raises (``_guarded`` turns that into a failed check)."""
    from geometry_diagrams.ir.ir import DiagramIR
    from geometry_diagrams.ir.to_sympy import compile_defs
    key = json.dumps(diagram_ir, sort_keys=True, default=str)
    hit = _VIEW_CACHE.get("last")
    if hit is not None and hit[0] == key:
        return hit[1]
    diagram = DiagramIR.model_validate(diagram_ir)
    view = DrawingView(diagram, compile_defs(diagram))
    _VIEW_CACHE["last"] = (key, view)
    return view


def _guarded(evaluate):
    """An evaluator whose compile/lowering failure is a failed check, not an exception."""
    @functools.wraps(evaluate)
    def wrapper(args, diagram_ir, tikz_code):
        try:
            return evaluate(args, diagram_ir, tikz_code)
        except Exception as exc:
            return {"passed": False, "message": f"Error: {exc}"}
    return wrapper


def resolve_check_args(
    args: dict, name_keys: Sequence[str], diagram_ir: dict, variable_ids: dict | None = None,
) -> tuple[dict, dict]:
    """``args`` with the point names under ``name_keys`` (``points``, ``center``, ``members``,
    ``segments``) resolved to figure ids, and the names that needed resolving (name -> id).
    Raises ``NameResolutionError`` for a name that is unresolved or ambiguous, or for two
    names of one key that are the same point."""
    view = read_drawing(diagram_ir)
    resolver = NameResolver(view.points, view.diagram, variable_ids)
    out = dict(args)
    resolved: dict[str, str] = {}
    for key in name_keys:
        if key in out:
            resolver.resolved = {}
            out[key] = resolver.resolve_args(out[key])
            resolved.update(resolver.resolved)
    return out, resolved


# ---------------------------------------------------------------------------
# Geometry of the drawn spans
# ---------------------------------------------------------------------------

def _direction(origin: Point, to: Point) -> float | None:
    dx, dy = to[0] - origin[0], to[1] - origin[1]
    return None if dx == 0 and dy == 0 else math.degrees(math.atan2(dy, dx))


def _same_ray(u: float | None, v: float | None) -> bool:
    if u is None or v is None:
        return False
    gap = abs(u - v) % 360.0
    return min(gap, 360.0 - gap) <= ANGLE_TOLERANCE_DEG


def _dist_to_span(pt: Point, s: _Straight) -> float:
    dx, dy = s.b[0] - s.a[0], s.b[1] - s.a[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.dist(pt, s.a)
    t = ((pt[0] - s.a[0]) * dx + (pt[1] - s.a[1]) * dy) / length_sq
    if s.kind == "segment":
        t = max(0.0, min(1.0, t))
    elif s.kind == "ray":
        t = max(0.0, t)
    return math.dist(pt, (s.a[0] + t * dx, s.a[1] + t * dy))


def _span_is_drawn(view: DrawingView, a: Point, b: Point, dashed_only: bool = False) -> bool:
    """Whether drawn straight objects (only dashed ones if asked) cover the whole span a-b,
    sampled along it; a run drawn in several pieces counts."""
    pool = [s for s in view.straights if s.dashed or not dashed_only]
    for k in range(COVER_SAMPLES + 1):
        t = k / COVER_SAMPLES
        sample = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        if not any(_dist_to_span(sample, s) <= view.tolerance for s in pool):
            return False
    return True


def _distance_to_segment(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_sq))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def _distance_to_line(p: Point, a: Point, b: Point) -> float:
    """Distance from ``p`` to the infinite line through ``a`` and ``b``."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return math.dist(p, a)
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / length


def _line_angle_deg(p: tuple[Point, Point], q: tuple[Point, Point]) -> float:
    ang = math.atan2(p[1][1] - p[0][1], p[1][0] - p[0][0]) - math.atan2(
        q[1][1] - q[0][1], q[1][0] - q[0][0]
    )
    return abs(math.degrees(ang)) % 180.0


def _same_run(s1: _Straight, s2: _Straight, tol: float, merge_deg: float) -> bool:
    """Whether two spans are collinear (within ``merge_deg``) and overlap or touch."""
    d1 = (s1.b[0] - s1.a[0], s1.b[1] - s1.a[1])
    length = math.hypot(*d1)
    if length == 0:
        return False
    apart = _line_angle_deg((s1.a, s1.b), (s2.a, s2.b))
    if min(apart, 180.0 - apart) > merge_deg:
        return False

    def along(p: Point) -> tuple[float, float]:
        t = ((p[0] - s1.a[0]) * d1[0] + (p[1] - s1.a[1]) * d1[1]) / length
        off = abs((p[0] - s1.a[0]) * d1[1] - (p[1] - s1.a[1]) * d1[0]) / length
        return t, off

    (t1, off1), (t2, off2) = along(s2.a), along(s2.b)
    if max(off1, off2) > tol:
        return False
    lo, hi = sorted((t1, t2))
    return hi >= -tol and lo <= length + tol


def _counts(view: DrawingView, merge_deg: float = RUN_DIRECTION_TOLERANCE_DEG,
            offset_scale: float = 1.0) -> dict[str, int]:
    """The drawn circles and straight runs (union-find over spans that are one run)."""
    parent = list(range(len(view.straights)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, s1 in enumerate(view.straights):
        for j in range(i + 1, len(view.straights)):
            if _same_run(s1, view.straights[j], view.tolerance * offset_scale, merge_deg):
                parent[find(i)] = find(j)
    return {"circle": len(view.circles), "straight": len({find(i) for i in range(len(parent))})}


def _count_problems(limits: dict[str, tuple[int, int]], view: DrawingView) -> list[str]:
    """What is wrong with the circles and straight runs drawn: more than ``high`` is judged
    on the usual merge, fewer than ``low`` on the stricter one."""
    most = _counts(view)
    fewest = _counts(view, OMISSION_MERGE_DEG, OMISSION_OFFSET_SCALE)
    wrong: list[str] = []
    for key, (low, high) in limits.items():
        if fewest[key] < low:
            wrong.append(f"{key}: {fewest[key]} drawn, at least {low} expected")
        elif most[key] > high:
            wrong.append(f"{key}: {most[key]} drawn, at most {high} expected")
    return wrong


# ---------------------------------------------------------------------------
# Argument validators (run when a scenario file loads)
# ---------------------------------------------------------------------------

def _check_keys(args: dict, where: str, allowed: set[str], kind: str) -> None:
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown {kind} arg(s) {unknown}")


def _names(args: dict, key: str) -> list[str]:
    value = args.get(key)
    return [str(v) for v in value] if isinstance(value, list) else []


def _non_empty_names(args: dict, where: str, kind: str, least: int, key: str = "points") -> None:
    value = args.get(key)
    if (not isinstance(value, list) or len(value) < least
            or any(not isinstance(v, str) or not v.strip() for v in value)):
        raise ValueError(f"{where}: {kind} '{key}' must be a list of at least {least} point names")


def _validate_dashed(args: dict, where: str) -> None:
    _check_keys(args, where, {"points", "object"}, "dashed")
    _non_empty_names(args, where, "dashed", 2)
    if args.get("object", "segment") not in OBJECT_KINDS:
        raise ValueError(f"{where}: dashed 'object' must be one of {sorted(OBJECT_KINDS)}")


def _validate_shaded(args: dict, where: str) -> None:
    _check_keys(args, where, {"points"}, "shaded")
    _non_empty_names(args, where, "shaded", 3)


def _validate_concentric(args: dict, where: str) -> None:
    _check_keys(args, where, {"center", "count"}, "concentric_circles")
    centre, count = args.get("center"), args.get("count")
    if not isinstance(centre, str) or not centre.strip():
        raise ValueError(f"{where}: concentric_circles 'center' must be a non-empty point name")
    if isinstance(count, bool) or not isinstance(count, int) or count < 2:
        raise ValueError(f"{where}: concentric_circles 'count' must be an integer of two or more")


def _validate_line_name(args: dict, where: str) -> None:
    _check_keys(args, where, {"points", "name"}, "line_name")
    _non_empty_names(args, where, "line_name", 2)
    name = args.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{where}: line_name 'name' must be a non-empty string")


def _members(args: dict) -> list[list[str]] | None:
    """The named members of a mark group (3 names per angle, 2 per segment), None if malformed."""
    value = args.get("members")
    width = 3 if args.get("mark") == "angle" else 2
    if not isinstance(value, list) or not value:
        return None
    found = []
    for member in value:
        if (not isinstance(member, list) or len(member) != width
                or any(not isinstance(n, str) or not n.strip() for n in member)):
            return None
        found.append([str(n) for n in member])
    return found


def _validate_mark_group(args: dict, where: str) -> None:
    _check_keys(args, where, {"mark", "members", "sides"}, "mark_group")
    mark = args.get("mark")
    if mark not in MARK_FAMILIES:
        raise ValueError(f"{where}: mark_group 'mark' must be one of {list(MARK_FAMILIES)}")
    members = _members(args)
    if members is None:
        raise ValueError(
            f"{where}: mark_group 'members' must be a non-empty list of "
            f"{3 if mark == 'angle' else 2} point names each"
        )
    sides = args.get("sides")
    if sides is None:
        return
    if (mark != "angle" or not isinstance(sides, list) or len(sides) != len(members)
            or any(x not in ANGLE_SIDES for x in sides)):
        raise ValueError(
            f"{where}: mark_group 'sides' is for angles only, one of {sorted(ANGLE_SIDES)} per member"
        )


def _validate_polygon_drawn(args: dict, where: str) -> None:
    _check_keys(args, where, {"points"}, "polygon_drawn")
    _non_empty_names(args, where, "polygon_drawn", 3)


def _validate_object_exists(args: dict, where: str) -> None:
    _check_keys(args, where, {"object", "points"}, "object_exists")
    kind = args.get("object")
    if kind not in EXISTENCE_OBJECTS:
        raise ValueError(f"{where}: object_exists 'object' must be one of {sorted(EXISTENCE_OBJECTS)}")
    _non_empty_names(args, where, "object_exists", 1 if kind == "circle" else 2)


def _length_pairs(args: dict) -> list[tuple[list[str], float]] | None:
    """The (segment, written value) pairs of a length_ratios check, None if malformed."""
    segments, values = args.get("segments"), args.get("values")
    if not isinstance(segments, list) or not isinstance(values, list) or len(segments) != len(values):
        return None
    pairs = []
    for seg, value in zip(segments, values):
        if (not isinstance(seg, list) or len(seg) != 2
                or any(not isinstance(n, str) or not n.strip() for n in seg)
                or isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
            return None
        pairs.append(([str(n) for n in seg], float(value)))
    return pairs


def _validate_length_ratios(args: dict, where: str) -> None:
    _check_keys(args, where, {"segments", "values"}, "length_ratios")
    pairs = _length_pairs(args)
    if pairs is None or len(pairs) < 2:
        raise ValueError(
            f"{where}: length_ratios needs 'segments' (lists of two point names) and "
            "'values' (positive numbers, one each), at least 2"
        )


def _count_range(value: object) -> tuple[int, int] | None:
    if (not isinstance(value, list) or len(value) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in value)):
        return None
    low, high = value
    return (low, high) if low <= high else None


def _validate_object_count(args: dict, where: str) -> None:
    _check_keys(args, where, set(COUNT_KEYS), "object_count")
    for key in COUNT_KEYS:
        if _count_range(args.get(key)) is None:
            raise ValueError(
                f"{where}: object_count '{key}' must be [low, high], whole numbers "
                "of at least 0 with low not above high"
            )


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------

def _unknown(names: list[str], points: list[Point | None]) -> dict:
    return _result(False, f"no point named {', '.join(n for n, p in zip(names, points) if p is None)}")


@register_structural_type("dashed", validate_args=_validate_dashed, name_keys=("points",))
@_guarded
def _eval_dashed(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """dashed: drawn dashed straight objects cover the whole span between the first two
    named points (a dashed run drawn in pieces counts). The object kind is not enforced. A
    prism's hidden edges are dashed (its reserved ``__{id}_hidden`` style); a block stack
    draws no dashed edge, so dashed on a stack never passes."""
    names = _names(args, "points")
    if diagram_ir is None or len(names) < 2:
        return _skip("needs the authored IR and two named points")
    view = read_drawing(diagram_ir)
    found = [view.point(n) for n in names[:2]]
    if None in found:
        return _unknown(names[:2], found)
    ok = _span_is_drawn(view, found[0], found[1], dashed_only=True)
    return _result(ok, "" if ok else f"{names[0]}{names[1]} is not drawn dashed along its span")


@register_structural_type("shaded", validate_args=_validate_shaded, name_keys=("points",))
@_guarded
def _eval_shaded(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """shaded: a filled triangle or polygon has exactly the named corners, in any order."""
    names = _names(args, "points")
    if diagram_ir is None or len(names) < 3:
        return _skip("needs the authored IR and three named corners")
    view = read_drawing(diagram_ir)
    corners = [view.point(n) for n in names]
    if None in corners:
        return _unknown(names, corners)
    for polygon in view.shaded:
        remaining = list(polygon)
        if len(remaining) != len(corners):
            continue
        for corner in corners:
            near = next((q for q in remaining if math.dist(q, corner) <= view.tolerance), None)
            if near is not None:
                remaining.remove(near)
        if not remaining:
            return _result(True)
    return _result(False, f"no fill over the polygon {''.join(names)}")


@register_structural_type("concentric_circles", validate_args=_validate_concentric, name_keys=("center",))
@_guarded
def _eval_concentric(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """concentric_circles: at least ``count`` circles centred on the point whose radii
    differ pairwise by more than the tolerance (one circle drawn twice is one)."""
    centre, count = args.get("center"), args.get("count")
    if diagram_ir is None or not isinstance(centre, str) or not isinstance(count, int) or count < 2:
        return _skip("needs the authored IR, a centre and a count of two or more")
    view = read_drawing(diagram_ir)
    middle = view.point(centre)
    if middle is None:
        return _result(False, f"no point named {centre}")
    radii = sorted(r for c, r in view.circles if math.dist(c, middle) <= view.tolerance)
    distinct = [r for i, r in enumerate(radii) if i == 0 or r - radii[i - 1] > view.tolerance]
    ok = len(distinct) >= count
    return _result(ok, "" if ok else f"{len(distinct)} different radii about {centre}, expected {count}")


@register_structural_type("line_name", validate_args=_validate_line_name, name_keys=("points",))
@_guarded
def _eval_line_name(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """line_name: the name is on the line through the first and last named point, by one of
    two routes. Strong: a ``label_segment`` whose text equals the name (``$m$`` == ``m``)
    targets a drawn line, segment or ray that both named points lie on (each within the
    tolerance of the INFINITE line, so a labelled segment shorter than the named span still
    counts); the label is bound to the object it targets, never to the nearest line. Weak
    fallback: a ``label_free_text`` reading the name sits within 15% of the figure's extent of
    the segment between the two points; it cannot tell which of two nearby lines the text
    names."""
    names, wanted = _names(args, "points"), args.get("name")
    if diagram_ir is None or len(names) < 2 or not isinstance(wanted, str):
        return _skip("needs the authored IR, two points on the line and its name")
    view = read_drawing(diagram_ir)
    ends = [view.point(names[0]), view.point(names[-1])]
    if None in ends:
        return _unknown([names[0], names[-1]], ends)
    if view.segment_label_names_line(wanted, ends[0], ends[1]):
        return _result(True)
    reach = LINE_NAME_REACH_FRACTION * view.scale
    texts = [at for text, at in view.free_texts if _bare(text) == _bare(wanted)]
    if any(_distance_to_segment(t, ends[0], ends[1]) <= reach for t in texts):
        return _result(True)
    return _result(False,
                   f"the name {wanted!r} is neither a segment label on a drawn line through "
                   f"{names[0]} and {names[-1]} nor a free text beside it")


@register_structural_type("mark_group", validate_args=_validate_mark_group, name_keys=("members",))
@_guarded
def _eval_mark_group(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """mark_group: the named segments (or angles) carry the same mark, read from
    ``mark_segments``/``mark_angles``: a tick count, a ``parallelN`` group or an arc count
    common to all members. It never counts marks the claim did not name, so two groups drawn
    with the same count cannot be told apart (an accepted limit)."""
    mark, members = args.get("mark"), _members(args)
    if diagram_ir is None or mark not in MARK_FAMILIES or members is None:
        return _skip("needs the authored IR and the named members of the group")
    view = read_drawing(diagram_ir)
    sides = args.get("sides")
    keys: list[set] = []
    for i, member in enumerate(members):
        points = [view.point(n) for n in member]
        if None in points:
            return _unknown(member, points)
        if mark == "angle":
            found = view.angle_mark_counts(points[0], points[1], points[2], sides[i] if sides else None)
        else:
            found = view.segment_mark_keys(mark, points[0], points[1])
        if not found:
            return _result(False, f"{''.join(member)} carries no {mark} mark")
        keys.append(found)
    if set(keys[0]).intersection(*keys[1:]):
        return _result(True)
    return _result(False, f"{', '.join(''.join(m) for m in members)} do not carry the same {_GROUP_NOUN[mark]}")


@register_structural_type("polygon_drawn", validate_args=_validate_polygon_drawn, name_keys=("points",))
@_guarded
def _eval_polygon_drawn(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """polygon_drawn: every side between consecutive named vertices (the last back to the
    first) is covered by drawn straight objects, whatever drew them. A longer object drawn
    along a side also covers it."""
    names = _names(args, "points")
    if diagram_ir is None or len(names) < 3:
        return _skip("needs the authored IR and three named vertices")
    view = read_drawing(diagram_ir)
    corners = [view.point(n) for n in names]
    if None in corners:
        return _unknown(names, corners)
    for i, a in enumerate(corners):
        j = (i + 1) % len(corners)
        if not _span_is_drawn(view, a, corners[j]):
            return _result(False, f"side {names[i]}{names[j]} of {''.join(names)} is not drawn")
    return _result(True)


@register_structural_type("object_exists", validate_args=_validate_object_exists, name_keys=("points",))
@_guarded
def _eval_object_exists(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """object_exists: a circle about the first named point (through the second, if named), or
    drawn straight objects covering the span between two named points. The kind (segment,
    ray, line) is not enforced, and a longer object lying along the span also covers it."""
    kind, names = args.get("object"), _names(args, "points")
    if diagram_ir is None or kind not in EXISTENCE_OBJECTS or len(names) < (1 if kind == "circle" else 2):
        return _skip("needs the authored IR, an object kind and its named points")
    view = read_drawing(diagram_ir)
    points = [view.point(n) for n in names]
    if None in points:
        return _unknown(names, points)
    if kind == "circle":
        centre, *anchors = points
        about = [r for c, r in view.circles if math.dist(c, centre) <= view.tolerance]
        ok = any(not anchors or abs(math.dist(centre, anchors[0]) - r) <= view.tolerance for r in about)
        return _result(ok, "" if ok else
                       f"no circle about {names[0]}" + (f" through {names[1]}" if anchors else "") + " is drawn")
    ok = _span_is_drawn(view, points[0], points[1])
    return _result(ok, "" if ok else f"no drawn {kind} covers {names[0]}{names[1]}")


def _ratio_agreement(mine: float, others: list[float]) -> int:
    """How many of the other drawn-to-written ratios are within 3% of the larger one."""
    return sum(abs(mine - r) <= LENGTH_TOLERANCE * max(mine, r) for r in others)


@register_structural_type("length_ratios", validate_args=_validate_length_ratios, name_keys=("segments",))
@_guarded
def _eval_length_ratios(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """length_ratios: the named segments have the written lengths up to one common scale.
    Each segment's drawn/written ratio must agree with that of at least half the others, so a
    figure drawn at any size passes and one stray length fails alone."""
    pairs = _length_pairs(args)
    if diagram_ir is None or pairs is None or len(pairs) < 2:
        return _skip("needs the authored IR and at least two written lengths")
    view = read_drawing(diagram_ir)
    ratios: list[float] = []
    for names, value in pairs:
        ends = [view.point(n) for n in names]
        if None in ends:
            return _unknown(names, ends)
        ratios.append(math.dist(ends[0], ends[1]) / value)
    strays = []
    for i, (names, _value) in enumerate(pairs):
        others = [r for j, r in enumerate(ratios) if j != i]
        if 2 * _ratio_agreement(ratios[i], others) < len(others):
            strays.append("".join(names))
    if not strays:
        return _result(True)
    return _result(False, f"{', '.join(strays)} not in proportion with the other written "
                          f"lengths (within {LENGTH_TOLERANCE:.0%})")


@register_structural_type("object_count", validate_args=_validate_object_count)
@_guarded
def _eval_object_count(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """object_count: the figure draws between ``low`` and ``high`` circles (full circles only,
    never arcs, sectors or ellipses) and straight runs (a run is a maximal set of collinear
    spans that overlap or touch, however drawn). An open polyline counts as its chain of
    straights. Meaningless on solids: a prism counts as its drawn edges and a block stack as
    its painted cube edges merged into runs (use ``solid_count``/``stack_*``). Hidden
    helpers that are never drawn do not count. An omission that leaves pieces between the two
    merge rules still reaches ``low`` and is not caught (an accepted limit)."""
    limits = {key: _count_range(args.get(key)) for key in COUNT_KEYS}
    if diagram_ir is None or any(r is None for r in limits.values()):
        return _skip("needs the authored IR and a [low, high] range for each kind")
    wrong = _count_problems(limits, read_drawing(diagram_ir))
    return _result(not wrong, "; ".join(wrong))

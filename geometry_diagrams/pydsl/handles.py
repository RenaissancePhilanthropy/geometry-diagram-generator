# geometry_diagrams/pydsl/handles.py
"""Thin typed handles returned by pydsl API functions.

A handle wraps an internal id (auto-generated or model-supplied for
identity-carrying points) and never requires the model to re-derive
geometric parts from raw point references — see Triangle/Polygon for the
accessor pattern that replaces the DSL's string-id threading.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _record_literal_point(builder: "object", x: float, y: float) -> "Point":
    """Record a new point_fixed def for a coordinate computed via Point
    arithmetic (e.g. `center + k * (source - center)`), the same way api.py's
    point() does — kept here rather than imported from api.py to avoid a
    handles<->api circular import. Takes `builder` explicitly (the caller's
    own captured `self._builder`) rather than calling get_builder(): this
    runs from inside Point.__add__/__sub__/__mul__, which execute as a
    script's own top-level statements, not nested inside a
    _bind_to_builder-wrapped tool call — get_builder()'s ambient contextvar
    is not set at that point when running inside the real sandbox."""
    from geometry_diagrams.ir.ir import PointFixed

    pid = builder._fresh_hidden_id("pt")
    builder._add(PointFixed(id=pid, x=x, y=y))
    builder._coord_floats[pid] = (float(x), float(y))
    return Point(id=pid, _builder=builder, x=float(x), y=float(y))


@dataclass(frozen=True)
class Point:
    id: str
    _builder: "object" = field(repr=False, compare=False)  # type is Builder; avoid a
                                                             # circular import at module load
    # Known only for point(x, y) literals (and points derived from them via
    # arithmetic) — never for constructed points (point_on, rotate_point,
    # dilate_point, reflect_point, ...), whose coordinates aren't resolved
    # until later via SymPy. None here, not a wrong guess, is the honest
    # answer for those; arithmetic on them raises rather than silently
    # producing a bogus result.
    x: float | None = None
    y: float | None = None

    def _known(self, other: "Point | None" = None) -> None:
        for pt in (self, other):
            if pt is not None and (pt.x is None or pt.y is None):
                raise ValueError(
                    f"Point {pt.id!r} has no known coordinates (only point(x, y) "
                    "literals — and points derived from them via +, -, * — carry "
                    "coordinates back to the script; a point from point_on()/"
                    "rotate_point()/dilate_point()/reflect_point()/etc. does not, "
                    "since its position isn't resolved until later). Use "
                    "dilate_point()/rotate_point()/reflect_point() instead of "
                    "arithmetic when either point's coordinates aren't known."
                )

    def __add__(self, other: "Point") -> "Point":
        self._known(other)
        return _record_literal_point(self._builder, self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        self._known(other)
        return _record_literal_point(self._builder, self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Point":
        self._known()
        return _record_literal_point(self._builder, self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def label(self, text: str, pos: str = "auto", show_coords: bool = False) -> None:
        """Label this point with text, e.g. p.label("A")."""
        from geometry_diagrams.ir.ir import LabelPoint

        self._builder._add_render(
            LabelPoint(p=self.id, text=text, pos=pos, show_coords=show_coords)
        )


@dataclass(frozen=True)
class Line:
    id: str


@dataclass(frozen=True)
class Segment:
    id: str
    _builder: "object" = field(repr=False, compare=False)

    def label(self, text: str, pos: "float | None" = None) -> None:
        """Label this segment with text, e.g. seg.label("r")."""
        from geometry_diagrams.ir.ir import LabelSegment

        self._builder._add_render(LabelSegment(seg=self.id, text=text, pos=pos))


@dataclass(frozen=True)
class Triangle:
    id: str
    vertices: tuple[Point, Point, Point]
    _builder: "object" = field(repr=False, compare=False)  # type is Builder; avoid a
                                                             # circular import at module load

    def side(self, p: Point, q: Point) -> "Segment":
        vertex_ids = {v.id for v in self.vertices}
        for name, pt in (("p", p), ("q", q)):
            if pt.id not in vertex_ids:
                raise ValueError(f"{pt.id!r} is not a vertex of triangle {self.id!r} ({name})")
        return self._builder._get_or_create_segment(p.id, q.id)

    def angle_at(self, v: Point) -> "AngleRef":
        from geometry_diagrams.pydsl.handles import AngleRef  # Task 7

        vertex_ids = [vert.id for vert in self.vertices]
        if v.id not in vertex_ids:
            raise ValueError(f"{v.id!r} is not a vertex of triangle {self.id!r}")
        others = [pid for pid in vertex_ids if pid != v.id]
        return AngleRef(
            a=Point(id=others[0], _builder=self._builder),
            o=v,
            b=Point(id=others[1], _builder=self._builder),
            _builder=self._builder,
        )


@dataclass(frozen=True)
class Circle:
    id: str
    center: Point
    _radius_thunk: "object" = field(repr=False, compare=False)  # Callable[[], float | str]

    @property
    def radius(self) -> "float | str":
        return self._radius_thunk()


@dataclass(frozen=True)
class Polygon:
    id: str
    vertices: tuple[Point, ...]
    _builder: "object" = field(repr=False, compare=False)

    def side(self, v1: Point, v2: Point) -> "Segment":
        ids = [v.id for v in self.vertices]
        for name, pt in (("v1", v1), ("v2", v2)):
            if pt.id not in ids:
                raise ValueError(f"{pt.id!r} is not a vertex of polygon {self.id!r} ({name})")
        i1, i2 = ids.index(v1.id), ids.index(v2.id)
        n = len(ids)
        if abs(i1 - i2) % n not in (1, n - 1):
            raise ValueError(
                f"{v1.id!r} and {v2.id!r} are not adjacent vertices of polygon {self.id!r}"
            )
        return self._builder._get_or_create_segment(v1.id, v2.id)

    def angle_at(self, v: Point) -> "AngleRef":
        from geometry_diagrams.pydsl.handles import AngleRef  # Task 7

        ids = [vert.id for vert in self.vertices]
        if v.id not in ids:
            raise ValueError(f"{v.id!r} is not a vertex of polygon {self.id!r}")
        n = len(ids)
        i = ids.index(v.id)
        prev_id, next_id = ids[(i - 1) % n], ids[(i + 1) % n]
        return AngleRef(
            a=Point(id=prev_id, _builder=self._builder),
            o=v,
            b=Point(id=next_id, _builder=self._builder),
            _builder=self._builder,
        )


@dataclass(frozen=True)
class AngleRef:
    a: Point
    o: Point
    b: Point
    _builder: "object" = field(repr=False, compare=False)

    def label(self, text: str, pos: "float | None" = None) -> None:
        """Label this angle with text, e.g. ref.label("theta")."""
        from geometry_diagrams.ir.ir import AnglePoints, LabelAngle

        self._builder._add_render(LabelAngle(
            angle=AnglePoints(a=self.a.id, o=self.o.id, b=self.b.id),
            text=text, pos=pos,
        ))


@dataclass(frozen=True)
class Median:
    id: str
    midpoint: Point
    segment: "Segment"


@dataclass(frozen=True)
class Altitude:
    id: str
    foot: Point
    line: Line
    segment: "Segment"

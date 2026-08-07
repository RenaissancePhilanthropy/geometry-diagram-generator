# geometry_diagrams/pydsl/handles.py
"""Thin typed handles returned by pydsl API functions.

A handle wraps an internal id (auto-generated or model-supplied for
identity-carrying points) and never requires the model to re-derive
geometric parts from raw point references — see Triangle/Polygon for the
accessor pattern that replaces the DSL's string-id threading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Escape letters Python's own string-literal parser recognizes for control
# characters that are never legitimate inside label text (unlike \n/\r/\t,
# which could plausibly be real whitespace) — mapping from the resulting
# control byte back to the letter that produced it.
_CONTROL_CHAR_TO_ESCAPE_LETTER = {
    "\a": "a",  # BEL, 0x07
    "\b": "b",  # BS,  0x08
    "\f": "f",  # FF,  0x0C
    "\v": "v",  # VT,  0x0B
}
_CONTROL_CHAR_RE = re.compile("[" + "".join(_CONTROL_CHAR_TO_ESCAPE_LETTER) + "]" + r"[A-Za-z]*")


def _sanitize_label_text(text: str, fn_name: str) -> str:
    """Recover from a classic Python-string-escaping trap: a script that
    writes a LaTeX-style command like "\\angle ABD" in a normal (non-raw)
    Python string literal has its backslash silently consumed by Python's
    own parser as an escape sequence before this code ever sees the text —
    "\\angle" (backslash + "a" + "ngle") becomes a literal BEL control
    character followed by "ngle". Left alone, that control character makes
    it all the way into the rendered SVG, which then fails "not valid XML"
    with no indication of the actual cause (confirmed 2026-08-07, >50% of
    google.gemma-4-31b's curriculum-eval failures traced to exactly this).

    If putting the control character's escape letter back reconstructs a
    known LaTeX macro name (checked against geometry_diagrams.ir.to_svg's
    own _LATEX_UNICODE table — the same substitution to_svg.py would have
    made had the model wrapped it in $...$), silently repair it to the
    correct Unicode symbol. Otherwise raise a clear error rather than let a
    mystery control character reach the renderer."""
    from geometry_diagrams.ir.to_svg import _LATEX_UNICODE

    def _replace(match: "re.Match") -> str:
        raw = match.group(0)
        letter = _CONTROL_CHAR_TO_ESCAPE_LETTER[raw[0]]
        macro = letter + raw[1:]
        symbol = _LATEX_UNICODE.get(macro)
        if symbol is not None:
            return symbol
        raise ValueError(
            f"{fn_name}(): text contains a non-printable control character "
            f"(byte {ord(raw[0]):#04x}) where '\\{macro}' appears to have "
            "been intended — Python's string-literal parser silently "
            "consumes an unescaped backslash before a recognized escape "
            "letter (\\a, \\b, \\f, \\v, ...), corrupting a LaTeX-style "
            "command before this code ever sees it. Use the Unicode symbol "
            "directly instead (e.g. ∠, ⊥, ∥, °, √, ≤, ≥, →, α, θ, π) rather "
            f"than a LaTeX command, or escape the backslash as '\\\\{macro}' "
            "if you need the literal command text to appear as-is."
        )

    return _CONTROL_CHAR_RE.sub(_replace, text)


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
    return Point(id=pid, _builder=builder, _x=float(x), _y=float(y))


@dataclass(frozen=True)
class Point:
    id: str
    _builder: "object" = field(repr=False, compare=False)  # type is Builder; avoid a
                                                             # circular import at module load
    # Known only for point(x, y) literals (and points derived from them via
    # arithmetic) — never for constructed points (point_on, rotate_point,
    # dilate_point, reflect_point, ...), whose coordinates aren't resolved
    # until later via SymPy. Private: the public x/y properties below raise a
    # clear error on access instead of silently handing back None — a model
    # reading `G.x` directly (not through +/-/*) used to get a bare None,
    # then a contextless TypeError from whatever it did next. Internal code
    # that needs to check "is this known yet, skip if not" (validation
    # guards, coincidence checks) reads these private fields directly.
    _x: float | None = None
    _y: float | None = None

    def _known(self, other: "Point | None" = None) -> None:
        for pt in (self, other):
            if pt is not None and (pt._x is None or pt._y is None):
                raise ValueError(
                    f"Point {pt.id!r} has no known coordinates (only point(x, y) "
                    "literals — and points derived from them via +, -, * — carry "
                    "coordinates back to the script; a point from point_on()/"
                    "rotate_point()/dilate_point()/reflect_point()/etc. does not, "
                    "since its position isn't resolved until later). Use "
                    "dilate_point()/rotate_point()/reflect_point() instead of "
                    "arithmetic when either point's coordinates aren't known."
                )

    @property
    def x(self) -> float:
        """The x-coordinate. Raises for a constructed point (point_on()/
        rotate_point()/dilate_point()/reflect_point()/etc.) whose position
        isn't resolved until later — only point(x, y) literals (and points
        derived from them via +, -, *) have a known x/y at script time."""
        self._known()
        return self._x

    @property
    def y(self) -> float:
        """The y-coordinate. Same contract as x — raises for a constructed
        point whose position isn't resolved until later."""
        self._known()
        return self._y

    def __add__(self, other: "Point") -> "Point":
        self._known(other)
        return _record_literal_point(self._builder, self._x + other._x, self._y + other._y)

    def __sub__(self, other: "Point") -> "Point":
        self._known(other)
        return _record_literal_point(self._builder, self._x - other._x, self._y - other._y)

    def __mul__(self, scalar: float) -> "Point":
        self._known()
        return _record_literal_point(self._builder, self._x * scalar, self._y * scalar)

    __rmul__ = __mul__

    def label(self, text: str, pos: str = "auto", show_coords: bool = False) -> None:
        """pos must be exactly "auto", "above", "below", "left", "right", "above left", "above right", "below left", or "below right" — e.g. p.label("A").

        No other spelling is accepted: not "top"/"bottom"/"upper"/"center",
        not a hyphenated form ("above-left"), not a compass abbreviation
        ("nw"/"sw")."""
        from geometry_diagrams.ir.ir import LabelPoint

        text = _sanitize_label_text(text, "label")
        self._builder._add_render(
            LabelPoint(p=self.id, text=text, pos=pos, show_coords=show_coords)
        )


@dataclass(frozen=True)
class Line:
    id: str


@dataclass(frozen=True)
class Ray:
    id: str


@dataclass(frozen=True)
class Arc:
    id: str


@dataclass(frozen=True)
class Sector:
    id: str


@dataclass(frozen=True)
class Segment:
    id: str
    _builder: "object" = field(repr=False, compare=False)

    def label(self, text: str, pos: "float | None" = None) -> None:
        """Label this segment with text, e.g. seg.label("r")."""
        from geometry_diagrams.ir.ir import LabelSegment

        text = _sanitize_label_text(text, "label")
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
class Ellipse:
    id: str
    center: Point
    _hradius_thunk: "object" = field(repr=False, compare=False)  # Callable[[], float]
    _vradius_thunk: "object" = field(repr=False, compare=False)  # Callable[[], float]

    @property
    def hradius(self) -> float:
        return self._hradius_thunk()

    @property
    def vradius(self) -> float:
        return self._vradius_thunk()


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
class Polyline:
    id: str
    vertices: tuple[Point, ...]
    _builder: "object" = field(repr=False, compare=False)


@dataclass(frozen=True)
class AngleRef:
    a: Point
    o: Point
    b: Point
    _builder: "object" = field(repr=False, compare=False)

    def label(self, text: str, pos: "float | None" = None) -> None:
        """Label this angle with text, e.g. ref.label("theta")."""
        from geometry_diagrams.ir.ir import AnglePoints, LabelAngle

        text = _sanitize_label_text(text, "label")
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


@dataclass(frozen=True)
class PerpendicularBisectorLine:
    id: str
    midpoint: Point
    line: Line

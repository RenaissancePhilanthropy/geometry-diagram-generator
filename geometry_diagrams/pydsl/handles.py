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
# control byte back to the letter that produced it. Used only to attempt
# reconstruction of a corrupted LaTeX macro name; see _UNSAFE_CONTROL_CHARS
# below for the full set of bytes this function rejects.
_CONTROL_CHAR_TO_ESCAPE_LETTER = {
    "\a": "a",  # BEL, 0x07
    "\b": "b",  # BS,  0x08
    "\f": "f",  # FF,  0x0C
    "\v": "v",  # VT,  0x0B
}

# The full set of bytes this function treats as illegitimate in label text.
# Broader than _CONTROL_CHAR_TO_ESCAPE_LETTER: empirically (2026-08-07,
# replaying google.gemma-4-31b's curriculum-eval failure scripts), most
# control bytes reaching this code are NOT the four Python-escape letters —
# they're raw control bytes (0x01, 0x02, 0x03, 0x0f, 0x1a, 0x1b, 0x1d, ...)
# the model emitted directly, apparently mangled attempts at a degree sign
# or ANSI styling, with no backslash-letter to reconstruct. \t/\n/\r are
# excluded since they could plausibly be real whitespace.
_UNSAFE_CONTROL_CHARS = "".join(
    chr(c) for c in range(0x20) if chr(c) not in "\t\n\r"
) + "\x7f"
_CONTROL_CHAR_RE = re.compile("[" + re.escape(_UNSAFE_CONTROL_CHARS) + "]" + r"[A-Za-z]*")


def _sanitize_label_text(text: str, fn_name: str) -> str:
    """Reject (or, where possible, repair) non-printable control bytes in
    label text before they reach the renderer, where they produce a bare
    "SVG is not valid XML" failure with no indication of the actual cause.

    Two distinct corruption sources produce these bytes, both confirmed via
    real eval failures: (1) a script that writes a LaTeX-style command like
    "\\angle ABD" in a normal (non-raw) Python string literal has the
    backslash silently consumed by Python's own parser as an escape
    sequence before this code ever sees the text — "\\angle" (backslash +
    "a" + "ngle") becomes a literal BEL control character followed by
    "ngle". (2) some models emit an arbitrary raw control byte directly
    (not from a recognized Python escape letter), with no reconstructible
    macro name at all.

    For (1), putting the control character's escape letter back and
    matching the result against geometry_diagrams.ir.to_svg's own
    _LATEX_UNICODE table (the same substitution to_svg.py would have made
    had the model wrapped it in $...$) silently repairs it to the correct
    Unicode symbol. Everything else raises a clear error rather than let a
    mystery control character reach the renderer."""
    from geometry_diagrams.ir.to_svg import _LATEX_UNICODE

    def _replace(match: "re.Match") -> str:
        raw = match.group(0)
        letter = _CONTROL_CHAR_TO_ESCAPE_LETTER.get(raw[0])
        if letter is not None:
            macro = letter + raw[1:]
            symbol = _LATEX_UNICODE.get(macro)
            if symbol is not None:
                return symbol
            hint = (
                "Python's string-literal parser silently consumes an "
                "unescaped backslash before a recognized escape letter "
                "(\\a, \\b, \\f, \\v, ...), corrupting a LaTeX-style "
                f"command before this code ever sees it — did you mean "
                f"'\\{macro}'? Escape the backslash as '\\\\{macro}' if so."
            )
        else:
            hint = (
                "this isn't a Python string-escape letter, so no LaTeX "
                "command can be reconstructed from it — remove it or "
                "replace it with the symbol you intended."
            )
        raise ValueError(
            f"{fn_name}(): text contains a non-printable control character "
            f"(byte {ord(raw[0]):#04x}). {hint} Use the Unicode symbol "
            "directly instead of a LaTeX command (e.g. ∠, ⊥, ∥, °, √, ≤, "
            "≥, →, α, θ, π)."
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
    # Known directly for point(x, y) literals (and points derived from
    # them via +, -, *) — set at construction time. For every other
    # constructed point (point_on(), rotate_point(), intersection(),
    # etc.), _x/_y stay None and the public x/y properties below resolve
    # them on demand via the builder (see Builder._resolve_point), so
    # every point works the same way from the script's point of view.
    _x: float | None = None
    _y: float | None = None

    @property
    def x(self) -> float:
        """The x-coordinate. Available for any point once its position is
        fully determined by earlier script statements — point(x, y)
        literals, arithmetic derived from them, and constructed points
        (point_on(), rotate_point(), intersection(), etc.) alike. Raises
        only if the position genuinely can't be determined (e.g. a real
        geometric error in an earlier construction)."""
        if self._x is not None:
            return self._x
        return self._builder._resolve_point(self.id)[0]

    @property
    def y(self) -> float:
        """The y-coordinate. Same contract as x."""
        if self._y is not None:
            return self._y
        return self._builder._resolve_point(self.id)[1]

    def __add__(self, other: "Point") -> "Point":
        return _record_literal_point(self._builder, self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        return _record_literal_point(self._builder, self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Point":
        return _record_literal_point(self._builder, self.x * scalar, self.y * scalar)

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
    _from_derived_center: bool = field(default=False, repr=False, compare=False)

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

# pydsl Derived Constructions — Design

## Problem

pydsl scripts cannot construct several extremely common derived
geometry objects at all: the intersection of two lines/circles, a
standalone perpendicular or parallel line through a point, a
perpendicular bisector, an angle bisector, a triangle's centroid, the
foot of a perpendicular, or a tangent line to a circle.

This is not a missing IR feature. `geometry_diagrams/ir/ir.py` already
defines `PointIntersection`, `LinePerpendicularThrough`,
`LineParallelThrough`, `LineAngleBisector`, `PointTriangleCenter`
(`which="centroid"` is already a valid literal, alongside
`circumcenter`/`incenter`/`orthocenter`), `PointFoot`, and `LineTangent`.
Two of pydsl's existing functions already use some of these internally —
`altitude()` already builds a `LinePerpendicularThrough` and a
`PointFoot` — just never expose them as their own standalone pydsl
calls. The recipe DSL (`geometry_diagrams/recipe/dsl.py`,
`geometry_diagrams/recipe/lower.py`) already exposes all eight as ops,
confirming both the IR support and the exact composition needed for the
two that aren't 1:1 IR wraps.

## Non-goals

- No IR or renderer changes — every field/kind used here already exists
  and is already compiled by `to_sympy.py`.
- No exposure of the full `PickRule` union (~12 discriminated variants:
  `PickIndex`, `PickOnObject`, `PickSameSide`, `PickInsideTriangle`,
  `PickBetween`, `PickBeyond`, `PickInterior`, `PickExterior`,
  `PickOppositeSide`, `PickChain`, plus the two used here). Only
  `PickClosestTo` and `PickUpperOfLine`/`PickLowerOfLine` are exposed,
  via plain `near`/`side_of`+`side` parameters — see API surface.
- No auto-drawing. `perpendicular_bisector()`'s DSL equivalent
  (`PerpendicularBisectorOp`) auto-draws a base segment between its two
  input points if one doesn't already exist; pydsl's version does not —
  consistent with pydsl's existing rule (already stated in
  `instructions_python_full.py`) that nothing renders unless the script
  calls `draw()`/`draw_points()` explicitly.

## API surface

All eight are new top-level functions in `api.py`, following the
existing pattern: call `get_builder()`, record via `builder._add(...)`,
return a handle.

### Direct 1:1 wraps

```python
def perpendicular_through(point: Point, line) -> Line:
    """The line through `point`, perpendicular to `line` (a Line/Segment/Ray)."""

def parallel_through(point: Point, line) -> Line:
    """The line through `point`, parallel to `line` (a Line/Segment/Ray)."""

def angle_bisector(vertex: Point, toward1: Point, toward2: Point) -> Line:
    """The line bisecting the angle at `vertex`, between rays toward toward1/toward2."""

def centroid(t: Triangle) -> Point:
    """The centroid of triangle `t`."""

def foot_of_perpendicular(point: Point, line) -> Point:
    """The foot of the perpendicular dropped from `point` onto `line`
    (a Line/Segment/Ray) — always projects onto the infinite line."""
```

Each records exactly one `DefStmt` (`LinePerpendicularThrough`,
`LineParallelThrough`, `LineAngleBisector`, `PointTriangleCenter(which=
"centroid")`, `PointFoot` respectively) and returns the corresponding
handle (`Line`/`Line`/`Line`/`Point`/`Point`) with no new handle types
needed for these five.

### `perpendicular_bisector(p, q) -> PerpendicularBisectorLine`

Composes three hidden defs, mirroring exactly how `altitude()` already
composes multiple hidden defs for one pydsl call:

```python
def perpendicular_bisector(p: Point, q: Point) -> "PerpendicularBisectorLine":
    """The perpendicular bisector of segment p-q. Does not draw the
    segment p-q itself — draw() it separately if you want it visible."""
    builder = get_builder()
    base_id = builder._fresh_hidden_id("bisector_base")
    builder._add(LineThrough(id=base_id, p=p.id, q=q.id))
    mid_id = builder._fresh_hidden_id("bisector_mid")
    builder._add(PointMidpoint(id=mid_id, p=p.id, q=q.id))
    line_id = builder._fresh_hidden_id("bisector")
    builder._add(LinePerpendicularThrough(id=line_id, through=mid_id, to_line=base_id))
    return PerpendicularBisectorLine(id=line_id, midpoint=Point(id=mid_id, _builder=builder))
```

New handle in `handles.py`, mirroring `Median`'s exact shape:

```python
@dataclass(frozen=True)
class PerpendicularBisectorLine:
    id: str
    midpoint: Point
```

### `intersection(obj1, obj2, near=None, side_of=None, side=None) -> Point`

```python
def intersection(
    obj1, obj2,
    near: "Point | None" = None,
    side_of: "tuple[Point, Point] | None" = None,
    side: "str | None" = None,
) -> Point:
    """The intersection point of obj1 and obj2 (lines/segments/rays/circles).

    Disambiguate when there's more than one candidate (e.g. a line crossing
    a circle twice) with EITHER:
    - near=P — the candidate closest to P, or
    - side_of=(A, B), side="left"|"right" — the candidate on that side of
      the directed line from A to B (walking from A toward B).
    Give at most one of these. With neither, and more than one candidate
    exists, an automatic (documented-as-arbitrary) heuristic picks one —
    prefer giving near/side_of+side whenever the choice matters."""
    from geometry_diagrams.ir.ir import PickClosestTo, PickLowerOfLine, PickUpperOfLine, PointIntersection

    has_near = near is not None
    has_side = side_of is not None or side is not None
    if has_near and has_side:
        raise ValueError("intersection(): give at most one of 'near' or 'side_of'+'side', not both")
    if (side_of is not None) != (side is not None):
        raise ValueError("intersection(): 'side_of' and 'side' must be given together")
    if side is not None and side not in ("left", "right"):
        raise ValueError(f"intersection(): side must be 'left' or 'right', got {side!r}")

    pick = None
    if has_near:
        pick = PickClosestTo(p=near.id)
    elif has_side:
        a, b = side_of
        pick = PickUpperOfLine(a=a.id, b=b.id) if side == "left" else PickLowerOfLine(a=a.id, b=b.id)

    builder = get_builder()
    pid = builder._fresh_hidden_id("isect")
    builder._add(PointIntersection(id=pid, obj1=obj1.id, obj2=obj2.id, pick=pick))
    return Point(id=pid, _builder=builder)
```

`"left"`/`"right"` map to `PickUpperOfLine`/`PickLowerOfLine` respectively
— confirmed against `to_sympy.py`'s pick application: `PickUpperOfLine`
selects the candidate with a positive cross product relative to the
directed line A→B, which is the standard-orientation left side of that
direction.

**Documented behavioral asymmetry with `tangent_line` below** (verified
by reading `to_sympy.py`'s `_apply_pick`/`PointIntersection` handling
directly): with no pick given and multiple intersection candidates,
`PointIntersection` does **not** raise — it falls back to an in-canvas /
closest-to-centroid heuristic that the IR's own comment already documents
as "arbitrary and may not match the LLM's intent." `intersection()`
does not change or hide this; scripts that care about which candidate
they get should always pass `near` or `side_of`+`side`.

### `tangent_line(circle, at=None, from_point=None, near=None, side_of=None, side=None) -> Line`

```python
def tangent_line(
    circle: Circle,
    at: "Point | None" = None,
    from_point: "Point | None" = None,
    near: "Point | None" = None,
    side_of: "tuple[Point, Point] | None" = None,
    side: "str | None" = None,
) -> Line:
    """The tangent line to `circle`. Exactly one of:
    - at=P — P is a point already ON the circle; the tangent there (always
      unambiguous, near/side_of/side are not used).
    - from_point=P — P is external to the circle; there are 0, 1, or 2
      tangent lines from an external point. Disambiguate a 2-tangent case
      with near=Q (closest touch point to Q) or side_of=(A,B), side=
      "left"|"right" (same convention as intersection()). With neither,
      and 2 tangent lines exist, this raises ValueError — unlike
      intersection(), there is no arbitrary-heuristic fallback here."""
    from geometry_diagrams.ir.ir import LinePerpendicularThrough, LineThrough, LineTangent, PickClosestTo, PickLowerOfLine, PickUpperOfLine

    if (at is None) == (from_point is None):
        raise ValueError("tangent_line() requires exactly one of 'at' or 'from_point'")

    builder = get_builder()
    if at is not None:
        radius_id = builder._fresh_hidden_id("tangent_radius")
        builder._add(LineThrough(id=radius_id, p=circle.center.id, q=at.id))
        line_id = builder._fresh_hidden_id("tangent")
        builder._add(LinePerpendicularThrough(id=line_id, through=at.id, to_line=radius_id))
        return Line(id=line_id)

    has_near = near is not None
    has_side = side_of is not None or side is not None
    if has_near and has_side:
        raise ValueError("tangent_line(): give at most one of 'near' or 'side_of'+'side', not both")
    if (side_of is not None) != (side is not None):
        raise ValueError("tangent_line(): 'side_of' and 'side' must be given together")
    if side is not None and side not in ("left", "right"):
        raise ValueError(f"tangent_line(): side must be 'left' or 'right', got {side!r}")

    pick = None
    if has_near:
        pick = PickClosestTo(p=near.id)
    elif has_side:
        a, b = side_of
        pick = PickUpperOfLine(a=a.id, b=b.id) if side == "left" else PickLowerOfLine(a=a.id, b=b.id)

    line_id = builder._fresh_hidden_id("tangent")
    builder._add(LineTangent(id=line_id, point=from_point.id, circle=circle.id, pick=pick))
    return Line(id=line_id)
```

The `at=` branch needs the circle's center — pydsl's `Circle` handle
already carries `.center` as a `Point` directly (unlike the DSL lowerer,
which has to look center ids up in a separate `self._circle_centers`
dict because DSL ops only carry string ids) — so this composition is
actually simpler in pydsl than in the DSL lowerer it's modeled on.

The `(at is None) == (from_point is None)` exactly-one-of check follows
the same immediate-validation pattern already established by
`label_text()`.

## Data flow

All eight functions, plus the new `PerpendicularBisectorLine` handle,
must be added to `geometry_diagrams/pydsl/__init__.py`'s import line and
`__all__` — both the stub generator and the sandbox's tool-injection key
off `__all__`.

`stub.py` needs no changes for the six plain functions. For
`PerpendicularBisectorLine`, add its name to `stub.py`'s
`_HANDLE_CLASS_NAMES` set (alongside `Median`/`Altitude`) so its
`.midpoint` field is introspected into the prompt the same way
`Median.midpoint` already is.

One new Rules bullet in `instructions_python_full.py`, introducing all
eight and demonstrating the `near`/`side_of`+`side` pattern once (so a
model sees a concrete worked example rather than inferring the parameter
shapes from signatures alone).

## Testing

New file `tests/test_pydsl_derived_constructions.py`, TDD, covering:

- Each of the five direct 1:1 wraps: correct `DefStmt` kind and fields
  recorded, correct handle type returned.
- `perpendicular_bisector(p, q)`: all three hidden defs present in the
  right dependency order (`LineThrough` → `PointMidpoint` →
  `LinePerpendicularThrough`); `.midpoint` accessor returns a `Point`
  whose id matches the recorded `PointMidpoint`; the base segment is
  NOT auto-drawn (`Draw`/`DrawPoints` absent from `ir.render` unless the
  script calls `draw()` itself) — this is the explicit non-goal
  regression guard.
- `intersection()`: no-pick case records `pick=None`; `near=P` records
  `PickClosestTo(p=P.id)`; `side_of=(A,B), side="left"` records
  `PickUpperOfLine(a=A.id, b=B.id)`; `side="right"` records
  `PickLowerOfLine`; giving both `near` and `side_of`+`side` raises
  `ValueError`; giving `side_of` without `side` (and vice versa) raises
  `ValueError`; an invalid `side` string raises `ValueError`.
- `tangent_line()`: `at=` records the two composed defs and returns a
  `Line`; `from_point=` with no pick records `pick=None`; the same
  `near`/`side_of`+`side` validation tests as `intersection()`; giving
  both `at` and `from_point` (or neither) raises `ValueError`.
- A sandbox-path test (`geometry_diagrams.pydsl.sandbox.run_script`)
  exercising `intersection()`, `perpendicular_through()`, and
  `perpendicular_bisector()` together through the real sandbox —
  matching the precedent set by the labeling and canvas plans.
- One SVG/numeric end-to-end test: build two non-parallel lines with
  known equations, take their `intersection()`, `compile_defs()`, and
  assert the resolved point's coordinates match the hand-computed
  intersection (e.g. two lines through literal points whose crossing
  point is easy to compute by hand) — proving the pydsl call reaches
  correct, not just present, geometry.

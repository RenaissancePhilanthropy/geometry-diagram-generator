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
Three of pydsl's existing functions already use some of these
internally — `altitude()` already builds a `LinePerpendicularThrough`
and a `PointFoot`; `circumcircle()`/`incircle()` both already build a
`PointTriangleCenter` — just never expose them as their own standalone
pydsl calls. The recipe DSL (`geometry_diagrams/recipe/dsl.py`,
`geometry_diagrams/recipe/lower.py`) already exposes all eight as ops,
confirming both the IR support and the exact composition needed for the
two that aren't 1:1 IR wraps.

## Non-goals

- No IR schema or renderer changes — every `DefStmt`/`PickRule` kind used
  here already exists in `ir.py` and is already rendered by
  `to_tikz.py`/`to_svg.py`. **One narrow, explicit exception**: fixing
  `to_sympy.py`'s `LineTangent` pick handling (see `tangent_line()`
  below) — this is completing an existing-but-incomplete compiler match
  arm, not adding a new IR concept, and is the same kind of small
  in-scope exception the labeling plan made for its pre-existing sandbox
  bugfix.
- No exposure of the full `PickRule` union (13 discriminated variants:
  `PickIndex`, `PickOnObject`, `PickClosestTo`, `PickSameSide`,
  `PickInsideTriangle`, `PickBetween`, `PickBeyond`, `PickInterior`,
  `PickExterior`, `PickOppositeSide`, `PickUpperOfLine`,
  `PickLowerOfLine`, `PickChain`). Only `PickClosestTo` and
  `PickUpperOfLine`/`PickLowerOfLine` (three of the thirteen) are
  exposed, via plain `near`/`side_of`+`side` parameters — see API
  surface.
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
    builder = get_builder()
    line_id = builder._fresh_hidden_id("perp")
    builder._add(LinePerpendicularThrough(id=line_id, through=point.id, to_line=line.id))
    return Line(id=line_id)

def parallel_through(point: Point, line) -> Line:
    """The line through `point`, parallel to `line` (a Line/Segment/Ray)."""
    builder = get_builder()
    line_id = builder._fresh_hidden_id("parallel")
    builder._add(LineParallelThrough(id=line_id, through=point.id, to_line=line.id))
    return Line(id=line_id)

def angle_bisector(vertex: Point, toward1: Point, toward2: Point) -> Line:
    """The line bisecting the angle at `vertex`, between rays toward toward1/toward2."""
    builder = get_builder()
    line_id = builder._fresh_hidden_id("bisector")
    # toward1 -> a, toward2 -> b: matches lower.py's ray1_toward->a, ray2_toward->b (lower.py:255)
    builder._add(LineAngleBisector(id=line_id, a=toward1.id, vertex=vertex.id, b=toward2.id))
    return Line(id=line_id)

def centroid(t: Triangle) -> Point:
    """The centroid of triangle `t`."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("centroid")
    builder._add(PointTriangleCenter(id=pid, tri=t.id, which="centroid"))
    return Point(id=pid, _builder=builder)

def foot_of_perpendicular(point: Point, line) -> Point:
    """The foot of the perpendicular dropped from `point` onto `line`
    (a Line/Segment/Ray) — always projects onto the infinite line."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("foot")
    builder._add(PointFoot(id=pid, source=point.id, onto=line.id))
    return Point(id=pid, _builder=builder)
```

Each records exactly one `DefStmt` (`LinePerpendicularThrough`,
`LineParallelThrough`, `LineAngleBisector`, `PointTriangleCenter(which=
"centroid")`, `PointFoot` respectively) and returns the corresponding
handle (`Line`/`Line`/`Line`/`Point`/`Point`) with no new handle types
needed for these five. `centroid()`/`foot_of_perpendicular()` pass
`_builder=builder` to their returned `Point`, matching every other
Point-returning pydsl function since the labeling plan's fix.

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
— confirmed empirically (built A=(0,0), B=(4,0), and both candidate
points, and checked which pick selected which): `PickUpperOfLine` selects
the candidate with a positive cross product `(B-A) × (P-A)`, which is the
standard-orientation left side when walking from A toward B. Reversing
the direction (B→A) flips which physical point counts as "left" — the
convention is relative to the direction given, not absolute.

**Documented behavioral asymmetry with `tangent_line` below** (verified
by reading `to_sympy.py`'s `_apply_pick` directly, lines 823-850, and
confirmed by actually compiling an ambiguous case): with no pick given
and multiple intersection candidates, `PointIntersection` does **not**
raise — it falls back to an in-canvas / closest-to-centroid heuristic
that `_apply_pick`'s own comment documents as "arbitrary and may not
match the LLM's intent." `intersection()` does not change or hide this;
scripts that care about which candidate they get should always pass
`near` or `side_of`+`side`.

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
      unambiguous — near/side_of/side are ignored if also given, silently,
      matching the DSL lowerer's own at= branch, which has no equivalent
      validation either).
    - from_point=P — P is external to the circle; there are 0, 1, or 2
      tangent lines from an external point. Disambiguate a 2-tangent case
      with near=Q (closest touch point to Q) or side_of=(A,B), side=
      "left"|"right" (same convention as intersection()). With neither,
      and 2 tangent lines exist, unlike intersection() there is no
      arbitrary-heuristic fallback — compilation fails later, inside
      compile_defs(), with geometry_diagrams.ir.errors.PickError (not a
      ValueError, and not raised by this function itself — the tangent
      count isn't known until coordinates resolve)."""
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

**Required `to_sympy.py` fix (the one exception to the no-IR-changes
non-goal):** confirmed by reading `to_sympy.py`'s `LineTangent` handling
directly (its `match pick:` block) and by actually compiling a
`from_point=` script with `PickClosestTo` — the match arm only handles
`PickIndex` and `PickUpperOfLine`/`PickLowerOfLine`; every other pick
kind, including `PickClosestTo`, falls through to `case _: return
tangents[0]` and is **silently discarded**, always returning SymPy's
arbitrary first tangent regardless of what `near=` asked for. Add a
`PickClosestTo` arm, following the same shape as the existing
`PickUpperOfLine`/`PickLowerOfLine` arm (compute each tangent's touch
point via `t_line.intersection(circle)`, then pick the tangent whose
touch point is closest to `_resolve(sym, pick.p, def_id=did)`; raise
`PickError` if no tangents exist, which can't happen here since the
earlier `if not tangents` check already guards it, but keep the same
`PickError` type for consistency with the rest of this match). This is
completing an existing match arm's coverage, not introducing a new
`PickRule` variant or a new IR concept.

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
- `PerpendicularBisectorLine` (and its `.midpoint: Point` field) actually
  appear in `generate_stub()`'s output — cheap, matches the existing
  pattern in `test_pydsl_stub.py` for `Median`/`Altitude`.
- A sandbox-path test (`geometry_diagrams.pydsl.sandbox.run_script`)
  exercising `intersection()`, `perpendicular_through()`, and
  `perpendicular_bisector()` together through the real sandbox —
  matching the precedent set by the labeling and canvas plans. Pass at
  least one disambiguation kwarg (e.g. `near=`) by keyword in this script,
  not just positionally, so the test also exercises kwargs actually
  flowing through smolagents' tool-call wrapping in the sandbox.
- Compile-level tests for `tangent_line()` (record-level tests alone
  aren't enough here — this is exactly the gap that let the missing
  `PickClosestTo` case go unnoticed): build a circle and an external
  point with two real tangent lines, then (a) with no pick, assert
  `compile_defs()` raises `PickError` (pins the documented asymmetry with
  `intersection()`); (b) with `near=Q`, assert the resolved tangent line's
  touch point is actually the geometrically closer one to `Q`, not just
  that a `PickClosestTo` was recorded — this test would fail before the
  `to_sympy.py` fix above and pass after, which is what proves the fix
  landed correctly, not just that some case was added.
- Extend the `side_of`/`side` tests similarly to compile-level, not just
  record-level: a line crossing a circle at two points, `side="left"` vs
  `side="right"`, each resolved via `compile_defs()` and asserted against
  the hand-computed left/right point — the record-level tests alone never
  prove "left" really means left once coordinates resolve.
- One SVG/numeric end-to-end test: build two non-parallel lines with
  known equations, take their `intersection()`, `compile_defs()`, and
  assert the resolved point's coordinates match the hand-computed
  intersection (e.g. two lines through literal points whose crossing
  point is easy to compute by hand) — proving the pydsl call reaches
  correct, not just present, geometry.

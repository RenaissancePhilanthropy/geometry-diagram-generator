# pydsl Shape Primitives — Design

## Problem

pydsl scripts can't construct a ray (only bounded segments and infinite
lines), an ellipse, a regular polygon, a rectangle, or a polygon built from
a sequence of side-lengths-and-turns. The recipe DSL has ops covering most
of this ground (`RayOp`, `EllipseOp`, `RegularPolygonOp`, `RectangleOp`,
`PolygonFromSidesOp`, `PolygonFromAnglesAndSidesOp`), but this plan is
explicitly **not** a port of that surface — the DSL's shape is dictated by
being pure declarative JSON (a model fills in a spec object; nothing there
can loop or compute), and several of its choices exist only to work around
that constraint, not because they're good design. Where pydsl — real
Python — can do better, it should.

## What's a straight IR wrap, and what needed rethinking

- `ray(a, b)` → `ir.Ray(a, b)`, 1:1, no design question.
- `ellipse(...)` → `ir.EllipseCenterAxes`/`ir.EllipseBBox`, 1:1 for two of
  the DSL's four input forms — see API surface for which two, and why the
  other two are dropped.
- `regular_polygon(...)` → **no IR wrap at all**. Confirmed by reading
  `recipe/lower.py`'s `_lower_regular_polygon`: it computes `cos`/`sin`
  coordinates directly into `PointFixed` defs, the same way pydsl's
  `point()` already does. Porting this is just copying a small trig loop.
- `rectangle(...)` — the DSL's version calls `recipe/solve.py`'s
  `solve_rectangle`, a real constraint solver, because the DSL lets a
  script specify a *partial* set of side lengths and infers the rest. But
  a rectangle only has 2 real shape degrees of freedom (width, height) —
  always fully determined, never under/over-constrained the way an
  arbitrary polygon's side list can be. pydsl's version takes width and
  height directly — no solver needed regardless of what the DSL does.
- `polygon_from_sides`/`polygon_from_angles_and_sides` — **not ported**.
  Investigated in depth (see the turtle/walk section below): the
  angles-and-sides op is already internally a turtle walk in
  `recipe/solve.py`'s `solve_polygon_from_angles_and_sides` (heading
  accumulated via `+=`, closure checked against a tolerance) — the DSL
  didn't need to solve anything there either. What it *does* have is
  JSON-forced arity gymnastics (accepting either V or V−1 side
  lengths/angles, inferring whichever is missing, `base`/`ref_point` mode
  switches) that exist only because a declarative spec object can't loop.
  pydsl replaces both ops with one primitive, `walk()`, plus the existing
  `polygon()` — see below.
- `circle_through_3(a, b, c)` — investigated and **dropped**.
  `recipe/lower.py`'s `_lower_circle_through_3` doesn't even use the IR's
  own `ir.CircleThrough3` class — it builds a hidden `Triangle` +
  `PointTriangleCenter(which="circumcenter")` + `CircleCenterPoint`
  instead, which is exactly what pydsl's existing `circumcircle(triangle(a,
  b, c))` already produces. A dedicated function would only save naming a
  throwaway `Triangle` handle. Left out of this plan; revisit if a real
  use case wants the ergonomic shortcut.

## The turtle/walk primitive

`polygon_from_sides`/`polygon_from_angles_and_sides` are replaced by a
single stateless function, `walk(from_point, heading, distance) -> Point`,
used in a script's own loop together with the existing `polygon(*pts)`.

**Why stateless, not a stateful turtle object** (`t.forward(4); t.turn(90);
... t.close()`): a `.close()` method is a trap either way it's built — it
must choose between silently connecting a path that didn't actually close
(masking an inconsistent spec, exactly the failure mode the DSL solver's
0.5°-tolerance closure check exists to catch) or re-implementing that same
tolerance check inside a new stateful object. Neither is needed if the
primitive never promises closure: with `walk()`, a script computes V−1
points via `heading += turn_angle` in its own loop, collects them into a
list, and hands that list straight to `polygon(*pts)` — which already
closes any vertex list by definition. There is no dangling endpoint to
validate, because nothing claimed one would exist. A stateful turtle object
would also reintroduce the DSL's real problem in a new shape: call-ordering
rules and closure semantics the model has to hold in its head instead of in
its own script, where the retry loop can see and react to a raised
`ValueError`'s message.

**Convention: radians, CCW from the +x axis** — matching `rotate_point()`'s
existing convention (`api.py`: "angle radians (positive = counter-clockwise)"),
not the DSL's degrees. Consistency within pydsl matters more than matching
the DSL; a degrees-here/radians-there split within one API is a bug
factory. Scripts needing degrees call `math.radians(...)` themselves —
confirmed the sandbox actually permits `import math` (verified directly
against `sandbox.run_script`, not just read from smolagents' docs).

**Floating-point drift** over the handful of steps a real diagram uses (3–12
sides, occasionally more) is a non-issue at float64 precision — `solve.py`
itself accumulates heading via the same kind of repeated `+=` and it's
never been a problem there.

**Self-intersection**: `walk()` doesn't guard against a script producing a
bowtie/self-intersecting shape from a turn-sign mistake — hand-written
`point()` coordinates can do this today too, so it isn't a new risk this
primitive introduces, and guarding it here wouldn't guard it everywhere
else it's equally possible. Out of scope; if it becomes a real problem, the
right fix is a polygon-simplicity check in `ir/checks.py` benefiting every
construction path, not a `walk()`-specific one.

**The one turtle-specific mistake worth guarding**: walking one step too
many and passing the near-duplicate starting point back into `polygon()`.
This is unambiguous, not a style choice — but the current docstring
doesn't actually say so. `polygon()`'s existing docstring, "A closed
polygon over 3 or more existing points, in perimeter order," is ambiguous
between two readings: (a) the *result* is closed, and the vertex list you
pass might already include a closing repeat of the first point, versus
(b) `polygon()` *performs the closing itself* from an open vertex list,
and a closing repeat would be redundant. It means (b) — `PolygonDef` just
stores the given point ids, and closure is applied downstream (rendering
connects the last back to the first) — but a script author, and this new
guard's own justification, can't tell that from the text alone. Unlike
GeoJSON-style APIs, there is no supported convention here for repeating
the first point at the end to signal "close the loop"; doing so is always
redundant. This plan updates the docstring alongside adding the guard, so
the rule is stated rather than left for the error message to explain:

```python
def polygon(*vertices: Point) -> Polygon:
    """A polygon over 3 or more points, in perimeter order. The shape is
    closed automatically — the last point connects back to the first.
    Do not repeat the first point at the end; that produces a
    coincident-vertex error rather than a no-op."""
```

Because closure is unambiguous once stated this way, treating last≈first
as an error rather than a silent no-op is safe — no legitimate call is
being rejected.

`polygon()` gains a check for near-coincident *consecutive* vertices
(including last→first) when both have known coordinates. The error message
states the rule, not just this one symptom, so it reads the same way
whether the duplicate came from `walk()`, `point_on()`, or a typo:

```
polygon() vertices {id} and {id} are coincident. polygon() already closes
the shape automatically — do not repeat the first point as the last.
```

## Non-goals

- No IR or renderer changes for `ray`/`ellipse` (both existing `DefStmt`
  kinds, already rendered). `regular_polygon`/`rectangle`/`walk` need none
  either — pure arithmetic into existing `PointFixed`/`Polygon` defs.
- No `circle_through_3()` — see above.
- No ellipse foci/eccentricity forms — the DSL's own lowering for those
  (`EllipseFoci`/eccentricity math, confirmed by reading `to_sympy.py`
  lines 471+) is itself just precomputing a center and semi-axes before
  handing off to the same `spg.Ellipse(center, hr, vr)` call — a script
  that wants an ellipse from foci can do that arithmetic itself and call
  the center_axes form; no new primitive closes a real capability gap.
- No "star" variant of `regular_polygon()` — a script that wants one can
  reorder the returned vertices itself.
- No cyclic-polygon-from-side-lengths-only solve (`solve.py`'s
  `solve_polygon_from_sides`, which bisects for a circumradius) — not
  reasonable to expect a script to reimplement, and no turtle-style
  reformulation removes the actual unknown there (unlike
  angles-and-sides, side-lengths-alone genuinely underdetermines the
  shape). Out of scope for this plan.

## API surface

```python
def ray(a: Point, b: Point) -> Ray:
    """A ray starting at a, extending through and beyond b."""
```

New minimal handle in `handles.py`, mirroring `Line`'s shape exactly (no
`_builder` — no methods):

```python
@dataclass(frozen=True)
class Ray:
    id: str
```

```python
def ellipse(
    center: "Point | None" = None,
    hradius: "float | None" = None,
    vradius: "float | None" = None,
    corner1: "Point | None" = None,
    corner2: "Point | None" = None,
) -> "Ellipse":
    """An axis-aligned ellipse. Exactly one of:
    - center, hradius, vradius — center point and semi-axis lengths (both > 0).
    - corner1, corner2 — opposite corners of the bounding box.
    All three of the first group, or both of the second, must be given together."""
```

Validation (immediate, before any builder call — mirrors
`tangent_line()`'s exactly-one-of-a-group style, extended to
partial-group detection since each group here has more than one member):

```python
    center_axes_parts = [center is not None, hradius is not None, vradius is not None]
    bbox_parts = [corner1 is not None, corner2 is not None]
    has_center_axes = all(center_axes_parts)
    has_bbox = all(bbox_parts)
    if has_center_axes and has_bbox:
        raise ValueError("ellipse(): give exactly one of (center, hradius, vradius) or (corner1, corner2), not both")
    if any(center_axes_parts) and not has_center_axes:
        raise ValueError("ellipse(): center, hradius, and vradius must all be given together")
    if any(bbox_parts) and not has_bbox:
        raise ValueError("ellipse(): corner1 and corner2 must both be given together")
    if not has_center_axes and not has_bbox:
        raise ValueError("ellipse() requires either (center, hradius, vradius) or (corner1, corner2)")
```

For the `center_axes` form, also validate `hradius > 0` and `vradius > 0`
immediately (mirroring `to_sympy.py`'s own `EllipseCenterAxes` check —
raising here gives a script an immediate, clear error instead of a
downstream `compile_defs()` failure).

New `Ellipse` handle, mirroring `Circle`'s exact lazy-radius pattern (see
`circumcircle()`'s `_compute_radius`/`_radius_thunk` in `api.py`) — needed
because the `bbox` form's `hradius`/`vradius` aren't given directly, they're
derived from the two corners:

```python
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
```

For the `center_axes` form: `center` is the given `Point` directly; the
thunks just return the given `hradius`/`vradius` floats. For the `bbox`
form: `center` is derived via a hidden `PointMidpoint(corner1.id,
corner2.id)` (same composition pattern `perpendicular_bisector()` already
uses); the thunks compute half the absolute coordinate deltas from
`builder._coord_floats` (same pattern as `circumcircle()`'s radius thunk,
including its `NotImplementedError` fallback when either corner isn't a
concrete literal yet).

```python
def regular_polygon(center: Point, radius: float, n: int, start_angle: float = 0.0) -> Polygon:
    """A regular n-gon centered at `center` with circumradius `radius`.
    start_angle (radians) rotates the first vertex; n must be >= 3."""
```

Requires `center` to have known coordinates (reuses `Point._known()`, same
guard `walk()` uses below). Loops `i in range(n)`, computing
`angle = start_angle + i * 2*pi/n`, `x = center.x + radius*cos(angle)`, `y
= center.y + radius*sin(angle)` — the exact computation
`_lower_regular_polygon` already does, ported verbatim — recording one
`PointFixed` per vertex via the same helper `Point.__add__`'s
`_record_literal_point` uses internally, then a `Polygon` over all n
points.

```python
def rectangle(
    corner: Point,
    width: float,
    height: float,
    rotation: float = 0.0,
    pivot: str = "center",
) -> Polygon:
    """An axis-aligned-before-rotation rectangle: `corner` is one corner in
    the unrotated frame, extending by width/height. `rotation` (radians, CCW)
    then rotates all four corners around either the rectangle's own center
    (pivot="center", default — the shape spins in place) or around `corner`
    itself (pivot="corner"). pivot must be "center" or "corner"."""
```

Requires `corner` to have known coordinates. Computes the four unrotated
corners (`corner`, `corner+(width,0)`, `corner+(width,height)`,
`corner+(0,height)`), picks the rotation center per `pivot` (average of the
four corners, or `corner` itself), rotates each of the four points around
that center by `rotation` via plain trig (`x' = cx + (x-cx)*cos(r) -
(y-cy)*sin(r)`, `y' = cy + (x-cx)*sin(r) + (y-cy)*cos(r)`), records four
`PointFixed` defs, and returns a `Polygon` over them. `pivot` not in
`("center", "corner")` raises `ValueError` immediately.

```python
def walk(from_point: Point, heading: float, distance: float) -> Point:
    """A point `distance` away from from_point in direction `heading`
    (radians, counter-clockwise from the +x axis — same convention as
    rotate_point()). Use in a loop with your own running heading to build a
    polygon's vertices one side at a time, then pass the collected points to
    polygon(*pts):
        pts, h = [start], 0.0
        for side, turn in steps:
            pts.append(walk(pts[-1], h, side))
            h += turn
        poly = polygon(*pts)
    """
```

Requires `from_point` to have known coordinates. `x = from_point.x +
distance*cos(heading)`, `y = from_point.y + distance*sin(heading)`, records
one `PointFixed`, returns a `Point`.

**`polygon()`'s docstring and new guard** (in the existing function,
`api.py`): docstring updated to the text quoted above. After the existing
`len(vertices) < 3` check, for each consecutive pair (including
last→first, wrapping around) where both vertices have known coordinates,
raise `ValueError` if they're closer than a small epsilon (e.g. `1e-9`):

```python
raise ValueError(
    f"polygon() vertices {prev.id!r} and {cur.id!r} are coincident. "
    "polygon() already closes the shape automatically — do not repeat "
    "the first point as the last."
)
```

Vertices with unknown coordinates (e.g. from `point_on()`) are skipped by
this check, same as every other coordinate-dependent validation in this
file.

## Data flow

`ray`, `ellipse`, `regular_polygon`, `rectangle`, `walk` all registered in
`pydsl/__init__.py`'s import line and `__all__`. `Ray`/`Ellipse` handles
registered there too; `Ellipse` also added to `stub.py`'s
`_HANDLE_CLASS_NAMES` (mirroring the `PerpendicularBisectorLine` precedent)
so its `.center`/`.hradius`/`.vradius` surface in the generated stub —
`hradius`/`vradius` are properties, already handled by `stub.py`'s existing
property-introspection loop, no `stub.py` code changes needed beyond the
set membership. `Ray` needs no stub.py change (no fields, no properties).

One new Rules bullet in `instructions_python_full.py` introducing all five
functions plus the `walk()` + `polygon()` worked example from its own
docstring above (concrete code beats prose for this one).

## Testing

New file `tests/test_pydsl_shape_primitives.py`, TDD, covering:

- `ray()`: correct `Ray` def recorded, correct handle returned.
- `ellipse()`: both valid forms record correct fields; every
  partial/both/neither validation case raises `ValueError` immediately
  (mirroring `tangent_line()`'s validation test shape); non-positive
  `hradius`/`vradius` in the `center_axes` form raises immediately;
  `.center`/`.hradius`/`.vradius` resolve correctly for the `bbox` form via
  a compile-level test (literal corners, hand-computed center/semi-axes).
- `regular_polygon()`: vertex count matches `n`; compile-level test with a
  literal square (n=4) asserting hand-computed vertex coordinates.
- `rectangle()`: compile-level tests for both `pivot` values with a literal
  corner/width/height/rotation, asserting hand-computed corner coordinates
  (e.g. a 90° rotation has an exact, easy-to-verify answer); invalid
  `pivot` string raises immediately.
- `walk()`: compile-level test building a square via a `walk()` loop
  (4 steps, 90° turns) and asserting the result closes back near the start
  point and matches hand-computed intermediate vertices.
- `polygon()`'s new guard: a near-duplicate consecutive vertex (both
  literal) raises `ValueError`; a near-duplicate first/last vertex (the
  literal "walked one extra step" mistake) also raises; vertices with
  unknown coordinates don't trigger a false positive; the existing
  `test_pydsl_draw.py`/`test_pydsl_polygon.py` polygon tests must still
  pass unchanged (this guard must not be stricter than any existing valid
  test fixture).
- A sandbox-path test (`run_script`) building a small polygon via a
  `walk()` loop, proving the whole thing works through the real sandbox.

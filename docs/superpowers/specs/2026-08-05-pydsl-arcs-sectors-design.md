# pydsl Arcs, Sectors, and a Plain Circle Constructor — Design

## Problem

pydsl has no way to draw a partial circle (an arc), a pie-slice region (a
sector), or divide a circle into equal sectors (a pie chart) — despite full
IR and rendering support already existing for all three (`ArcCenterStartEnd`,
`SectorCenterStartEnd` in `geometry_diagrams/ir/ir.py`; both already handled
in `to_tikz.py` and `to_svg.py`). The recipe DSL has 1:1-mapped ops for the
first two (`ArcOp`, `SectorOp`) and a composed op for the third
(`RegularSectorsOp`, which lowers to N separate `SectorCenterStartEnd`
defs) — pydsl exposes none of it.

Investigating this surfaced an unrelated but blocking gap: pydsl also has no
plain `circle(center, radius)` constructor. The only way to get a `Circle`
handle today is `circumcircle(triangle(...))` or `incircle(triangle(...))`,
both of which require fabricating a triangle first. Since every function in
this cluster operates on a `Circle`, this is fixed here too rather than
worked around.

## Two real footguns, found via Fable review

**1. The compiler derives the arc's radius from `start` alone — but the
renderer can still corrupt the diagram via an off-circle `end`.**
`ArcCenterStartEnd`/`SectorCenterStartEnd` don't store a radius; `to_sympy.py`
computes it as `center.distance(start)`, and `end` is stored as a raw point
used only for direction at that layer. That much is accurate. But
`render_util.py::arc_params` — used by both `to_tikz.py` and `to_svg.py` —
sometimes swaps `start`/`end` to satisfy the requested `reflex` sweep
direction, and when it does, **the raw (possibly off-circle) `end`
coordinates become the new anchor point** fed straight into the rendered
path (confirmed directly in `to_tikz.py`'s `\draw (sx,sy) arc[...]`, which
anchors TikZ's own arc-center computation at `(sx,sy)`). So an off-circle
`end` can silently shift the *entire* rendered arc away from the intended
circle, exactly like an off-circle `start` — not just a direction-only
input as the compile-level view alone would suggest.

**2. `regular_sectors()`'s literal trig can misclassify a slice's sweep
by float noise at `n=2`.** `math.sin(math.pi)` in Python is
`1.2246e-16`, not exactly `0`. For `n=2`, each slice spans exactly the
180° minor/major tie-break boundary in `arc_params` (`ccw <= 180.0`);
that tiny residue can flip the classification, causing both "halves" of
the pie to render as the same semicircle while the other half stays
empty. The recipe DSL hit this exact issue and fixed it by rounding
spoke coordinates to 10 decimal places before recording them
(`recipe/lower.py`); this design adopts the same fix.

**The fix for both:** `arc()`/`sector()`'s guard validates **both**
`start` and `end` against the circle (not just `start`) — this directly
prevents the render-time corruption in issue 1, at the cost of being
slightly stricter than the compile-level math strictly requires (a
deliberate, documented trade: correctness over permissiveness). And
`regular_sectors()` rounds each computed boundary coordinate to 10
decimal places, matching `recipe/lower.py`'s established, already-proven
fix for the identical float-tie problem, rather than inventing a new one.

pydsl already has the right tool for building validated `start`/`end`
points: `point_on(circle, angle)` (existing function — `PointOnParam`'s
`t` is "interpreted as angle in radians by convention" for circles)
always returns a point exactly on the circle, symbolically. `arc()`/
`sector()` document this as the correct way to build both `start` and
`end`, and the guard catches the mistake directly for anyone who
constructs a point by hand instead: when `circle.center`'s coordinates
and `circle.radius` are both resolvable to concrete numbers, and a given
point's own coordinates are known, verify it's actually on the circle
before recording anything, raising `ValueError` otherwise. This mirrors
Cluster B's `polygon()` coincident-vertex guard — a specific,
previously-easy LLM mistake gets a clear compile-time-adjacent error
instead of a silently wrong diagram.

When a point's coordinates, or `circle.center`'s coordinates, or
`circle.radius`, can't be resolved to a concrete number yet, the check
against that point is skipped — same "validate only what's currently
knowable" policy every other coordinate-dependent check in `api.py`
already follows (e.g. `circumcircle(...).radius`'s `NotImplementedError`
fallback, `regular_polygon()`'s `center._known()`). Note this means the
guard provides no protection at all for `circumcircle()`/`incircle()`-derived
circles, whose center is never a literal coordinate (see Data flow) — for
those, `point_on(circle, angle)`'s documentation is the only safeguard.

## Non-goals

- No ellipse-arc / ellipse-sector variant — the IR has no such class
  (`ArcCenterStartEnd`/`SectorCenterStartEnd` are circle-only); out of
  scope until a real need for one surfaces.
- No angle-based `arc(circle, start_angle, end_angle)` alternate input
  form. Considered and rejected: `point_on(circle, angle)` already covers
  exactly this need in one extra call, and a script that already has
  points in hand (e.g. an intersection point known to lie on the circle)
  would have to convert them back to angles unnecessarily under an
  angles-only design. One consistent points-based signature, backed by
  the existing `point_on()` composition, covers both cases without
  doubling the API surface.
- No "star"/non-uniform variant of `regular_sectors()` (e.g. sectors with
  per-slice weights) — out of scope; a script wanting non-uniform slices
  can call `sector()` directly, in a loop, computing each slice's
  `start`/`end` angle itself via `point_on()`.
- No fill support. `to_tikz.py`/`to_svg.py` do support filling a `Sector`
  (confirmed during Fable's review), but pydsl has no `fill()` of any kind
  yet for *any* shape — that's Cluster D's scope (fill/styling), not this
  one. `sector()` is exposed here purely as an outline/wedge-boundary
  primitive (e.g. for angle-highlight diagrams); a filled pie chart isn't
  achievable until Cluster D lands. Its docstring doesn't oversell this.

## API surface

```python
def circle(center: Point, radius: float) -> Circle:
    """A circle with the given center and radius."""
```

Validates `radius > 0` immediately (mirrors `ellipse()`'s center-axes
check). Records `CircleCenterRadius(id=cid, center=center.id,
radius=radius)` — the same IR class `incircle()`'s literal-radius branch
already uses — and returns the existing `Circle` handle with
`_radius_thunk=lambda: radius` (no new handle needed; `Circle` already
supports a literal-radius thunk via `incircle()`'s precedent).

```python
def arc(circle: Circle, start: Point, end: Point, reflex: bool = False) -> Arc:
    """The circular arc between start and end (both must lie on circle —
    use point_on(circle, angle) to construct them; an off-circle point can
    silently shift the rendered arc away from circle). reflex=False (the
    default) draws whichever of the two arcs spans <=180°; reflex=True
    draws the other one."""
```

```python
def sector(circle: Circle, start: Point, end: Point, reflex: bool = False) -> Sector:
    """The closed pie-slice region bounded by the two radii to start and
    end and the arc between them. Same start/end contract as arc() — both
    must lie on circle; see arc()'s docstring."""
```

Both extract `circle.center` themselves — unlike the DSL's `ArcOp`/`SectorOp`,
which take `center` as a separate field even though it's always the arc's
own circle's center. Both call a shared private helper, once per point,
before recording anything:

```python
def _validate_on_circle(fn_name: str, circle: Circle, point: Point, point_role: str) -> None:
    cx, cy = circle.center.x, circle.center.y
    px, py = point.x, point.y
    if cx is None or cy is None or px is None or py is None:
        return
    try:
        radius = circle.radius
    except NotImplementedError:
        return
    if isinstance(radius, str):
        return  # incircle()'s symbolic fallback — not a comparable number
    actual = math.hypot(px - cx, py - cy)
    if abs(actual - radius) > max(radius * 1e-6, 1e-9):
        raise ValueError(
            f"{fn_name}(): {point_role} point {point.id!r} is not on the given "
            f"circle (distance {actual:.6g} from center, circle radius is "
            f"{radius:.6g}). Use point_on(circle, angle) to get a point "
            "guaranteed to lie on the circle."
        )
```

Both `arc()` and `sector()` call this twice — `_validate_on_circle(fn_name,
circle, start, "start")` and `_validate_on_circle(fn_name, circle, end,
"end")` — checking `end` as well as `start` closes the render-time
corruption path described above, even though the compile-level math alone
only strictly requires checking `start`.

`arc()` then records `ArcCenterStartEnd(id=aid, center=circle.center.id,
start=start.id, end=end.id, reflex=reflex)` and returns `Arc(id=aid)`.
`sector()` records `SectorCenterStartEnd(...)` the same way and returns
`Sector(id=sid)`. Two new handles in `handles.py`, both structurally
identical to the existing `Line`/`Ray` (bare `id: str`, no `_builder`, no
methods) — `draw()` only needs `.id`, and a script already holds the
source `circle` for center/radius:

```python
@dataclass(frozen=True)
class Arc:
    id: str


@dataclass(frozen=True)
class Sector:
    id: str
```

```python
def regular_sectors(circle: Circle, n: int) -> tuple[Sector, ...]:
    """Divide circle into n equal pie slices, returned in counter-clockwise
    order starting from angle 0. n must be >= 2."""
```

Pure trig, no solver — the same shape as `regular_polygon()`'s loop, but
driven by `circle.center`/`circle.radius` instead of caller-given values.
Requires a *literal* circle (i.e. `circle()`, not `circumcircle()`/
`incircle()`) via `circle.center._known()`, exactly the same restriction
`regular_polygon()` already has on its own `center` parameter — an
accepted, precedented limitation, not a new one:

```python
def regular_sectors(circle: Circle, n: int) -> tuple[Sector, ...]:
    if n < 2:
        raise ValueError(f"regular_sectors() requires n >= 2, got {n}")
    circle.center._known()  # raises for circumcircle()/incircle() circles,
                             # whose center is never a literal coordinate —
                             # same restriction regular_polygon() already has
    radius = circle.radius  # always a float once center._known() has passed:
                             # only circle()'s literal-radius path reaches here
    builder = get_builder()
    boundary_pts = []
    for i in range(n):
        angle = i * 2 * math.pi / n
        # Rounded to 10dp, matching recipe/lower.py's established fix for
        # the exact same problem: math.sin(math.pi) == 1.2246e-16, not 0,
        # which at n=2 flips arc_params's minor/major tie-break (ccw<=180.0)
        # and renders both "halves" of the pie as the same semicircle.
        x = round(circle.center.x + radius * math.cos(angle), 10)
        y = round(circle.center.y + radius * math.sin(angle), 10)
        boundary_pts.append(_record_literal_point(builder, x, y))
    return tuple(
        sector(circle, boundary_pts[i], boundary_pts[(i + 1) % n])
        for i in range(n)
    )
```

Each slice spans `2π/n <= π` for any `n >= 2`, so `reflex` is always
`False` — never ambiguous between the minor/major arc for an equal
division (the rounding above is what makes this actually true at `n=2`
rather than merely true in exact arithmetic). `regular_sectors()` reuses
`sector()`'s own validation and `SectorCenterStartEnd`-recording rather
than duplicating it — harmless, inherited safety, since every
`boundary_pts` point is freshly computed as exactly `radius` from
`circle.center` by construction and the guard never actually fires here.

## Data flow

All four functions live in `geometry_diagrams/pydsl/api.py`, alongside the
existing circle-family functions (`circumcircle`, `incircle`) — `circle()`
goes right before them; `arc()`/`sector()`/`regular_sectors()` go
immediately after, since `regular_sectors()` depends on `sector()`.
`Arc`/`Sector` handles go in `handles.py` next to `Ray`. All four functions
and both handles are registered in `geometry_diagrams/pydsl/__init__.py`'s
import lines and `__all__`; `Arc` and `Sector` are added to `stub.py`'s
`_HANDLE_CLASS_NAMES` (same reasoning as `Ray`/`Ellipse` in Cluster B — a
class not in that set is silently omitted from the generated stub even
when referenced as a return type).

Two small pre-existing docstrings get one-line updates so the
LLM-facing stub stays accurate: `point_on()`'s docstring currently only
mentions lines/segments — since this design leans on `point_on(circle,
angle)` as the correct way to build `arc()`/`sector()`'s points, it needs
to mention circles explicitly. `draw()`'s docstring enumerates the
drawable types by name ("triangle, polygon, circle, line, or segment")
and needs `arc`/`sector` added to that list.

No IR or renderer changes: `CircleCenterRadius`, `ArcCenterStartEnd`, and
`SectorCenterStartEnd` all already exist and are already fully handled by
`to_sympy.py`/`to_tikz.py`/`to_svg.py` (confirmed — both `to_tikz.py` and
`to_svg.py` already branch on `isinstance(sym_obj, Arc)` /
`isinstance(sym_obj, Sector)` for stroke/fill rendering). This cluster is
pure pydsl-layer exposure, like Cluster A and most of Cluster B.

## Testing

New file `tests/test_pydsl_arcs_sectors.py`, TDD, covering:

- `circle()`: records `CircleCenterRadius` with correct fields; `radius <= 0`
  raises immediately; `.center`/`.radius` resolve correctly on the returned
  handle.
- `arc()`/`sector()`: each records the correct IR def with correct
  `center`/`start`/`end`/`reflex` field mapping (record-level, using
  `circle()`'s output so `circle.center` is a real `Point`).
- The on-circle guard: literal-coordinate tests where `start` is
  deliberately off-circle raises `ValueError` mentioning "not on the given
  circle" AND mentioning "start"; a separate test that an off-circle `end`
  raises the same way, mentioning "end" (this is the case Fable's review
  caught — the compile-level radius math alone wouldn't require checking
  `end`, but the render-time endpoint-swap in `render_util.py::arc_params`
  means an off-circle `end` is just as real a bug, so it must be covered
  here); a `start`/`end` pair built via hand-computed literals that ARE on
  the circle does not raise; a case where `circle.center`'s coordinates
  are unknown does not raise (guard skipped, not a false positive) —
  mirrors the `polygon()` guard's known/unknown-coordinate test shape from
  Cluster B.
- `reflex`: a compile-level test using `compile_defs()` that a `reflex=True`
  arc's rendered sweep differs from `reflex=False` for the same
  `start`/`end` (e.g. checking the `Arc`/`Sector` marker object's `.reflex`
  field survives compilation, since the actual sweep-angle math lives in
  already-tested `to_sympy.py`/`to_tikz.py`/`to_svg.py` code this cluster
  doesn't touch).
- `regular_sectors()`: `n < 2` rejection; a hand-computed test with a
  literal-center circle (e.g. `circle(point(0,0), 1)`, `n=4`) asserting the
  4 boundary points land at hand-computable angles (0, π/2, π, 3π/2) and
  that exactly 4 `SectorCenterStartEnd` defs are recorded, each pairing
  consecutive boundary points (including the wraparound last→first pair);
  the specific `n=2` case Fable's review flagged, asserting the two
  recorded sectors' boundary points are NOT coincident/degenerate and that
  each rounds to the expected exact half-circle boundary (e.g.
  `circle(point(0,0), 1)`, `n=2` → boundary points at `(1,0)` and exactly
  `(-1,0)`, not `(-1, 1.2e-16)`); a circle from `circumcircle()`/
  `incircle()` (unknown center) raises `_known()`'s "no known coordinates"
  error, NOT a symbolic-radius-specific error — this is the same
  restriction `regular_polygon()` already has and reuses that function's
  existing error message, so no separate "known numeric value" error path
  exists to test.
- A sandbox-path test (`run_script`) building a circle, an arc, and a
  sector through the real sandbox, confirming all three names resolve and
  the resulting `DiagramIR` contains the expected def kinds.

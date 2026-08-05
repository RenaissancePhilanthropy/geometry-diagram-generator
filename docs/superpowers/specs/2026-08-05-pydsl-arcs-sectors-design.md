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

## A real footgun in the underlying IR

`ArcCenterStartEnd`/`SectorCenterStartEnd` don't store a radius — the
compiler derives it from `center.distance(start)` (confirmed in
`to_sympy.py`'s `Arc`/`Sector` marker-class docstrings: "`radius` is
... `center.distance(start)`... The arc sweeps counter-clockwise from
`start` to the point where the ray `center → end` meets the circle").
Concretely: **only `start`'s distance from center sets the arc's actual
radius; `end` only supplies a direction** — a ray from center through
`end`, intersected with the circle of that radius.

This means a script that passes a `start` point which isn't actually on the
circle it thinks it's drawing an arc of gets a **silently wrong radius** —
the arc renders at `start`'s distance from center, detached from the circle
the script actually drew. `end`'s distance from center is irrelevant and
never needs checking.

pydsl already has the tool to avoid this correctly: `point_on(circle,
angle)` (existing function — `PointOnParam`'s `t` is "interpreted as angle
in radians by convention" for circles) always returns a point exactly on
the circle. `arc()`/`sector()` document this as the correct way to build
`start`/`end`, and additionally **guard against the mistake directly**: when
`circle.center`'s coordinates and `circle.radius` are both resolvable to
concrete numbers, verify `start` is actually on the circle before recording
anything, raising `ValueError` otherwise. This mirrors Cluster B's
`polygon()` coincident-vertex guard — a specific, previously-easy LLM
mistake gets a clear compile-time-adjacent error instead of a silently
wrong diagram.

The guard only checks `start` (per the radius derivation above, `end`'s
distance from center is never used, so validating it would reject correct
calls). When either `circle.center`'s coordinates or `circle.radius` can't
be resolved to a concrete number yet, the guard is skipped — same
"validate only what's currently knowable" policy every other
coordinate-dependent check in `api.py` already follows (e.g.
`circumcircle(...).radius`'s `NotImplementedError` fallback,
`regular_polygon()`'s `center._known()`).

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
    """The circular arc from start to end, sweeping counter-clockwise
    around circle.center. start must lie on circle (use point_on(circle,
    angle) to construct it) — its distance from the center sets the arc's
    actual radius, so an off-circle start silently detaches the arc from
    the circle it's nominally part of. end only supplies a direction and
    does not need to be exactly on the circle. reflex=True draws the major
    (>180°) arc instead of the minor (<=180°) one."""
```

```python
def sector(circle: Circle, start: Point, end: Point, reflex: bool = False) -> Sector:
    """The closed pie-slice region bounded by the two radii to start and
    end and the arc between them (fillable, unlike arc()). Same start/end
    contract as arc() — start must lie on circle; see arc()'s docstring."""
```

Both extract `circle.center` themselves — unlike the DSL's `ArcOp`/`SectorOp`,
which take `center` as a separate field even though it's always the arc's
own circle's center. Both call a shared private helper before recording
anything:

```python
def _validate_start_on_circle(fn_name: str, circle: Circle, start: Point) -> None:
    cx, cy = circle.center.x, circle.center.y
    sx, sy = start.x, start.y
    if cx is None or cy is None or sx is None or sy is None:
        return
    try:
        radius = circle.radius
    except NotImplementedError:
        return
    if isinstance(radius, str):
        return  # incircle()'s symbolic fallback — not a comparable number
    actual = math.hypot(sx - cx, sy - cy)
    if abs(actual - radius) > max(radius * 1e-6, 1e-9):
        raise ValueError(
            f"{fn_name}(): start point {start.id!r} is not on the given circle "
            f"(distance {actual:.6g} from center, circle radius is {radius:.6g}). "
            "Use point_on(circle, angle) to get a point guaranteed to lie on the circle."
        )
```

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
driven by `circle.center`/`circle.radius` instead of caller-given values:

```python
def regular_sectors(circle: Circle, n: int) -> tuple[Sector, ...]:
    if n < 2:
        raise ValueError(f"regular_sectors() requires n >= 2, got {n}")
    circle.center._known()
    radius = circle.radius
    if isinstance(radius, str):
        raise ValueError(
            "regular_sectors() requires circle.radius to be a known numeric "
            "value, not a symbolic expression"
        )
    builder = get_builder()
    boundary_pts = []
    for i in range(n):
        angle = i * 2 * math.pi / n
        x = circle.center.x + radius * math.cos(angle)
        y = circle.center.y + radius * math.sin(angle)
        boundary_pts.append(_record_literal_point(builder, x, y))
    return tuple(
        sector(circle, boundary_pts[i], boundary_pts[(i + 1) % n])
        for i in range(n)
    )
```

Each slice spans `2π/n <= π` for any `n >= 2`, so `reflex` is always
`False` — never ambiguous between the minor/major arc for an equal
division. `regular_sectors()` reuses `sector()`'s own validation and
`SectorCenterStartEnd`-recording rather than duplicating it (every
`boundary_pts` point is freshly computed as exactly `radius` from
`circle.center` by construction, so the guard never fires here — it's
inherited safety, not redundant work).

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
- The on-circle guard: a compile-level or literal-coordinate test where
  `start` is deliberately off-circle raises `ValueError` mentioning
  "not on the given circle"; a `start` built via a hand-computed
  literal that IS on the circle does not raise; a case where
  `circle.center`'s coordinates are unknown does not raise (guard
  skipped, not a false positive) — mirrors the `polygon()` guard's
  known/unknown-coordinate test shape from Cluster B.
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
  a symbolic-radius circle (e.g. from `incircle()` with unresolvable
  vertices) raises the "known numeric value" error.
- A sandbox-path test (`run_script`) building a circle, an arc, and a
  sector through the real sandbox, confirming all three names resolve and
  the resulting `DiagramIR` contains the expected def kinds.

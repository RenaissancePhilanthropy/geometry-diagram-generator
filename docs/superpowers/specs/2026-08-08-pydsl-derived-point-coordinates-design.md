# pydsl Derived-Point Numeric Coordinates — Design

## Problem

`Point` (`geometry_diagrams/pydsl/handles.py`) is a frozen dataclass with
private `_x`/`_y` fields (`float | None`). Only `point(x, y)` literals —
and points derived from them via `+`/`-`/`*` — have known `_x`/`_y` at
script time. Every *constructed* point — `intersection()`, `rotate_point()`,
`reflect_point()`, `point_on()`, `dilate_point()`, `centroid()`,
`foot_of_perpendicular()`, `perpendicular_bisector().midpoint`, etc. —
returns `Point(id=pid, _builder=builder)` with `_x=None, _y=None`
permanently. The public `.x`/`.y` properties raise a clear `ValueError` for
these; `api.py`'s `distance()` and `Point.__add__`/`__sub__`/`__mul__` read
the private fields directly and hit the same wall.

This is not a corner case. A large multi-model eval (13 LLMs, 402-scenario
geometry curriculum, reviewed by 13 independent Fable subagents) found this
is the single most common cross-model failure class — confirmed
independently in 6+ models, up to 43% of one model's failures. The
textbook-correct construction —

```python
O = intersection(perp_bisector_1, perp_bisector_2)
circ = circle(O, distance(O, A))
```

— fails every time, even though `O`'s position is fully determined the
moment both perpendicular bisectors exist. The error message already
explains the limitation; models fail identically across all 3 retries
regardless. It's a real DSL capability gap, not model confusion.

## Goal

Make `.x`/`.y` (and everything built on them: `distance()`, `+`/`-`/`*`,
`walk()`) resolve on demand for *any* point once its inputs are fully
numeric — reusing the real compiler (`to_sympy.py`), not duplicating
geometry math in the pydsl layer. Raise only when resolution genuinely
fails for a real geometric reason.

## Non-goals

- No change to the "skip if not yet known" internal guards that
  intentionally read `pt._x`/`pt._y` directly today (coincidence checks in
  `polygon()`/`polyline()`, `_validate_on_circle()`/`_validate_on_ellipse()`
  in `api.py`). These stay reading the raw private fields — they're
  best-effort early-friendly-error checks, not the numeric-access path this
  design is fixing, and forcing a full resolve on every `polygon()`/
  `circle()` call would add unwanted compile cost with no benefit (the real
  validation happens at render-compile time regardless).
- No change to `PointFree`/random-parameter points' *semantics*. (They
  happen to be dead code for pydsl today — `grep` confirms pydsl never
  emits `PointFree`, `PointOnRandom`, or `PointOnIntent`; `point_on()`
  always records `PointOnParam(t=t)`. Nothing in this design depends on
  that staying true, but it's why RNG ordering isn't a concern here.)
- No IR schema changes. `PickClosestTo` and `PointFixed` already exist and
  already do exactly what's needed for pin-on-observe (below).

## Design

### Why "just recompile a prefix" isn't quite right

An earlier version of this design proposed: on `.x` access, build a
`DiagramIR` from `builder.define` so far and call the existing
`compile_defs()` (which does its own topological sort from scratch each
time). A Fable design review caught a real bug in this: `compile_defs()`
is **not** a pure function of each def's own dependencies in one specific
case — `PointIntersection` with `pick=None` (the common case when a model
doesn't pass `near=`/`side_of=`). Its auto-pick heuristic
(`_apply_pick` in `to_sympy.py`, lines ~928-955) filters by canvas bounds
and tie-breaks by distance to **the centroid of every point compiled so
far** — `sym.values()`. A preview compile (partial `sym`) and the final
render compile (complete `sym`) can therefore pick *different* candidates
for the same ambiguous intersection. A script could compute a radius or
label offset from a point at candidate A, and the actual rendered diagram
could place it at candidate B — silent, hard-to-notice corruption.

Verified: this is the *only* place `_compile_one` reads anything from
`sym` other than a statement's own declared dependencies (`ref(x_id)`
lookups, which are always already present thanks to topological order).
Every other `DefStmt` kind, and every explicit `PickRule`
(`PickClosestTo`, `PickUpperOfLine`/`PickLowerOfLine`, etc.), is a pure
function of its own inputs. So the fix only needs to handle one case.

### Mechanism

**1. Incremental compile, not recompile-from-scratch.** pydsl's
`builder._defs` list is *already* a valid topological order — defs are
append-only and every reference points backward to an already-recorded
id. So there's no need to rebuild a `DiagramIR` and re-run
`TopologicalSorter` on every access. `Builder` (`builder.py`) gains:

```python
self._sym: dict[str, Any] = {}       # SymTable, growing incrementally
self._sym_watermark: int = 0         # index into self._defs already compiled into self._sym
```

and a new method:

```python
def _resolve_point(self, pid: str) -> tuple[float, float]:
    """Return (x, y) for any point id, compiling as many new defs as
    needed (and no more) via to_sympy.py's real per-statement compiler.
    Raises whatever to_sympy.py raises (IntersectionError, PickError,
    IRCompileError, ...) if a def between the watermark and pid's
    definition genuinely can't be resolved."""
    if pid in self._coord_floats:
        return self._coord_floats[pid]
    self._advance_sym()
    if pid not in self._coord_floats:
        raise ValueError(f"Point {pid!r} has no known coordinates")
    return self._coord_floats[pid]

def _advance_sym(self) -> None:
    from random import Random
    import sympy.geometry as spg
    from geometry_diagrams.ir import ir as ir_mod
    from geometry_diagrams.ir.to_sympy import _compile_one

    canvas = self._canvas or ir_mod.Canvas()
    rng = Random(42)  # PointFree/random defs are dead code for pydsl; any seed is fine
    # Iterate a SLICE (a copy) taken once up front — _pin_intersection appends
    # new hidden PointFixed defs to self._defs mid-loop, which must not be
    # picked up by this iteration (they're compiled and cached inline below
    # instead, and self._sym_watermark accounts for them afterward).
    for stmt in self._defs[self._sym_watermark:]:
        obj = _compile_one(stmt, self._sym, {}, canvas, rng, all_def_ids=None)
        self._sym[stmt.id] = obj
        if isinstance(obj, spg.Point):
            self._coord_floats[stmt.id] = (float(obj.x), float(obj.y))
        if isinstance(stmt, ir_mod.PointIntersection) and stmt.pick is None:
            self._pin_intersection(stmt, obj)
    self._sym_watermark = len(self._defs)
```

This calls `_compile_one` — the existing per-statement compiler already
used inside `compile_defs()`'s loop — directly, threading through the same
running `sym` dict a script's own execution builds up. No new geometry
math; the real compiler is the only thing that ever computes a coordinate.

Two things `compile_defs()`'s own loop does *outside* `_compile_one` that
`_advance_sym` deliberately does not replicate: registering
`PolygonExterior`/`PolygonOnEdge` sub-vertices into `sym`, and consuming
the op-cap counter for synthesized pin defs. The first is safe today
because pydsl never emits either `DefStmt` kind (`grep` confirms every
`builder._add` call site) — this is a landmine if pydsl ever grows a
`polygon_exterior()`-style function; whoever adds one must also teach
`_advance_sym` the same sub-vertex registration `compile_defs()` does. The
second is intentional: pinned hidden `PointFixed` defs are internal
bookkeeping, not model-authored ops, and shouldn't count against a
script's op cap.

One more accepted edge case: `_advance_sym` resolves against
`self._canvas or ir_mod.Canvas()` — whatever canvas exists *at the moment
of first resolution*. If a script queries `.x` on an ambiguous
intersection before calling `canvas()`, the auto-pick heuristic filters
against the default ±5 bounds, and that choice gets pinned permanently —
even if the script's eventual real canvas would have made the *other*
candidate the in-bounds one. This doesn't break the preview/final
consistency guarantee (both still agree with each other), but the pinned
candidate could end up outside the visible canvas. Not fixed by this
design; flagged here so it isn't mistaken for a bug later.

**2. Pin-on-observe for ambiguous intersections.** Immediately after
compiling a `PointIntersection` whose `pick` is still `None`, synthesize a
hidden `PointFixed` at the just-observed coordinates and rewrite the
stored def's `pick` in place:

```python
def _pin_intersection(self, stmt, obj) -> None:
    from geometry_diagrams.ir import ir as ir_mod

    hidden_pid = self._fresh_hidden_id("pin")
    self._defs.append(ir_mod.PointFixed(id=hidden_pid, x=float(obj.x), y=float(obj.y)))
    self._sym[hidden_pid] = obj
    self._coord_floats[hidden_pid] = (float(obj.x), float(obj.y))
    stmt.pick = ir_mod.PickClosestTo(p=hidden_pid)
```

`DefBase` (`ir.py`) has no `frozen=True` in its `model_config`, so mutating
`stmt.pick` in place is a normal pydantic field assignment — the same
object reference already lives in `builder._defs`, so this change is
picked up by `builder.build()` automatically. From this point on, a full
from-scratch `compile_defs()` call (the one `run_ir_pipeline` makes at
render time) resolves this intersection via `PickClosestTo` — pure,
dependency-only, guaranteed to reproduce the observed point regardless of
what else is in `sym` by then. Preview and final render agree **by
construction**, not by hoping the heuristic stays stable.

This pin is applied unconditionally whenever an unpicked intersection is
resolved this way — including the case where it wasn't actually ambiguous
(a single candidate). Re-deriving "was this actually ambiguous" without
duplicating `_apply_pick`'s candidate-filtering logic isn't worth it, and
pinning a single-candidate intersection to `PickClosestTo` targeting
itself is a correct no-op.

**3. `Point.x`/`Point.y` become resolve-on-demand:**

```python
@property
def x(self) -> float:
    """The x-coordinate. Available for any point once its position is
    fully determined by earlier script statements — point(x, y) literals,
    arithmetic derived from them, and constructed points (point_on(),
    rotate_point(), intersection(), etc.) alike. Raises only if the
    position genuinely can't be determined (e.g. a real geometric error
    in an earlier construction)."""
    if self._x is not None:
        return self._x
    return self._builder._resolve_point(self.id)[0]

@property
def y(self) -> float:
    """The y-coordinate. Same contract as x."""
    if self._y is not None:
        return self._y
    return self._builder._resolve_point(self.id)[1]
```

`_known()` has five callers, not just the three inside `Point` itself —
`grep` finds it also used in `api.py` at `regular_polygon()` (line 128),
`rectangle()` (153), `walk()` (187), and `regular_sectors()` (424).
Deleting the method outright breaks all four with `AttributeError`; the
fix differs per call site:

- `regular_polygon()`, `rectangle()`, `walk()`: each calls `pt._known()`
  purely as a pre-check immediately before reading `.x`/`.y` on that same
  point. Once `.x`/`.y` resolve-or-raise correctly on their own, the
  pre-check is redundant — delete these three call lines outright. This is
  a genuine improvement: these three now work with constructed points too
  (e.g. `walk()` from a `point_on()` result), matching this design's Goal.
- `regular_sectors()` is different: its `_known()` call on `circle.center`
  is not a coordinate pre-check, it's the enforcement of a *documented*
  restriction — the docstring states "circle must be a literal `circle()`
  (not `circumcircle()`/`incircle()`)" — because the line right after it,
  `radius = circle.radius`, relies on radius being a plain float; only
  `circle()`'s literal-radius path guarantees that. `circumcircle()`/
  `incircle()`'s `.radius` is a thunk that can raise `NotImplementedError`
  or return a symbolic string. Once derived points resolve on demand, a
  `circumcircle()`'s center stops being what makes this check fire, so
  checking `circle.center._known()` no longer enforces the intended
  restriction — replace it with a direct check on `radius` itself:

  ```python
  def regular_sectors(circle: Circle, n: int) -> tuple[Sector, ...]:
      if n < 2:
          raise ValueError(f"regular_sectors() requires n >= 2, got {n}")
      try:
          radius = circle.radius
      except NotImplementedError as exc:
          raise ValueError(
              "regular_sectors(): circle must be a literal circle() with a "
              "numeric radius, not circumcircle()/incircle()"
          ) from exc
      if not isinstance(radius, (int, float)):
          raise ValueError(
              "regular_sectors(): circle must be a literal circle() with a "
              f"numeric radius, not circumcircle()/incircle() — got {radius!r}"
          )
      # ... unchanged from here (boundary_pts loop, sector() calls)
  ```

With those four sites updated, `_known()` itself is deleted — nothing else
calls it. `__add__`/`__sub__`/`__mul__` and `api.py`'s `distance()` are
simplified to use the public, now-always-correct properties instead of the
private fields:

```python
def __add__(self, other: "Point") -> "Point":
    return _record_literal_point(self._builder, self.x + other.x, self.y + other.y)

def __sub__(self, other: "Point") -> "Point":
    return _record_literal_point(self._builder, self.x - other.x, self.y - other.y)

def __mul__(self, scalar: float) -> "Point":
    return _record_literal_point(self._builder, self.x * scalar, self.y * scalar)
```

```python
def distance(p: Point, q: Point) -> float:
    """The distance between p and q — works for any two points once both
    positions are determined, not just point(x, y) literals."""
    return math.hypot(p.x - q.x, p.y - q.y)
```

**Cache lives on `Builder`, not `Point`.** `Point` is frozen, and handles
get freely re-minted elsewhere in the codebase without carrying forward
known coordinates — e.g. `Triangle.angle_at()`/`Polygon.angle_at()`
construct `Point(id=others[0], _builder=self._builder)` for a vertex that
may already be a `point(x, y)` literal with real coordinates sitting in
`builder._coord_floats`. Checking the builder-level cache first (inside
`.x`/`.y`, ahead of any resolve attempt) fixes this pre-existing latent bug
for free: today, `.x` on a triangle-vertex handle minted this way
incorrectly raises even when the underlying point is a literal.

**Error behavior.** If resolution genuinely fails, `_resolve_point`
propagates whatever `to_sympy.py` raises (`IntersectionError`,
`PickError`, `IRCompileError`, plain geometry `ValueError`s from SymPy,
...) rather than the old generic "no known coordinates" message — that
message would now be actively misleading, since resolution is genuinely
attempted. `python_full.py`'s retry loop already surfaces
`Code execution failed at line '...' due to: <exception>` verbatim, so no
extra wrapping is required for the model-visible feedback to stay
actionable. One accepted side effect: accessing `.x` on point N can now
surface a compile error from an *earlier*, unrelated statement between the
last resolve and N (whatever was appended since the watermark last
advanced) — that statement would have failed at render time regardless;
this only changes *when* the error surfaces, typically earlier and closer
to its actual cause, which is a net improvement for the retry loop.

### Consequence for scope

This subsumes the narrower fixes suggested by the eval review for this
failure class. A dedicated `circle_through(center, point)` convenience
function is no longer necessary — `circle(center, distance(center,
through_point))` now works once `distance()` transparently resolves
derived points.

## Docstring / prompt updates

- `Point.x`/`Point.y` docstrings (above) — rewritten to describe the new
  contract; the old "raises for a constructed point" framing is gone. The
  `Point` class body comment above the `_x`/`_y` field declarations
  (`handles.py` lines ~118-126, "Known only for point(x, y) literals...")
  describes the same old contract and needs the same rewrite.
- `geometry_diagrams/strategies/instructions_python_full.py` currently
  documents `.x`/`.y` as raising on constructed points (added earlier this
  session as part of the labeling-fix work) — this passage needs rewriting
  to reflect the new behavior. `stub.py` regenerates the prompt's API
  listing from docstrings automatically, so only the docstrings and this
  one prose passage need hand-editing.
- Existing tests that assert the *old* raising behavior must be **replaced
  outright**, not left alongside new ones — `test_pydsl_point_ergonomics.py`
  has `test_direct_x_access_on_constructed_point_raises_not_none`,
  `test_direct_y_access_on_point_on_raises_not_none`, and
  `test_pydsl_derived_constructions.py`/wherever `distance()` is tested has
  `test_distance_raises_for_a_point_with_unknown_coordinates` — these now
  assert behavior this design deliberately removes.

## Testing

- `.x`/`.y` resolve correctly for one representative case of each
  construction kind that previously left `_x`/`_y` unset: `point_on()`,
  `rotate_point()`, `reflect_point()`, `dilate_point()`, `centroid()`,
  `foot_of_perpendicular()`, `perpendicular_bisector().midpoint`, and
  `intersection()` (both with an explicit `near=`/`side_of=` pick and with
  none).
- `distance()` and Point arithmetic (`+`/`-`/`*`) work when one or both
  operands are constructed points, matching values computed independently
  via SymPy for the same construction.
- **Pin-on-observe correctness (the load-bearing test):** a script that
  triggers a genuinely ambiguous `intersection()` (two candidates, both
  in-canvas) with no explicit pick, reads `.x`/`.y` on it (forcing a
  preview resolve), then continues the script adding more points/canvas
  changes that would shift the auto-pick heuristic's centroid if it ran
  again unpinned. Assert: (a) the previewed value and (b) the value in the
  final `compile_defs()`-produced `DiagramIR` (as `run_ir_pipeline` would
  produce it) are identical. This is the regression test for the exact bug
  the design review caught.
- Builder-level cache hit for a triangle/polygon vertex re-minted via
  `angle_at()` returns the correct literal coordinates without a resolve
  attempt (the "free" bugfix).
- A genuine resolution failure (e.g. `intersection()` of two objects that
  don't actually meet) surfaces the real underlying error, not the old
  generic message, when reached via `.x`/`.y`/`distance()`.
- Full existing suite still passes after removing `_known()` and updating
  the three tests listed above.

# Final review fix report — pydsl assert predicates

Branch: `pydsl-assert-predicates` (unchanged, no branch switch).

## Finding 1: Stale docstring claim in `geometry_diagrams/pydsl/asserts.py`

The module docstring previously claimed every function in the file was "a
thin wrapper around an existing `ir.Check` kind", which is false for
`assert_in_canvas` (deliberately not backed by any `ir.Check`, per
`.scratch/pydsl-assert-predicates/spec.md`'s Implementation Decisions).

**Before:**
```
"""assert_* geometric-invariant predicates for the Python DSL surface.

Each function here is a thin wrapper around an existing `ir.Check` kind:
build the matching `ir.Check` object from the caller's handle ids, force
resolution of any not-yet-materialized point via `Builder._advance_sym()`,
run it through `checks._check_one` (the same dispatcher the JSON/recipe DSL
uses), and raise `GeometricAssertionError` with a message that has every
recognized point id substituted for its resolved `(x.xx, y.yy)` coordinate
string (pydsl ids are opaque auto-generated hidden ids the LLM never wrote,
so a raw id in a failure message is useless to it).

`GeometricAssertionError` is a `ValueError` subclass (defined in
`builder.py`, imported here) so any code that already catches `ValueError`
keeps working unchanged; `retry.py` additionally special-cases it to the
`"geometric_assertion"` failure classification.
"""
```

**After:**
```
"""assert_* geometric-invariant predicates for the Python DSL surface.

All functions except `assert_in_canvas` are thin wrappers around an existing
`ir.Check` kind: build the matching `ir.Check` object from the caller's
handle ids, force resolution of any not-yet-materialized point via
`Builder._advance_sym()`, run it through `checks._check_one` (the same
dispatcher the JSON/recipe DSL uses), and raise `GeometricAssertionError`
with a message that has every recognized point id substituted for its
resolved `(x.xx, y.yy)` coordinate string (pydsl ids are opaque
auto-generated hidden ids the LLM never wrote, so a raw id in a failure
message is useless to it).

`assert_in_canvas` is the one exception: it has no backing `ir.Check` kind
(a deliberate design decision — see its own docstring) and instead reads
`builder._canvas` directly and compares bounds itself.

`GeometricAssertionError` is a `ValueError` subclass (defined in
`builder.py`, imported here) so any code that already catches `ValueError`
keeps working unchanged; `retry.py` additionally special-cases it to the
`"geometric_assertion"` failure classification.
"""
```

No behavior changed — `assert_in_canvas`'s implementation and its own
docstring (which already correctly explained the "no ir.Check" decision)
were left untouched.

## Finding 2: Undocumented schema addition in `docs/geometry-dsl-spec.md`

Read `geometry_diagrams/ir/ir.py` (lines ~796-824) and
`geometry_diagrams/ir/checks.py` (`_check_one` dispatch, lines ~202-231) to
confirm field names and semantics for the four new `ir.Check` kinds added by
this feature:

- `Convex(polygon: ObjId)` — kind `"convex"` — maps to `Polygon.is_convex()`.
- `CCW(polygon: ObjId)` — kind `"ccw"` — positive signed area check.
- `MinDistance(a: PointId, b: PointId, min_dist: float)` — kind
  `"min_distance"` — fails if points are strictly closer than `min_dist`.
- `CongruentTriangles(t1: TriangleId, t2: TriangleId)` — kind
  `"congruent_triangles"` — SSS: sorted side lengths match pairwise within
  tolerance, no vertex correspondence required.

The doc's "Geometric properties" list (under `## Validation`, item 2) is the
existing place enumerating check kinds in `name(args): description` format
(e.g. `right_angle(A, B, C)`, `centroid(G, A, B, C)`). Added four entries
there, matching that exact style, immediately after the existing
`centroid(...)` line:

```
   - `centroid(G, A, B, C)`: G is centroid of triangle ABC
   - `convex(P)`: polygon P's vertices form a convex shape
   - `ccw(P)`: polygon P's vertices are wound counter-clockwise (positive signed area)
   - `min_distance(A, B, min_dist)`: points A and B are at least min_dist apart
   - `congruent_triangles(T1, T2)`: triangles T1 and T2 are congruent (SSS: matching sorted side lengths, no required vertex correspondence)
```

## Finding 3: Stray ticket-number comment

`geometry_diagrams/pydsl/asserts.py` had a section-divider comment reading:

```
# ---------------------------------------------------------------------------
# New predicates (ticket 04): convex / ccw / min-distance / congruent triangles
# ---------------------------------------------------------------------------
```

Reworded to describe the code without referencing the internal ticket
number:

```
# ---------------------------------------------------------------------------
# Convex / ccw / min-distance / congruent-triangles predicates
# ---------------------------------------------------------------------------
```

Grepped the file afterward for "ticket" (case-insensitive) — no remaining
references.

## Scope discipline

Did not touch: the 24 `assert_*` functions' type annotations, `__init__.py`'s
`__all__` construction, tolerance handling in `assert_convex`/`assert_ccw`,
type-checking in `assert_same_side`/`assert_opposite_side`, or any test
assertions. Only the two touched findings' surrounding text and the doc file
were edited.

## Test results

- `.venv/bin/python -m pytest tests/test_pydsl_asserts.py -q` → 59 passed.
- `.venv/bin/python -m pytest tests/ -q` → 1904 passed, 48 skipped. (Some
  unrelated OTEL span-export connection-refused warnings printed to stderr
  after the summary — these come from a tracing exporter trying to reach
  `localhost:3000`, are pre-existing/environmental, and do not affect test
  pass/fail results.)

## Files changed

- `geometry_diagrams/pydsl/asserts.py` — docstring reworded, ticket comment
  reworded.
- `docs/geometry-dsl-spec.md` — four new check-kind doc entries added.

## Concerns

None. All three fixes are documentation/comment-only; no runtime behavior
changed, and the full test suite passes.

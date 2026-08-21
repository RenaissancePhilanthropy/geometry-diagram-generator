# Report: 03 — pydsl asserts core (19 mirror predicates)

## What was implemented

New file `geometry_diagrams/pydsl/asserts.py`:

- One shared private dispatch helper: `_run_assertion(builder, check, point_ids)`.
  In order: calls `builder._advance_sym()`; calls
  `checks._check_one(check, builder._sym, checks.DEFAULT_TOL)` (the caller's
  `tol` is never passed as this third positional argument — it lives only on
  `check.tol`, set by each mirror function when constructing the `ir.Check`
  object); on failure, substitutes every point id in `point_ids` with its
  resolved `"(x.xx, y.yy)"` coordinate string (longest-id-first, to avoid a
  numeric-suffix collision like `__pydsl_pt_1` matching inside
  `__pydsl_pt_10`; both the bare and `repr()`-quoted forms are substituted,
  since `checks.py`'s messages use both styles across different `Check`
  kinds); raises `GeometricAssertionError` (imported from `builder.py`, not
  redefined).

- All 19 mirror functions, each a thin wrapper building the matching
  `ir.Check` and delegating to `_run_assertion`:
  `assert_distinct_points`, `assert_distinct_objects`, `assert_not_collinear`,
  `assert_collinear`, `assert_on`, `assert_not_on`, `assert_parallel`,
  `assert_not_parallel`, `assert_perpendicular`, `assert_right_angle`,
  `assert_angle_equal`, `assert_equal_length`, `assert_distance`,
  `assert_ratio_equal`, `assert_similar_triangles`, `assert_tangent`,
  `assert_opposite_side`, `assert_same_side`, `assert_centroid`.

- Every function takes `*, tol: float | None = None` (except the
  already-final positional args for e.g. `assert_distance(seg, expected, *,
  tol=None)`), and signatures use pydsl handles (`Point`, `Triangle`,
  `AngleRef`, generic linear/circle handles via duck-typed `.id`), not raw
  string ids. `assert_opposite_side`/`assert_same_side` take `Point` handles
  for `line_a`/`line_b` (matching `ir.OppositeSide`/`ir.SameSide`'s actual
  field types — `PointId`, not `LineId` — verified by reading `ir.py`
  directly; the line is defined by two points, not a `Line` object, in this
  particular `ir.Check` kind).

- `assert_right_angle` and `assert_angle_equal` docstrings explicitly note
  the `_candidate_angles_at` hint-search limitation (hints are always empty
  for pydsl-originated checks, since every pydsl point id is
  hidden-prefixed and the hint search filters those out).

- `geometry_diagrams/pydsl/__init__.py`: all 19 functions imported from
  `asserts.py` and appended to `__all__`.

## Testing

New file `tests/test_pydsl_asserts.py`, 45 tests, all passing:

- A pass case and a fail case (raising `GeometricAssertionError`) for each
  of the 19 mirror functions — 38 tests.
- `assert_right_angle`/`assert_angle_equal` docstring-content tests (2),
  confirming the hint-limitation note is present.
- Deferred-point regression tests (2): one calling `assert_on` on an
  `intersection()`-produced point whose `._x`/`._y` were never touched
  before the call (asserted `None` immediately beforehand to prove it),
  one calling `assert_distinct_points` on a `rotate_point()`-produced
  point under the same condition. Both resolve correctly via
  `Builder._advance_sym()` rather than raising a missing-coordinates error.
- Message-content test (1): `assert_distinct_points(point(2,1), point(2,1))`'s
  failure message is asserted to contain `"(2.00, 1.00)"` and not contain
  `"__pydsl_"`.
- `tol` override tests (2): a looser explicit `tol` permits an otherwise-out-
  of-tolerance `assert_distance` to pass; a tighter explicit `tol` still
  fails.

Full suite: `.venv/bin/python -m pytest tests/ -q` → **1886 passed, 48
skipped** (skips are pre-existing/unrelated — model-gated eval tests etc.),
no failures, no regressions.

## TDD evidence

Implementation and the full test file were written together (given the
mechanical 19-function shape, tests were derived directly from each mirror
function's contract rather than written one at a time with a manual
red/green cycle per function). To verify the tests are load-bearing rather
than vacuously green, I ran an explicit mutation check after the fact: I
temporarily reintroduced the exact bug the spec calls out as the
motivating failure mode — passing the caller's (possibly-`None`) `tol` as
`_check_one`'s `default_tol` argument instead of `checks.DEFAULT_TOL`:

```python
result = checks._check_one(check, builder._sym, check.tol)  # mutated
```

This immediately broke 13 of 45 tests with `TypeError: '>' not supported
between instances of 'float' and 'NoneType'` wrapped in
`GeometricAssertionError` (confirming `checks.py`'s broad `except Exception`
at the bottom of `_check_one` does exactly what the spec predicted — turns
a geometrically-correct construction into a false failure), and also broke
the message-content test (the error message became the exception text, not
a coordinate-substituted geometry message). I then reverted the mutation
and confirmed all 45 tests pass again. This is strong evidence the tests
actually exercise the dispatch helper's contract, not just its happy path.

## Refactor notes

Single pass: extracted `_run_assertion` as the one shared helper up front
(all 19 functions are 3-4 lines each, calling it) rather than writing 19
independent implementations and refactoring after. No further refactor
needed — the shape is already "19 thin functions + 1 helper" as requested.

## Files changed

- `geometry_diagrams/pydsl/asserts.py` (new)
- `geometry_diagrams/pydsl/__init__.py` (modified: import + `__all__`)
- `tests/test_pydsl_asserts.py` (new)

## Self-review findings

- All 19 functions exist, are exported via `__all__`, have a pass+fail
  test, and raise `GeometricAssertionError` (verified via
  `pytest.raises(GeometricAssertionError)`, not a bare `ValueError`) with
  coordinate-substituted messages on failure.
- One shared dispatch helper, confirmed via mutation test above to be
  load-bearing (not vacuous).
- Docstrings: first line of every function names its predicate; the two
  angle predicates carry the required hint-limitation note.
- Deferred-point regression test and message-content test are both
  present per the ticket's explicit call-out not to skip them.
- Did not implement `assert_convex`, `assert_ccw`, `assert_in_canvas`,
  `assert_min_distance`, `assert_congruent_triangles`, or the `retry.py`
  classification change — all out of scope for ticket 03 per its own text
  (only the 19 mirrors) and left for tickets 04/05/06.

## Concerns

None. Full suite green, mutation-verified dispatch helper, all acceptance
criteria in the ticket checklist satisfied.

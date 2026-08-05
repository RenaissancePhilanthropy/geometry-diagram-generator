# pydsl Derived Constructions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let pydsl scripts construct intersections, perpendicular/parallel
lines, bisectors, centroids, perpendicular feet, and tangent lines — all
things pydsl scripts cannot do at all today, even though the IR already
supports every one of them.

**Architecture:** Eight new top-level functions in `api.py`, following the
exact `get_builder()` → `builder._add(...)` → return-a-handle pattern every
existing pydsl function already uses. One new data-only handle
(`PerpendicularBisectorLine`, mirroring `Median`'s shape). One narrow,
explicit exception to "no IR changes": `to_sympy.py`'s `LineTangent` pick
handling is missing a `PickClosestTo` case (confirmed by direct testing
during spec review — it silently falls through to an arbitrary tangent
instead of honoring the pick), and needs that case added before
`tangent_line()`'s `near=` parameter can mean anything.

**Tech Stack:** Python, pydantic (IR), pytest (TDD).

## Global Constraints

- No IR schema or renderer changes, with one explicit exception: adding a
  `PickClosestTo` case to `to_sympy.py`'s `LineTangent` pick handling
  (Task 1) — completing an existing-but-incomplete match arm, not adding a
  new `PickRule` variant.
- Only `PickClosestTo` and `PickUpperOfLine`/`PickLowerOfLine` (3 of the
  IR's 13 `PickRule` variants) are exposed, via plain `near`/`side_of`+
  `side` parameters — never the raw `PickRule` union.
- `"left"` maps to `PickUpperOfLine`, `"right"` to `PickLowerOfLine`
  (relative to walking from the first point of `side_of` toward the
  second).
- `intersection()`/`tangent_line()`'s `near`/`side_of`+`side` validation:
  at most one of `near` or (`side_of` and `side` together) may be given;
  `side_of` without `side` (or vice versa) raises `ValueError`
  immediately; an invalid `side` string raises `ValueError` immediately.
- `tangent_line()` requires exactly one of `at`/`from_point` (raises
  `ValueError` immediately if both or neither given) — same
  immediate-validation style as `label_text()`. When `at` is given,
  `near`/`side_of`/`side` are silently ignored (matching the DSL
  lowerer's own `at=` branch, which has no equivalent validation either).
- `perpendicular_bisector()` does NOT auto-draw the base segment between
  its two input points, unlike the DSL's `PerpendicularBisectorOp` —
  consistent with pydsl's existing "nothing renders unless you `draw()`
  it" rule.
- Every function/handle added must be registered in
  `geometry_diagrams/pydsl/__init__.py`'s import line and `__all__` — both
  the stub generator and the sandbox's tool-injection key off `__all__`.
- At least one test must exercise the real sandbox
  (`geometry_diagrams.pydsl.sandbox.run_script`), passing at least one
  disambiguation parameter (e.g. `near=`) by keyword, not just
  positionally.
- Compile-level tests (via `compile_defs()`), not just record-level ones,
  are required for `tangent_line()` and for `side_of`/`side` on both
  `intersection()` and `tangent_line()` — record-level tests alone are
  exactly what let the missing `PickClosestTo` case go unnoticed during
  spec review.

---

### Task 1: Fix `to_sympy.py`'s `LineTangent` to honor `PickClosestTo`

**Files:**
- Modify: `geometry_diagrams/ir/to_sympy.py:334-374` (the `LineTangent`
  case)
- Test: `tests/test_compile_defs.py` (extend)

**Interfaces:**
- Consumes: `ir.PickClosestTo(p: PointId)` (existing IR class, already
  used by `PointIntersection`'s pick handling — this task only extends
  `LineTangent`'s handling to also understand it).
- Produces: `LineTangent` now correctly honors a `PickClosestTo` pick,
  selecting the tangent line whose touch point is closest to the given
  point. Later tasks (`tangent_line()`'s `near=` parameter) depend on this
  working correctly — do not skip ahead of this task.

This task has no pydsl-facing change — it's a compiler bugfix, verified
entirely through `tests/test_compile_defs.py`.

- [ ] **Step 1: Write the failing test proving the current bug**

Append to `tests/test_compile_defs.py` (the file already imports
`PickIndex`, `LineTangent`, `PointFixed`, `CircleCenterRadius`, and has a
`_compile(*stmts, **kwargs)` helper — see the existing
`test_line_tangent` test around line 653 for the exact same circle/point
setup this reuses):

```python
def test_line_tangent_with_pick_closest_to_selects_correct_tangent():
    """Regression test for a real bug found during pydsl derived-constructions
    spec review: LineTangent's pick handling only understood PickIndex and
    PickUpperOfLine/PickLowerOfLine — PickClosestTo silently fell through to
    `case _: return tangents[0]`, always returning SymPy's arbitrary first
    tangent regardless of what the pick asked for."""
    from geometry_diagrams.ir.ir import PickClosestTo

    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=1),
        PointFixed(id="P", x=3, y=0),
        # Two tangent lines from P=(3,0) to the unit circle at O touch at
        # approximately (1/3, +-2*sqrt(2)/3) ~= (0.333, +-0.943).
        PointFixed(id="Q", x=0, y=5),  # far above -> closest touch point is the +y one
        LineTangent(id="t", point="P", circle="c", pick=PickClosestTo(p="Q")),
    )
    tang = sym["t"]
    touch_points = tang.intersection(sym["c"])
    assert len(touch_points) == 1
    touch = touch_points[0]
    assert float(touch.y.evalf()) > 0, (
        f"expected the tangent touching above the x-axis (closest to Q=(0,5)), "
        f"got touch point {touch}"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_compile_defs.py::test_line_tangent_with_pick_closest_to_selects_correct_tangent -v`
Expected: FAIL — either an `AssertionError` on the `touch.y > 0` check
(if SymPy's arbitrary first tangent happens to be the lower one) or the
test happens to pass by luck depending on SymPy's internal ordering. If
it passes by luck, that's not a false negative for this plan — proceed to
Step 3 regardless, since the fix is independently justified and Task 5
depends on it; the important verification is Step 4's pass after the fix
is real (not order-dependent).

- [ ] **Step 3: Add the `PickClosestTo` case**

In `geometry_diagrams/ir/to_sympy.py`, the `LineTangent` case currently
ends with (lines 355-374):

```python
                case ir.PickUpperOfLine(a=a_id, b=b_id) | ir.PickLowerOfLine(a=a_id, b=b_id):
                    a_pt = _resolve(sym, a_id, def_id=did)
                    b_pt = _resolve(sym, b_id, def_id=did)
                    sign_target = 1 if isinstance(pick, ir.PickUpperOfLine) else -1

                    def _touch_point(t_line):
                        pts = t_line.intersection(circle)
                        return pts[0] if pts else None

                    candidates = [
                        t for t in tangents
                        if (tp := _touch_point(t)) is not None
                        and float(_cross_sign(a_pt, b_pt, tp).evalf()) * sign_target > 0
                    ]
                    direction = "upper" if sign_target > 0 else "lower"
                    if not candidates:
                        raise PickError(did, f"no {direction} tangent relative to {a_id}→{b_id}")
                    return candidates[0]
                case _:
                    return tangents[0]
```

Add a `PickClosestTo` case before the `case _:` fallback:

```python
                case ir.PickUpperOfLine(a=a_id, b=b_id) | ir.PickLowerOfLine(a=a_id, b=b_id):
                    a_pt = _resolve(sym, a_id, def_id=did)
                    b_pt = _resolve(sym, b_id, def_id=did)
                    sign_target = 1 if isinstance(pick, ir.PickUpperOfLine) else -1

                    def _touch_point(t_line):
                        pts = t_line.intersection(circle)
                        return pts[0] if pts else None

                    candidates = [
                        t for t in tangents
                        if (tp := _touch_point(t)) is not None
                        and float(_cross_sign(a_pt, b_pt, tp).evalf()) * sign_target > 0
                    ]
                    direction = "upper" if sign_target > 0 else "lower"
                    if not candidates:
                        raise PickError(did, f"no {direction} tangent relative to {a_id}→{b_id}")
                    return candidates[0]
                case ir.PickClosestTo(p=p_id):
                    ref_pt = _resolve(sym, p_id, def_id=did)

                    def _touch_point_2(t_line):
                        pts = t_line.intersection(circle)
                        return pts[0] if pts else None

                    scored = [
                        (tp.distance(ref_pt), t)
                        for t in tangents
                        if (tp := _touch_point_2(t)) is not None
                    ]
                    if not scored:
                        raise PickError(did, f"no tangent line has a resolvable touch point")
                    scored.sort(key=lambda pair: float(pair[0].evalf()))
                    return scored[0][1]
                case _:
                    return tangents[0]
```

(The inner helper is named `_touch_point_2` rather than reusing
`_touch_point` from the sibling `case` above purely because both are
locally-scoped closures inside the same `match` block, each attached to
its own case — Python allows this, but give it a distinct name so
there's no ambiguity about which `case` it belongs to when reading the
diff.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_compile_defs.py::test_line_tangent_with_pick_closest_to_selects_correct_tangent -v`
Expected: PASS.

- [ ] **Step 5: Run the full `to_sympy` test suite to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/test_compile_defs.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/ir/to_sympy.py tests/test_compile_defs.py
git commit -m "fix: honor PickClosestTo in LineTangent's pick handling"
```

---

### Task 2: Five direct 1:1-wrap functions

**Files:**
- Modify: `geometry_diagrams/pydsl/api.py` (add 5 functions)
- Modify: `geometry_diagrams/pydsl/__init__.py` (register all 5)
- Test: `tests/test_pydsl_derived_constructions.py` (new file)

**Interfaces:**
- Consumes: `get_builder()`, `Builder._add()`, `Builder._fresh_hidden_id()`
  (existing); `Point`, `Line`, `Triangle` handles (existing).
- Produces: `perpendicular_through(point: Point, line) -> Line`,
  `parallel_through(point: Point, line) -> Line`,
  `angle_bisector(vertex: Point, toward1: Point, toward2: Point) -> Line`,
  `centroid(t: Triangle) -> Point`,
  `foot_of_perpendicular(point: Point, line) -> Point`. Later tasks don't
  depend on these directly, but Task 6's sandbox test uses
  `perpendicular_through`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pydsl_derived_constructions.py`:

```python
# tests/test_pydsl_derived_constructions.py
"""Tests for pydsl derived-construction primitives: intersection(),
perpendicular_through(), parallel_through(), perpendicular_bisector(),
angle_bisector(), centroid(), foot_of_perpendicular(), tangent_line().
All wrap IR DefStmt kinds that already exist and are already compiled by
to_sympy.py — the recipe DSL already exposes equivalent ops for all eight,
confirming the composition each one needs."""
import pytest

from geometry_diagrams.pydsl.api import (
    angle_bisector, centroid, foot_of_perpendicular, line_through,
    parallel_through, perpendicular_through, point, triangle,
)
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.ir.ir import (
    LineAngleBisector, LineParallelThrough, LinePerpendicularThrough,
    PointFoot, PointTriangleCenter,
)


def test_perpendicular_through_records_line_perpendicular_through():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        base = line_through(a, b)
        p = point(2, 5)
        result = perpendicular_through(p, base)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, LinePerpendicularThrough) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].through == p.id
    assert defs[0].to_line == base.id


def test_parallel_through_records_line_parallel_through():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        base = line_through(a, b)
        p = point(2, 5)
        result = parallel_through(p, base)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, LineParallelThrough) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].through == p.id
    assert defs[0].to_line == base.id


def test_angle_bisector_records_line_angle_bisector_with_correct_field_mapping():
    with new_builder_context() as builder:
        vertex = point(0, 0)
        toward1 = point(1, 1)
        toward2 = point(1, -1)
        result = angle_bisector(vertex, toward1, toward2)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, LineAngleBisector) and d.id == result.id]
    assert len(defs) == 1
    # toward1 -> a, toward2 -> b (matches recipe/lower.py's ray1_toward->a, ray2_toward->b)
    assert defs[0].a == toward1.id
    assert defs[0].vertex == vertex.id
    assert defs[0].b == toward2.id


def test_centroid_records_point_triangle_center_which_centroid():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        result = centroid(t)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointTriangleCenter) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].tri == t.id
    assert defs[0].which == "centroid"


def test_foot_of_perpendicular_records_point_foot():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        base = line_through(a, b)
        p = point(2, 5)
        result = foot_of_perpendicular(p, base)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointFoot) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].source == p.id
    assert defs[0].onto == base.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -v`
Expected: FAIL — `ImportError` (none of the 5 functions exist yet).

- [ ] **Step 3: Add the top-level IR imports needed**

In `geometry_diagrams/pydsl/api.py`, change the existing import line
(line 8):

```python
from geometry_diagrams.ir.ir import AnglePoints, CircleCenterRadius, Draw, DrawPoints, LinePerpendicularThrough, LineThrough, MarkAngles, PointDilate, PointFixed, PointFoot, PointMidpoint, PointOn, PointOnParam, PointReflect, PointRotate, PointTriangleCenter
```

to (adding `LineAngleBisector` and `LineParallelThrough` in alphabetical
position):

```python
from geometry_diagrams.ir.ir import AnglePoints, CircleCenterRadius, Draw, DrawPoints, LineAngleBisector, LineParallelThrough, LinePerpendicularThrough, LineThrough, MarkAngles, PointDilate, PointFixed, PointFoot, PointMidpoint, PointOn, PointOnParam, PointReflect, PointRotate, PointTriangleCenter
```

- [ ] **Step 4: Implement the five functions**

Add to `geometry_diagrams/pydsl/api.py`, after `dilate_point()` and
before `draw()`:

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

Note: the parameter name `point` shadows the module-level `point()`
function within each function body — this is fine (matches the pattern
already used by `median()`/`altitude()`'s `from_vertex` parameter not
colliding with anything, and by `point`/`line` never being called from
inside these bodies), but do not rename the module-level `point()`
function to work around it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -v`
Expected: all 5 PASS.

- [ ] **Step 6: Register all five in `pydsl/__init__.py`**

Change the import line from:

```python
from geometry_diagrams.pydsl.api import altitude, canvas, circumcircle, dilate_point, draw, draw_points, incircle, label_text, line_through, mark_angle, median, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
```

to:

```python
from geometry_diagrams.pydsl.api import altitude, angle_bisector, canvas, centroid, circumcircle, dilate_point, draw, draw_points, foot_of_perpendicular, incircle, label_text, line_through, mark_angle, median, parallel_through, perpendicular_through, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
```

and add all five to `__all__`, in this exact list (order doesn't matter
functionally, but keep it roughly alphabetical among the other
constructors, after `altitude`):

```python
__all__ = [
    "point",
    "line_through",
    "triangle",
    "polygon",
    "segment",
    "circumcircle",
    "incircle",
    "median",
    "altitude",
    "angle_bisector",
    "centroid",
    "foot_of_perpendicular",
    "parallel_through",
    "perpendicular_through",
    "canvas",
    "mark_angle",
    "draw",
    "draw_points",
    "label_text",
    "point_on",
    "rotate_point",
    "reflect_point",
    "dilate_point",
    "Point",
    "Line",
    "Segment",
    "Triangle",
    "Polygon",
    "Circle",
    "Median",
    "Altitude",
    "AngleRef",
]
```

- [ ] **Step 7: Run the pydsl test suite to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py tests/test_pydsl_labels.py tests/test_pydsl_canvas.py tests/test_pydsl_end_to_end.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_derived_constructions.py
git commit -m "feat: add perpendicular_through, parallel_through, angle_bisector, centroid, foot_of_perpendicular"
```

---

### Task 3: `perpendicular_bisector()` and `PerpendicularBisectorLine`

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py` (add `PerpendicularBisectorLine`)
- Modify: `geometry_diagrams/pydsl/api.py` (add `perpendicular_bisector()`)
- Modify: `geometry_diagrams/pydsl/stub.py` (register the handle)
- Modify: `geometry_diagrams/pydsl/__init__.py` (register both)
- Test: `tests/test_pydsl_derived_constructions.py` (extend)

**Interfaces:**
- Consumes: `LineThrough`, `PointMidpoint`, `LinePerpendicularThrough`
  (existing IR); `Point`, `Line` handles (existing).
- Produces: `PerpendicularBisectorLine` handle (`id: str`, `midpoint:
  Point`, no `_builder` field — it has no methods, so it needs none, the
  same reason `Median`/`Altitude`/`Line` have none);
  `perpendicular_bisector(p: Point, q: Point) -> PerpendicularBisectorLine`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pydsl_derived_constructions.py`:

```python
from geometry_diagrams.pydsl.api import perpendicular_bisector
from geometry_diagrams.ir.ir import Draw, DrawPoints, PointMidpoint


def test_perpendicular_bisector_composes_three_defs_in_dependency_order():
    with new_builder_context() as builder:
        p, q = point(0, 0), point(4, 0)
        result = perpendicular_bisector(p, q)
        ir = builder.build()
    kinds_in_order = [d.kind for d in ir.define]
    # p, q are point_fixed; then base line_through, then point_midpoint,
    # then line_perp_through, in that dependency order.
    assert kinds_in_order[-3:] == ["line_through", "point_midpoint", "line_perp_through"]
    assert ir.define[-1].id == result.id


def test_perpendicular_bisector_midpoint_accessor():
    with new_builder_context() as builder:
        p, q = point(0, 0), point(4, 0)
        result = perpendicular_bisector(p, q)
        ir = builder.build()
    mid_defs = [d for d in ir.define if isinstance(d, PointMidpoint)]
    assert len(mid_defs) == 1
    assert result.midpoint.id == mid_defs[0].id
    assert mid_defs[0].p == p.id
    assert mid_defs[0].q == q.id


def test_perpendicular_bisector_does_not_auto_draw():
    """Non-goal regression guard: unlike the DSL's PerpendicularBisectorOp,
    pydsl's perpendicular_bisector() must not auto-draw a base segment."""
    with new_builder_context() as builder:
        p, q = point(0, 0), point(4, 0)
        perpendicular_bisector(p, q)
        ir = builder.build()
    assert not any(isinstance(r, (Draw, DrawPoints)) for r in ir.render)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py::test_perpendicular_bisector_composes_three_defs_in_dependency_order tests/test_pydsl_derived_constructions.py::test_perpendicular_bisector_midpoint_accessor tests/test_pydsl_derived_constructions.py::test_perpendicular_bisector_does_not_auto_draw -v`
Expected: FAIL — `ImportError: cannot import name 'perpendicular_bisector'`.

- [ ] **Step 3: Add `PerpendicularBisectorLine` to `handles.py`**

Add to `geometry_diagrams/pydsl/handles.py`, after the `Altitude` class
(the last class in the file):

```python
@dataclass(frozen=True)
class PerpendicularBisectorLine:
    id: str
    midpoint: Point
```

- [ ] **Step 4: Implement `perpendicular_bisector()` in `api.py`**

Add `PerpendicularBisectorLine` to the existing handles import line:

```python
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Circle, Line, Median, PerpendicularBisectorLine, Point, Polygon, Segment, Triangle
```

Add the function itself, after `foot_of_perpendicular()`:

```python
def perpendicular_bisector(p: Point, q: Point) -> PerpendicularBisectorLine:
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

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -v`
Expected: all PASS.

- [ ] **Step 6: Register in `stub.py`'s `_HANDLE_CLASS_NAMES`**

In `geometry_diagrams/pydsl/stub.py`, change:

```python
_HANDLE_CLASS_NAMES = {"Point", "Line", "Segment", "Triangle", "Polygon", "Circle",
                        "Altitude", "Median", "AngleRef"}
```

to:

```python
_HANDLE_CLASS_NAMES = {"Point", "Line", "Segment", "Triangle", "Polygon", "Circle",
                        "Altitude", "Median", "AngleRef", "PerpendicularBisectorLine"}
```

- [ ] **Step 7: Write and run a stub-generation test**

Append to `tests/test_pydsl_derived_constructions.py`:

```python
def test_perpendicular_bisector_line_appears_in_stub():
    from geometry_diagrams.pydsl.stub import generate_stub

    stub_text = generate_stub()
    assert "class PerpendicularBisectorLine:" in stub_text
    assert "midpoint: Point" in stub_text
```

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py::test_perpendicular_bisector_line_appears_in_stub -v`
Expected: FAIL until `PerpendicularBisectorLine` is also registered in
`pydsl/__init__.py` (Step 8) — `generate_stub()` iterates
`pydsl_module.__all__`, so the class must be exported there too, not only
added to `_HANDLE_CLASS_NAMES`.

- [ ] **Step 8: Register `perpendicular_bisector` and `PerpendicularBisectorLine` in `pydsl/__init__.py`**

Change the import lines to:

```python
from geometry_diagrams.pydsl.api import altitude, angle_bisector, canvas, centroid, circumcircle, dilate_point, draw, draw_points, foot_of_perpendicular, incircle, label_text, line_through, mark_angle, median, parallel_through, perpendicular_bisector, perpendicular_through, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Circle, Line, Median, PerpendicularBisectorLine, Point, Polygon, Segment, Triangle
```

and add both to `__all__` (after `perpendicular_through`, and after
`Median` respectively):

```python
__all__ = [
    "point",
    "line_through",
    "triangle",
    "polygon",
    "segment",
    "circumcircle",
    "incircle",
    "median",
    "altitude",
    "angle_bisector",
    "centroid",
    "foot_of_perpendicular",
    "parallel_through",
    "perpendicular_bisector",
    "perpendicular_through",
    "canvas",
    "mark_angle",
    "draw",
    "draw_points",
    "label_text",
    "point_on",
    "rotate_point",
    "reflect_point",
    "dilate_point",
    "Point",
    "Line",
    "Segment",
    "Triangle",
    "Polygon",
    "Circle",
    "Median",
    "PerpendicularBisectorLine",
    "Altitude",
    "AngleRef",
]
```

- [ ] **Step 9: Run the full test file to confirm the stub test now passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -v`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add geometry_diagrams/pydsl/handles.py geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/stub.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_derived_constructions.py
git commit -m "feat: add perpendicular_bisector() and PerpendicularBisectorLine handle"
```

---

### Task 4: `intersection()`

**Files:**
- Modify: `geometry_diagrams/pydsl/api.py` (add `intersection()`)
- Modify: `geometry_diagrams/pydsl/__init__.py` (register)
- Test: `tests/test_pydsl_derived_constructions.py` (extend)

**Interfaces:**
- Consumes: `PointIntersection`, `PickClosestTo`, `PickUpperOfLine`,
  `PickLowerOfLine` (existing IR).
- Produces: `intersection(obj1, obj2, near=None, side_of=None, side=None)
  -> Point`. Task 5's `tangent_line()` reuses the identical
  near/side_of/side validation shape (copy the pattern, not the code —
  each function validates its own parameters independently, matching how
  `label_text()`'s exactly-one-of check isn't shared code either).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pydsl_derived_constructions.py`:

```python
from geometry_diagrams.pydsl.api import intersection
from geometry_diagrams.ir.ir import PickClosestTo, PickLowerOfLine, PickUpperOfLine, PointIntersection


def test_intersection_no_pick_records_pick_none():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        result = intersection(l1, l2)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointIntersection) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].obj1 == l1.id
    assert defs[0].obj2 == l2.id
    assert defs[0].pick is None


def test_intersection_near_records_pick_closest_to():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        ref = point(10, 10)
        result = intersection(l1, l2, near=ref)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointIntersection) and d.id == result.id]
    assert isinstance(defs[0].pick, PickClosestTo)
    assert defs[0].pick.p == ref.id


def test_intersection_side_left_records_pick_upper_of_line():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        s1, s2 = point(0, 0), point(1, 0)
        result = intersection(l1, l2, side_of=(s1, s2), side="left")
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointIntersection) and d.id == result.id]
    assert isinstance(defs[0].pick, PickUpperOfLine)
    assert defs[0].pick.a == s1.id
    assert defs[0].pick.b == s2.id


def test_intersection_side_right_records_pick_lower_of_line():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        s1, s2 = point(0, 0), point(1, 0)
        result = intersection(l1, l2, side_of=(s1, s2), side="right")
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointIntersection) and d.id == result.id]
    assert isinstance(defs[0].pick, PickLowerOfLine)


def test_intersection_near_and_side_of_together_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        ref = point(10, 10)
        s1, s2 = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="at most one"):
            intersection(l1, l2, near=ref, side_of=(s1, s2), side="left")


def test_intersection_side_of_without_side_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        s1, s2 = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="together"):
            intersection(l1, l2, side_of=(s1, s2))


def test_intersection_side_without_side_of_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        with pytest.raises(ValueError, match="together"):
            intersection(l1, l2, side="left")


def test_intersection_invalid_side_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        s1, s2 = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="left.*right"):
            intersection(l1, l2, side_of=(s1, s2), side="up")


def test_intersection_numeric_result_matches_hand_computed_crossing():
    """Compile-level check: two lines through literal points crossing at a
    hand-computable point — proves the pydsl call reaches correct geometry,
    not just records a plausible-looking def."""
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)   # y = x
        c, d = point(0, 4), point(4, 0)   # y = 4 - x
        l1, l2 = line_through(a, b), line_through(c, d)
        result = intersection(l1, l2)
        ir = builder.build()
    sym = compile_defs(ir)
    pt = sym[result.id]
    assert float(pt.x.evalf()) == pytest.approx(2.0)
    assert float(pt.y.evalf()) == pytest.approx(2.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -k intersection -v`
Expected: FAIL — `ImportError: cannot import name 'intersection'`.

- [ ] **Step 3: Implement `intersection()`**

Add to `geometry_diagrams/pydsl/api.py`, after `perpendicular_bisector()`:

```python
def intersection(
    obj1,
    obj2,
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -k intersection -v`
Expected: all PASS.

- [ ] **Step 5: Register `intersection` in `pydsl/__init__.py`**

Add `intersection` to the import line and `__all__` (after `incircle`,
before `line_through`, matching the existing alphabetical-ish grouping —
see how `label_text` was placed relative to `line_through` in an earlier
task):

```python
from geometry_diagrams.pydsl.api import altitude, angle_bisector, canvas, centroid, circumcircle, dilate_point, draw, draw_points, foot_of_perpendicular, incircle, intersection, label_text, line_through, mark_angle, median, parallel_through, perpendicular_bisector, perpendicular_through, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
```

```python
    "incircle",
    "intersection",
    "median",
```

- [ ] **Step 6: Run the full test file to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_derived_constructions.py
git commit -m "feat: add intersection() with near/side_of/side disambiguation"
```

---

### Task 5: `tangent_line()`

**Files:**
- Modify: `geometry_diagrams/pydsl/api.py` (add `tangent_line()`)
- Modify: `geometry_diagrams/pydsl/__init__.py` (register)
- Test: `tests/test_pydsl_derived_constructions.py` (extend)

**Interfaces:**
- Consumes: `LineTangent` (existing IR, now correctly honoring
  `PickClosestTo` per Task 1 — this task would ship a silently-broken
  `near=` parameter without Task 1 complete); `Circle.center` (existing
  `Point` handle field).
- Produces: `tangent_line(circle, at=None, from_point=None, near=None,
  side_of=None, side=None) -> Line`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pydsl_derived_constructions.py`:

```python
from geometry_diagrams.pydsl.api import circumcircle, tangent_line
from geometry_diagrams.ir.ir import LinePerpendicularThrough, LineTangent, LineThrough


def test_tangent_line_at_point_on_circle_composes_two_defs():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(2, 3)
        t = triangle(a, b, c)
        circ = circumcircle(t)
        result = tangent_line(circ, at=a)
        ir = builder.build()
    radius_defs = [d for d in ir.define if isinstance(d, LineThrough) and d.p == circ.center.id and d.q == a.id]
    assert len(radius_defs) == 1
    perp_defs = [d for d in ir.define if isinstance(d, LinePerpendicularThrough) and d.id == result.id]
    assert len(perp_defs) == 1
    assert perp_defs[0].through == a.id
    assert perp_defs[0].to_line == radius_defs[0].id


def test_tangent_line_from_point_no_pick_records_pick_none():
    with new_builder_context() as builder:
        circ_center = point(0, 0)
        far = point(3, 4)
        from geometry_diagrams.ir.ir import CircleCenterRadius
        builder._add(CircleCenterRadius(id="c1", center=circ_center.id, radius=1.0))
        from geometry_diagrams.pydsl.handles import Circle
        circ = Circle(id="c1", center=circ_center, _radius_thunk=lambda: 1.0)
        result = tangent_line(circ, from_point=far)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, LineTangent) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].point == far.id
    assert defs[0].circle == "c1"
    assert defs[0].pick is None


def test_tangent_line_requires_exactly_one_of_at_or_from_point():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(2, 3)
        t = triangle(a, b, c)
        circ = circumcircle(t)
        with pytest.raises(ValueError, match="exactly one"):
            tangent_line(circ)
        with pytest.raises(ValueError, match="exactly one"):
            tangent_line(circ, at=a, from_point=b)


def test_tangent_line_from_point_near_and_side_of_validation_matches_intersection():
    with new_builder_context() as builder:
        origin = point(0, 0)
        from geometry_diagrams.ir.ir import CircleCenterRadius
        builder._add(CircleCenterRadius(id="c1", center=origin.id, radius=1.0))
        from geometry_diagrams.pydsl.handles import Circle
        circ = Circle(id="c1", center=origin, _radius_thunk=lambda: 1.0)
        far = point(3, 0)
        ref = point(0, 5)
        s1, s2 = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="at most one"):
            tangent_line(circ, from_point=far, near=ref, side_of=(s1, s2), side="left")
        with pytest.raises(ValueError, match="together"):
            tangent_line(circ, from_point=far, side_of=(s1, s2))
        with pytest.raises(ValueError, match="left.*right"):
            tangent_line(circ, from_point=far, side_of=(s1, s2), side="up")


def test_tangent_line_from_point_no_pick_two_tangents_raises_at_compile_time():
    """Documented asymmetry with intersection(): unlike PointIntersection's
    arbitrary auto-pick fallback, LineTangent with no pick and >1 candidate
    raises PickError at compile time, not ValueError at record time."""
    from geometry_diagrams.ir.errors import PickError
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        origin = point(0, 0)
        from geometry_diagrams.ir.ir import CircleCenterRadius
        builder._add(CircleCenterRadius(id="c1", center=origin.id, radius=1.0))
        from geometry_diagrams.pydsl.handles import Circle
        circ = Circle(id="c1", center=origin, _radius_thunk=lambda: 1.0)
        far = point(3, 0)
        tangent_line(circ, from_point=far)  # no pick -> ambiguous (2 tangents)
        ir = builder.build()
    with pytest.raises(PickError):
        compile_defs(ir)


def test_tangent_line_near_selects_geometrically_correct_tangent():
    """Compile-level proof that near= actually works end to end (this is the
    exact case that was silently broken before Task 1's to_sympy.py fix)."""
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        origin = point(0, 0)
        from geometry_diagrams.ir.ir import CircleCenterRadius
        builder._add(CircleCenterRadius(id="c1", center=origin.id, radius=1.0))
        from geometry_diagrams.pydsl.handles import Circle
        circ = Circle(id="c1", center=origin, _radius_thunk=lambda: 1.0)
        far = point(3, 0)
        ref = point(0, 5)  # far above -> nearer to the +y touch point
        result = tangent_line(circ, from_point=far, near=ref)
        ir = builder.build()
    sym = compile_defs(ir)
    tang = sym[result.id]
    touch_points = tang.intersection(sym["c1"])
    assert len(touch_points) == 1
    assert float(touch_points[0].y.evalf()) > 0


def test_tangent_line_side_left_vs_right_select_opposite_tangents():
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        origin = point(0, 0)
        from geometry_diagrams.ir.ir import CircleCenterRadius
        builder._add(CircleCenterRadius(id="c1", center=origin.id, radius=1.0))
        from geometry_diagrams.pydsl.handles import Circle
        circ = Circle(id="c1", center=origin, _radius_thunk=lambda: 1.0)
        far = point(3, 0)
        s1, s2 = point(0, 0), point(1, 0)  # directed +x axis: "left" = +y side
        left_result = tangent_line(circ, from_point=far, side_of=(s1, s2), side="left")
        right_result = tangent_line(circ, from_point=far, side_of=(s1, s2), side="right")
        ir = builder.build()
    sym = compile_defs(ir)
    left_touch = sym[left_result.id].intersection(sym["c1"])[0]
    right_touch = sym[right_result.id].intersection(sym["c1"])[0]
    assert float(left_touch.y.evalf()) > 0
    assert float(right_touch.y.evalf()) < 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -k tangent_line -v`
Expected: FAIL — `ImportError: cannot import name 'tangent_line'`.

- [ ] **Step 3: Implement `tangent_line()`**

Add to `geometry_diagrams/pydsl/api.py`, after `intersection()`:

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
      unambiguous — near/side_of/side are silently ignored if also given,
      matching the DSL lowerer's own at= branch, which has no equivalent
      validation either).
    - from_point=P — P is external to the circle; there are 0, 1, or 2
      tangent lines from an external point. Disambiguate a 2-tangent case
      with near=Q (closest touch point to Q) or side_of=(A,B), side=
      "left"|"right" (same convention as intersection()). With neither,
      and 2 tangent lines exist, unlike intersection() there is no
      arbitrary-heuristic fallback — compilation fails later, inside
      compile_defs(), with geometry_diagrams.ir.errors.PickError."""
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py -k tangent_line -v`
Expected: all PASS. If `test_tangent_line_near_selects_geometrically_correct_tangent`
fails, that specifically means Task 1's `to_sympy.py` fix is missing or
incomplete — do not patch around it here, go back and verify Task 1.

- [ ] **Step 5: Register `tangent_line` in `pydsl/__init__.py`**

Add `tangent_line` to the import line (after `segment`, before
`triangle`) and to `__all__` (after `segment`):

```python
from geometry_diagrams.pydsl.api import altitude, angle_bisector, canvas, centroid, circumcircle, dilate_point, draw, draw_points, foot_of_perpendicular, incircle, intersection, label_text, line_through, mark_angle, median, parallel_through, perpendicular_bisector, perpendicular_through, point, point_on, polygon, reflect_point, rotate_point, segment, tangent_line, triangle
```

```python
    "segment",
    "tangent_line",
    "circumcircle",
```

- [ ] **Step 6: Run the full test file and the pydsl suite to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py tests/test_pydsl_labels.py tests/test_pydsl_canvas.py tests/test_pydsl_end_to_end.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_derived_constructions.py
git commit -m "feat: add tangent_line() with near/side_of/side disambiguation"
```

---

### Task 6: Sandbox integration test and instructions doc

**Files:**
- Test: `tests/test_pydsl_derived_constructions.py` (extend — sandbox-path test)
- Modify: `geometry_diagrams/strategies/instructions_python_full.py:24-59`

**Interfaces:**
- Consumes: every function from Tasks 2-5.
- Produces: nothing new for later tasks — this is the plan's final,
  wrap-up task.

- [ ] **Step 1: Write the failing sandbox-path test**

Append to `tests/test_pydsl_derived_constructions.py`:

```python
def test_derived_constructions_work_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script
    from geometry_diagrams.ir.ir import PickClosestTo, PointIntersection

    script = (
        "a = point(0, 0)\n"
        "b = point(4, 4)\n"
        "c = point(0, 4)\n"
        "d = point(4, 0)\n"
        "l1 = line_through(a, b)\n"
        "l2 = line_through(c, d)\n"
        "ref = point(10, 10)\n"
        "p = intersection(l1, l2, near=ref)\n"
        "perp = perpendicular_through(p, l1)\n"
        "draw(l1)\n"
        "draw(l2)\n"
        "draw(perp)\n"
        "draw_points(a, b, c, d, p)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    isect_defs = [d for d in result.diagram_ir.define if isinstance(d, PointIntersection)]
    assert len(isect_defs) == 1
    assert isinstance(isect_defs[0].pick, PickClosestTo)
```

- [ ] **Step 2: Run it to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py::test_derived_constructions_work_through_the_real_sandbox -v`
Expected: PASS already, since Tasks 1-5 are complete by this point in the
plan — this step is a direct confirmation, not a red-then-green cycle. If
it fails, treat it as a signal that an earlier task's `__all__`
registration is incomplete — do not patch around it here.

- [ ] **Step 3: Add the Rules bullet**

In `geometry_diagrams/strategies/instructions_python_full.py`'s `##
Rules` section, add one bullet immediately after the `canvas(...)` bullet
(the one starting `- Call \`canvas(x_range=...`):

```python
- Use `intersection(obj1, obj2)` for where two lines/segments/rays/circles
  cross, `perpendicular_through(point, line)` / `parallel_through(point,
  line)` for a standalone perpendicular/parallel line, `perpendicular_bisector(p, q)`
  (its `.midpoint` accessor gives the midpoint), `angle_bisector(vertex,
  toward1, toward2)`, `centroid(triangle)`, `foot_of_perpendicular(point, line)`,
  and `tangent_line(circle, at=P)` (P on the circle) or
  `tangent_line(circle, from_point=P)` (P external). When a construction
  has more than one valid answer (a line crossing a circle twice, two
  tangent lines from an external point), disambiguate with `near=Q` (the
  candidate closest to Q) or `side_of=(A, B), side="left"` /`"right"` (the
  candidate on that side of the directed line from A to B) — e.g.
  `intersection(line1, circle, near=approx_point)` or
  `tangent_line(circle, from_point=p, side_of=(p, circle.center), side="left")`.
  Without one of these, an ambiguous construction may pick an unexpected
  candidate (or fail outright for `tangent_line`) — always disambiguate
  when there's more than one geometrically valid answer.
```

- [ ] **Step 4: Run the full pydsl + strategy test suite**

Run: `.venv/bin/python -m pytest tests/test_pydsl_derived_constructions.py tests/test_pydsl_labels.py tests/test_pydsl_canvas.py tests/test_pydsl_end_to_end.py tests/test_python_full_strategy.py tests/test_compile_defs.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_pydsl_derived_constructions.py geometry_diagrams/strategies/instructions_python_full.py
git commit -m "test: add sandbox coverage for derived constructions; document in prompt"
```

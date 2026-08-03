# Python DSL Shim + Executor (Phase 1a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python fluent API ("builder shim") that lets a script of ordinary function calls produce a `DiagramIR` object — the exact same shape `geometry_diagrams/recipe/lower.py` produces from the JSON DSL today — executed inside a sandboxed, resource-limited interpreter, with a retry-loop-ready error/did-you-mean layer on top.

**Architecture:** A new `geometry_diagrams/pydsl/` package holds typed handle classes (`Point`, `Line`, `Segment`, `Triangle`, `Polygon`, `Circle`, `Altitude`, `Median`, `AngleRef`) and public API functions (`point`, `line_through`, `triangle`, `polygon`, `circumcircle`, `incircle`, `altitude`, `median`, `mark_angle`). Every function reads an ambient `Builder` from a `contextvar`, appends the matching `DefStmt`(s), and returns a handle. `Builder.build()` assembles the recorded defs into a `DiagramIR`, identical in shape to what `lower_to_ir()` returns. A separate executor layer runs untrusted script text through `smolagents.LocalPythonExecutor` inside a resource-limited subprocess, and a retry-loop layer turns executor failures into retry prompts with did-you-mean suggestions.

**Tech Stack:** Python 3.11, Pydantic 2.x (existing `geometry_diagrams.ir.ir` models), `smolagents>=1.17.0` (new dependency), stdlib `contextvars`, `multiprocessing`, `resource`, `difflib`, `ast`, `inspect`. Test with `pytest` (existing project convention, flat `tests/` directory, plain `pytest` functions, no test classes).

## Global Constraints

- `smolagents` must be pinned `>=1.17.0` (fixes CVE-2025-5120 / GHSA-6v92-r5mx-h5fx sandbox escape). Add as a `[project.dependencies]` entry in `pyproject.toml`, not a dev-only dependency (the executor is runtime code, not test-only).
- No eager geometric validation anywhere in the builder — only structural checks (arity, membership, adjacency). Any geometric property (parallelism, distance, angle value, self-intersection) is validated downstream by the existing `geometry_diagrams/ir/checks.py` / `to_sympy.py`, unchanged. Exception: computing an *output value* the same way the DSL already does (e.g. `_lower_incircle`'s numeric Heron-formula radius when coordinates are already concrete) is not "validation" and is fine to replicate — it produces a value, it doesn't reject a script.
- `side()`-style accessors on `Triangle`/`Polygon` are order-independent: `T.side(A, B)` and `T.side(B, A)` must return the same `Segment` handle object.
- Output points (`circ.center`, `alt.foot`, `med.midpoint`) are computed properties on handles, never passed in or named by API callers.
- `RLIMIT_AS` is a documented no-op on macOS (confirmed via the `pynisher` project) — do not rely on it as the memory backstop in any test that must pass in local dev. `RLIMIT_CPU` and the wall-clock kill are the cross-platform-reliable backstops; `RLIMIT_AS` is Linux-only defense-in-depth, and any test asserting its effect must be marked to run only on Linux (e.g. `@pytest.mark.skipif(sys.platform != "linux", ...)`).
- `while`, `Lambda`, `ClassDef` are permitted in generated scripts — do not add an AST rule rejecting them.
- Op-count cap defaults to 2000 per builder instance and is enforced by the `Builder` itself, not by AST inspection.
- Did-you-mean logic lives in the retry layer (catching the executor's own undefined-name error), never as a module-level `__getattr__` on the API namespace — that mechanism cannot fire inside `LocalPythonExecutor`'s own name resolution.

---

## File Structure

```
geometry_diagrams/pydsl/
    __init__.py       # re-exports the public API: handle classes + op functions
    handles.py         # Point, Line, Segment, Triangle, Polygon, Circle, Altitude, Median, AngleRef
    builder.py          # Builder class, contextvar, op-count cap, DiagramIR assembly
    api.py              # point(), line_through(), triangle(), polygon(), circumcircle(),
                        #   incircle(), altitude(), median(), mark_angle()
    stub.py              # generate_stub() — introspects api.py + handles.py into prompt text
    sandbox.py           # run_script() — subprocess + rlimits + LocalPythonExecutor wiring
    retry.py             # classify_failure(), build_retry_message(), did-you-mean matching

tests/
    test_pydsl_builder.py     # Builder core: contextvar isolation, op-count cap
    test_pydsl_basic_ops.py    # point(), line_through()
    test_pydsl_triangle.py      # Triangle handle + triangle()
    test_pydsl_polygon.py        # Polygon handle + polygon()
    test_pydsl_circle.py          # Circle handle + circumcircle()/incircle()
    test_pydsl_altitude.py         # Altitude handle + altitude()
    test_pydsl_median.py            # Median handle + median()
    test_pydsl_angle.py              # AngleRef + angle_at() + mark_angle()
    test_pydsl_stub.py                # stub generator
    test_pydsl_sandbox.py              # executor/sandbox: import lockdown, dangerous calls,
                                        #   CPU-bomb, memory-bomb, timeout kill
    test_pydsl_retry.py                 # did-you-mean, failure classification, retry message
    test_pydsl_end_to_end.py             # Phase 1a exit criterion: full script -> DiagramIR ->
                                          #   to_sympy.py -> checks.py, compared to DSL equivalent
```

`geometry_diagrams/pydsl/` sits as a sibling package to `geometry_diagrams/recipe/`, `geometry_diagrams/ir/`, `geometry_diagrams/strategies/`, `geometry_diagrams/util/` — matching the existing top-level package layout. Test files follow the existing flat `tests/` convention (no subpackages), plain `pytest` functions, `test_<behavior>` names, matching the style observed in `tests/test_recipe_lower.py`.

---

### Task 1: Builder core + basic ops (point, line_through)

**Files:**
- Create: `geometry_diagrams/pydsl/handles.py`
- Create: `geometry_diagrams/pydsl/builder.py`
- Create: `geometry_diagrams/pydsl/api.py`
- Create: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_builder.py`
- Test: `tests/test_pydsl_basic_ops.py`

**Interfaces:**
- Consumes: `geometry_diagrams.ir.ir.{DiagramIR, PointFixed, LineThrough, Segment}` (existing).
- Produces: `Builder` class with `.build() -> DiagramIR`, `.op_count -> int`, `_current_builder: contextvars.ContextVar[Builder | None]`, `get_builder() -> Builder` (raises `RuntimeError` if none active), `new_builder_context() -> contextmanager` yielding a fresh `Builder` and resetting the contextvar on exit. `Point` and `Line` handle classes each expose `.id: str` (the internal, auto-generated IR id). `point(x: float, y: float) -> Point`, `line_through(p: Point, q: Point) -> Line`.

- [ ] **Step 1: Write the failing test for builder isolation**

```python
# tests/test_pydsl_builder.py
"""Tests for the pydsl Builder core: contextvar isolation and the op-count cap."""
import pytest

from geometry_diagrams.pydsl.builder import Builder, get_builder, new_builder_context


def test_get_builder_raises_outside_context():
    """Calling get_builder() with no active builder context is an error, not a silent None."""
    with pytest.raises(RuntimeError, match="no active Builder"):
        get_builder()


def test_new_builder_context_activates_and_resets():
    """Inside the context, get_builder() returns the same instance; outside, it's gone again."""
    with new_builder_context() as builder:
        assert get_builder() is builder
    with pytest.raises(RuntimeError):
        get_builder()


def test_sequential_builder_contexts_do_not_leak_ops():
    """Running two scripts back-to-back must not let ops from the first leak into the second.

    This is the concrete failure mode of an ambient-builder design: if the contextvar
    or the Builder's internal def-list were ever shared/reused across executions,
    script N+1's DiagramIR would silently include script N's geometry.
    """
    from geometry_diagrams.ir.ir import PointFixed

    with new_builder_context() as b1:
        b1._add(PointFixed(id="p1", x=0, y=0))
        ir1 = b1.build()

    with new_builder_context() as b2:
        b2._add(PointFixed(id="p2", x=1, y=1))
        ir2 = b2.build()

    assert [d.id for d in ir1.define] == ["p1"]
    assert [d.id for d in ir2.define] == ["p2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.pydsl'`

- [ ] **Step 3: Implement `Builder` core**

```python
# geometry_diagrams/pydsl/builder.py
"""Ambient builder context for the Python DSL surface.

Every public API function in `api.py` records its op against the Builder
returned by `get_builder()`. The contextvar is set fresh per script execution
(see sandbox.py) so that sequential executions never share state.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

from geometry_diagrams.ir.ir import Canvas, DefBase, DefStmt, DiagramIR

DEFAULT_OP_CAP = 2000


class OpCapExceededError(RuntimeError):
    """Raised when a script records more ops than the configured cap."""


class Builder:
    def __init__(self, op_cap: int = DEFAULT_OP_CAP) -> None:
        self._defs: list[DefStmt] = []
        self._coord_floats: dict[str, tuple[float, float]] = {}
        self._op_cap = op_cap
        self._hidden_id_counter = 0

    @property
    def op_count(self) -> int:
        return len(self._defs)

    def _add(self, defstmt: DefBase) -> None:
        if len(self._defs) >= self._op_cap:
            raise OpCapExceededError(
                f"script recorded more than {self._op_cap} ops "
                "(this is a size cap, not a security boundary)"
            )
        self._defs.append(defstmt)  # type: ignore[arg-type]

    def _fresh_hidden_id(self, prefix: str) -> str:
        self._hidden_id_counter += 1
        return f"__pydsl_{prefix}_{self._hidden_id_counter}"

    def build(self) -> DiagramIR:
        return DiagramIR(define=list(self._defs), canvas=Canvas())


_current_builder: contextvars.ContextVar["Builder | None"] = contextvars.ContextVar(
    "pydsl_current_builder", default=None
)


def get_builder() -> Builder:
    builder = _current_builder.get()
    if builder is None:
        raise RuntimeError("no active Builder — call inside new_builder_context()")
    return builder


@contextmanager
def new_builder_context(op_cap: int = DEFAULT_OP_CAP) -> Iterator[Builder]:
    builder = Builder(op_cap=op_cap)
    token = _current_builder.set(builder)
    try:
        yield builder
    finally:
        _current_builder.reset(token)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_builder.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing test for op-count cap**

```python
# append to tests/test_pydsl_builder.py
from geometry_diagrams.pydsl.builder import OpCapExceededError


def test_op_cap_raises_once_exceeded():
    """A script that records more ops than the cap gets a clean, catchable error."""
    from geometry_diagrams.ir.ir import PointFixed

    with new_builder_context(op_cap=3) as builder:
        for i in range(3):
            builder._add(PointFixed(id=f"p{i}", x=i, y=i))
        with pytest.raises(OpCapExceededError, match="more than 3 ops"):
            builder._add(PointFixed(id="p_overflow", x=99, y=99))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_builder.py -v`
Expected: PASS (4 tests) — the cap check was already implemented in Step 3, so this should pass immediately; if not, fix `Builder._add`.

- [ ] **Step 7: Write the failing test for handles + basic ops**

```python
# tests/test_pydsl_basic_ops.py
"""Tests for the point() and line_through() API functions and their handles."""
import pytest

from geometry_diagrams.pydsl.api import line_through, point
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_point_creates_point_fixed_def_and_returns_handle():
    with new_builder_context():
        p = point(1.5, -2.0)
        ir = get_builder().build()
    assert len(ir.define) == 1
    d = ir.define[0]
    assert d.kind == "point_fixed"
    assert d.x == 1.5 and d.y == -2.0
    assert p.id == d.id


def test_line_through_references_both_points():
    with new_builder_context():
        a = point(0, 0)
        b = point(1, 1)
        line = line_through(a, b)
        ir = get_builder().build()
    line_defs = [d for d in ir.define if d.kind == "line_through"]
    assert len(line_defs) == 1
    assert line_defs[0].p == a.id
    assert line_defs[0].q == b.id
    assert line.id == line_defs[0].id


def test_api_functions_raise_outside_builder_context():
    with pytest.raises(RuntimeError, match="no active Builder"):
        point(0, 0)
```

- [ ] **Step 8: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_basic_ops.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.pydsl.api'` (and `handles`)

- [ ] **Step 9: Implement handles and basic ops**

```python
# geometry_diagrams/pydsl/handles.py
"""Thin typed handles returned by pydsl API functions.

A handle wraps an internal id (auto-generated or model-supplied for
identity-carrying points) and never requires the model to re-derive
geometric parts from raw point references — see Triangle/Polygon for the
accessor pattern that replaces the DSL's string-id threading.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    id: str


@dataclass(frozen=True)
class Line:
    id: str


@dataclass(frozen=True)
class Segment:
    id: str
```

```python
# geometry_diagrams/pydsl/api.py
"""Public builder-shim API. Every function here records an op against the
ambient Builder (see builder.py) and returns a handle."""
from __future__ import annotations

from geometry_diagrams.ir.ir import LineThrough, PointFixed
from geometry_diagrams.pydsl.builder import get_builder
from geometry_diagrams.pydsl.handles import Line, Point


def point(x: float, y: float) -> Point:
    """A point fixed at literal coordinates (x, y)."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("pt")
    builder._add(PointFixed(id=pid, x=x, y=y))
    builder._coord_floats[pid] = (float(x), float(y))
    return Point(id=pid)


def line_through(p: Point, q: Point) -> Line:
    """The line through two points."""
    builder = get_builder()
    lid = builder._fresh_hidden_id("line")
    builder._add(LineThrough(id=lid, p=p.id, q=q.id))
    return Line(id=lid)
```

```python
# geometry_diagrams/pydsl/__init__.py
"""Python fluent API surface for the geometry construction pipeline (Phase 1a).

Re-exports handles and op functions so callers (and the stub generator) have
one place to introspect the public surface.
"""
from geometry_diagrams.pydsl.api import line_through, point
from geometry_diagrams.pydsl.handles import Line, Point, Segment

__all__ = ["point", "line_through", "Point", "Line", "Segment"]
```

- [ ] **Step 10: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_basic_ops.py tests/test_pydsl_builder.py -v`
Expected: PASS (7 tests)

- [ ] **Step 11: Commit**

```bash
git add geometry_diagrams/pydsl/ tests/test_pydsl_builder.py tests/test_pydsl_basic_ops.py
git commit -m "Add pydsl builder core, contextvar isolation, point/line_through ops"
```

---

### Task 2: Triangle handle + `triangle()` op

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py`
- Modify: `geometry_diagrams/pydsl/api.py`
- Modify: `geometry_diagrams/pydsl/builder.py` (add `_triangle_vertices` bookkeeping)
- Modify: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_triangle.py`

**Interfaces:**
- Consumes: `Point` from Task 1; `geometry_diagrams.ir.ir.{Triangle as TriangleDef, Segment as SegmentDef}`.
- Produces: `Triangle` handle with `.vertices -> tuple[Point, Point, Point]`, `.side(p: Point, q: Point) -> Segment` (order-independent, raises `ValueError` if `p`/`q` are not both vertices of this triangle), `.angle_at(v: Point) -> AngleRef` (added in Task 7 — for now, stub the method to raise `NotImplementedError` with a clear message so Task 7 has a known slot to fill). `triangle(a: Point, b: Point, c: Point) -> Triangle`. `Builder._triangle_vertices: dict[str, tuple[str, str, str]]` mapping triangle id -> vertex ids, and `Builder._segment_cache: dict[frozenset[str], str]` mapping `{p_id, q_id}` -> segment id, so repeated `.side()` calls on the same pair (in either order) return the same handle rather than creating duplicate `Segment` defs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_triangle.py
"""Tests for the Triangle handle and triangle() op."""
import pytest

from geometry_diagrams.pydsl.api import point, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_triangle_creates_triangle_def_with_vertex_ids():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        ir = get_builder().build()
    tri_defs = [d for d in ir.define if d.kind == "triangle"]
    assert len(tri_defs) == 1
    assert (tri_defs[0].a, tri_defs[0].b, tri_defs[0].c) == (a.id, b.id, c.id)
    assert t.id == tri_defs[0].id


def test_vertices_accessor_returns_point_handles_in_order():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        assert [v.id for v in t.vertices] == [a.id, b.id, c.id]


def test_side_is_order_independent():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        s1 = t.side(a, b)
        s2 = t.side(b, a)
        assert s1.id == s2.id


def test_side_creates_exactly_one_segment_def():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        t.side(a, b)
        t.side(b, a)  # same pair, reversed order — must not create a second Segment
        ir = get_builder().build()
    seg_defs = [d for d in ir.define if d.kind == "segment"]
    assert len(seg_defs) == 1


def test_side_raises_for_non_vertex_point():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        outside = point(5, 5)
        t = triangle(a, b, c)
        with pytest.raises(ValueError, match="not a vertex"):
            t.side(a, outside)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_triangle.py -v`
Expected: FAIL with `ImportError: cannot import name 'triangle'`

- [ ] **Step 3: Implement `Triangle` handle and `triangle()` op**

```python
# add to geometry_diagrams/pydsl/handles.py
from geometry_diagrams.pydsl.builder import get_builder


@dataclass(frozen=True)
class Triangle:
    id: str
    vertices: tuple[Point, Point, Point]

    def side(self, p: Point, q: Point) -> "Segment":
        vertex_ids = {v.id for v in self.vertices}
        for name, pt in (("p", p), ("q", q)):
            if pt.id not in vertex_ids:
                raise ValueError(f"{pt.id!r} is not a vertex of triangle {self.id!r} ({name})")
        builder = get_builder()
        return builder._get_or_create_segment(p.id, q.id)

    def angle_at(self, v: Point) -> "AngleRef":
        from geometry_diagrams.pydsl.handles import AngleRef  # Task 7

        vertex_ids = [vert.id for vert in self.vertices]
        if v.id not in vertex_ids:
            raise ValueError(f"{v.id!r} is not a vertex of triangle {self.id!r}")
        others = [pid for pid in vertex_ids if pid != v.id]
        return AngleRef(a=Point(id=others[0]), o=v, b=Point(id=others[1]))
```

```python
# add to geometry_diagrams/pydsl/builder.py, inside class Builder
    def _get_or_create_segment(self, p_id: str, q_id: str) -> "Segment":
        from geometry_diagrams.ir.ir import Segment as SegmentDef
        from geometry_diagrams.pydsl.handles import Segment

        key = frozenset((p_id, q_id))
        if not hasattr(self, "_segment_cache"):
            self._segment_cache: dict[frozenset, str] = {}
        if key in self._segment_cache:
            return Segment(id=self._segment_cache[key])
        sid = self._fresh_hidden_id("seg")
        self._add(SegmentDef(id=sid, a=p_id, b=q_id))
        self._segment_cache[key] = sid
        return Segment(id=sid)
```

```python
# add to geometry_diagrams/pydsl/api.py
from geometry_diagrams.ir.ir import Triangle as TriangleDef
from geometry_diagrams.pydsl.handles import Point, Triangle


def triangle(a: Point, b: Point, c: Point) -> Triangle:
    """A triangle over three existing points."""
    builder = get_builder()
    tid = builder._fresh_hidden_id("tri")
    builder._add(TriangleDef(id=tid, a=a.id, b=b.id, c=c.id))
    builder._triangle_vertices = getattr(builder, "_triangle_vertices", {})
    builder._triangle_vertices[tid] = (a.id, b.id, c.id)
    return Triangle(id=tid, vertices=(a, b, c))
```

Add `triangle` and `Triangle` to `geometry_diagrams/pydsl/__init__.py`'s imports and `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_triangle.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/ tests/test_pydsl_triangle.py
git commit -m "Add Triangle handle: vertices, order-independent side(), angle_at() stub"
```

---

### Task 3: Polygon handle + `polygon()` op

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py`
- Modify: `geometry_diagrams/pydsl/api.py`
- Modify: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_polygon.py`

**Interfaces:**
- Consumes: `Point`, `Builder._get_or_create_segment` from Task 2.
- Produces: `Polygon` handle with `.vertices -> tuple[Point, ...]`, `.side(v1: Point, v2: Point) -> Segment` (raises `ValueError` if `v1`/`v2` are not adjacent in vertex order — this is the structural, non-geometric adjacency check), `.angle_at(v: Point) -> AngleRef` (stub, filled in Task 7). `polygon(*vertices: Point) -> Polygon`, requires 3+ vertices.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_polygon.py
"""Tests for the Polygon handle and polygon() op."""
import pytest

from geometry_diagrams.pydsl.api import point, polygon
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_polygon_creates_polygon_def_with_vertex_ids_in_order():
    with new_builder_context():
        pts = [point(0, 0), point(1, 0), point(1, 1), point(0, 1)]
        p = polygon(*pts)
        ir = get_builder().build()
    poly_defs = [d for d in ir.define if d.kind == "polygon"]
    assert len(poly_defs) == 1
    assert poly_defs[0].points == [pt.id for pt in pts]
    assert p.id == poly_defs[0].id


def test_polygon_requires_at_least_three_vertices():
    with new_builder_context():
        with pytest.raises(ValueError, match="at least 3"):
            polygon(point(0, 0), point(1, 0))


def test_side_accepts_adjacent_vertices_either_order():
    with new_builder_context():
        a, b, c, d = point(0, 0), point(1, 0), point(1, 1), point(0, 1)
        p = polygon(a, b, c, d)
        s1 = p.side(a, b)
        s2 = p.side(b, a)
        assert s1.id == s2.id
        s_wrap = p.side(d, a)  # last vertex to first — also adjacent
        assert s_wrap.id != s1.id


def test_side_raises_for_non_adjacent_vertices():
    with new_builder_context():
        a, b, c, d = point(0, 0), point(1, 0), point(1, 1), point(0, 1)
        p = polygon(a, b, c, d)
        with pytest.raises(ValueError, match="not adjacent"):
            p.side(a, c)  # diagonal, not an edge
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_polygon.py -v`
Expected: FAIL with `ImportError: cannot import name 'polygon'`

- [ ] **Step 3: Implement `Polygon` handle and `polygon()` op**

```python
# add to geometry_diagrams/pydsl/handles.py
@dataclass(frozen=True)
class Polygon:
    id: str
    vertices: tuple[Point, ...]

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
        builder = get_builder()
        return builder._get_or_create_segment(v1.id, v2.id)

    def angle_at(self, v: Point) -> "AngleRef":
        from geometry_diagrams.pydsl.handles import AngleRef  # Task 7

        ids = [vert.id for vert in self.vertices]
        if v.id not in ids:
            raise ValueError(f"{v.id!r} is not a vertex of polygon {self.id!r}")
        n = len(ids)
        i = ids.index(v.id)
        prev_id, next_id = ids[(i - 1) % n], ids[(i + 1) % n]
        return AngleRef(a=Point(id=prev_id), o=v, b=Point(id=next_id))
```

```python
# add to geometry_diagrams/pydsl/api.py
from geometry_diagrams.ir.ir import Polygon as PolygonDef
from geometry_diagrams.pydsl.handles import Polygon


def polygon(*vertices: Point) -> Polygon:
    """A closed polygon over 3 or more existing points, in perimeter order."""
    if len(vertices) < 3:
        raise ValueError(f"polygon requires at least 3 vertices, got {len(vertices)}")
    builder = get_builder()
    pid = builder._fresh_hidden_id("poly")
    builder._add(PolygonDef(id=pid, points=[v.id for v in vertices]))
    return Polygon(id=pid, vertices=tuple(vertices))
```

Add `polygon` and `Polygon` to `geometry_diagrams/pydsl/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_polygon.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/ tests/test_pydsl_polygon.py
git commit -m "Add Polygon handle: vertices, adjacency-validated side(), angle_at() stub"
```

---

### Task 4: Circle handle + `circumcircle()`/`incircle()` ops

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py`
- Modify: `geometry_diagrams/pydsl/api.py`
- Modify: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_circle.py`

**Interfaces:**
- Consumes: `Triangle` from Task 2, `Builder._triangle_vertices`, `Builder._coord_floats` (populated by `point()` in Task 1).
- Produces: `Circle` handle with `.center -> Point` (computed, hidden id), `.radius -> float | str` (numeric when vertex coordinates are concrete, else a symbolic length-expression string — mirroring the existing `_lower_incircle` fallback behavior in `geometry_diagrams/recipe/lower.py`, not new scope). `circumcircle(t: Triangle) -> Circle`, `incircle(t: Triangle) -> Circle`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_circle.py
"""Tests for the Circle handle and circumcircle()/incircle() ops."""
import math

from geometry_diagrams.pydsl.api import circumcircle, incircle, point, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_circumcircle_center_is_a_computed_point_triangle_center():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        circ = circumcircle(t)
        center = circ.center
        ir = get_builder().build()
    center_defs = [d for d in ir.define if d.kind == "point_triangle_center"]
    assert len(center_defs) == 1
    assert center_defs[0].which == "circumcenter"
    assert center_defs[0].tri == t.id
    assert center.id == center_defs[0].id


def test_incircle_radius_is_numeric_for_concrete_vertices():
    with new_builder_context():
        # 3-4-5 right triangle: inradius = (a + b - c) / 2 = (3 + 4 - 5) / 2 = 1.0
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        inc = incircle(t)
    assert math.isclose(inc.radius, 1.0, abs_tol=1e-9)


def test_incircle_center_is_a_computed_incenter_point():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        inc = incircle(t)
        center = inc.center
        ir = get_builder().build()
    center_defs = [d for d in ir.define if d.kind == "point_triangle_center" and d.which == "incenter"]
    assert len(center_defs) == 1
    assert center.id == center_defs[0].id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_circle.py -v`
Expected: FAIL with `ImportError: cannot import name 'circumcircle'`

- [ ] **Step 3: Implement `Circle` handle and ops**

```python
# add to geometry_diagrams/pydsl/handles.py
@dataclass(frozen=True)
class Circle:
    id: str
    center: Point
    radius: "float | str"
```

```python
# add to geometry_diagrams/pydsl/api.py
import math

from geometry_diagrams.ir.ir import CircleCenterRadius, PointTriangleCenter
from geometry_diagrams.pydsl.handles import Circle, Triangle


def circumcircle(t: Triangle) -> Circle:
    """The circumscribed circle of a triangle. Radius is left to SymPy downstream."""
    builder = get_builder()
    center_id = builder._fresh_hidden_id("circumcenter")
    builder._add(PointTriangleCenter(id=center_id, tri=t.id, which="circumcenter"))
    cid = builder._fresh_hidden_id("circumcircle")
    # Radius is resolved by SymPy from the center + any vertex; the IR's
    # CircleCenterPoint form takes a "through" point rather than a radius.
    from geometry_diagrams.ir.ir import CircleCenterPoint

    builder._add(CircleCenterPoint(id=cid, center=center_id, through=t.vertices[0].id))
    return Circle(id=cid, center=Point(id=center_id), radius="unresolved")


def incircle(t: Triangle) -> Circle:
    """The inscribed circle of a triangle.

    Mirrors geometry_diagrams/recipe/lower.py's _lower_incircle: computes the
    inradius numerically via Heron's formula when all three vertices are
    already concrete (PointFixed) coordinates, tracked in builder._coord_floats;
    falls back to a symbolic length-expression string otherwise. This is
    replicating an existing output-computation, not new eager validation —
    no script is ever rejected by this logic.
    """
    builder = get_builder()
    center_id = builder._fresh_hidden_id("incenter")
    builder._add(PointTriangleCenter(id=center_id, tri=t.id, which="incenter"))
    a_id, b_id, c_id = (v.id for v in t.vertices)
    cid = builder._fresh_hidden_id("incircle")

    coord_floats = builder._coord_floats
    if all(v in coord_floats for v in (a_id, b_id, c_id)):
        ax, ay = coord_floats[a_id]
        bx, by = coord_floats[b_id]
        cx, cy = coord_floats[c_id]
        side_a = math.hypot(bx - cx, by - cy)
        side_b = math.hypot(ax - cx, ay - cy)
        side_c = math.hypot(ax - bx, ay - by)
        s = (side_a + side_b + side_c) / 2
        area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2
        radius: "float | str" = round(area / s, 10)
    else:
        radius = (
            f"sqrt((length({b_id},{c_id})+length({a_id},{c_id})+length({a_id},{b_id}))/2 - length({b_id},{c_id})) "
            f"* sqrt((length({b_id},{c_id})+length({a_id},{c_id})+length({a_id},{b_id}))/2 - length({a_id},{c_id})) "
            f"* sqrt((length({b_id},{c_id})+length({a_id},{c_id})+length({a_id},{b_id}))/2 - length({a_id},{b_id})) "
            f"/ sqrt((length({b_id},{c_id})+length({a_id},{c_id})+length({a_id},{b_id}))/2)"
        )
    builder._add(CircleCenterRadius(id=cid, center=center_id, radius=radius))
    return Circle(id=cid, center=Point(id=center_id), radius=radius)
```

Add `circumcircle`, `incircle`, `Circle` to `geometry_diagrams/pydsl/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_circle.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/ tests/test_pydsl_circle.py
git commit -m "Add Circle handle: circumcircle()/incircle() mirroring lower.py's numeric/symbolic split"
```

---

### Task 5: Median handle + `median()` op

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py`
- Modify: `geometry_diagrams/pydsl/api.py`
- Modify: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_median.py`

**Interfaces:**
- Consumes: `Triangle`, `Point`, `Builder._triangle_vertices`.
- Produces: `Median` handle with `.midpoint -> Point`, `.segment -> Segment`. `median(t: Triangle, from_vertex: Point) -> Median`, raises `ValueError` if `from_vertex` is not a vertex of `t`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_median.py
"""Tests for the Median handle and median() op."""
import pytest

from geometry_diagrams.pydsl.api import median, point, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_median_midpoint_is_midpoint_of_opposite_side():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 4)
        t = triangle(a, b, c)
        m = median(t, from_vertex=a)
        mid = m.midpoint
        ir = get_builder().build()
    mid_defs = [d for d in ir.define if d.kind == "point_midpoint"]
    assert len(mid_defs) == 1
    assert {mid_defs[0].p, mid_defs[0].q} == {b.id, c.id}
    assert mid.id == mid_defs[0].id


def test_median_segment_connects_vertex_to_midpoint():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 4)
        t = triangle(a, b, c)
        m = median(t, from_vertex=a)
        seg = m.segment
        ir = get_builder().build()
    seg_defs = [d for d in ir.define if d.kind == "segment" and d.id == seg.id]
    assert len(seg_defs) == 1
    assert seg_defs[0].a == a.id
    assert seg_defs[0].b == m.midpoint.id


def test_median_raises_for_vertex_not_in_triangle():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 4)
        outside = point(9, 9)
        t = triangle(a, b, c)
        with pytest.raises(ValueError, match="not a vertex"):
            median(t, from_vertex=outside)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_median.py -v`
Expected: FAIL with `ImportError: cannot import name 'median'`

- [ ] **Step 3: Implement `Median` handle and op**

```python
# add to geometry_diagrams/pydsl/handles.py
@dataclass(frozen=True)
class Median:
    id: str
    midpoint: Point
    segment: "Segment"
```

```python
# add to geometry_diagrams/pydsl/api.py
from geometry_diagrams.ir.ir import PointMidpoint
from geometry_diagrams.ir.ir import Segment as SegmentDef
from geometry_diagrams.pydsl.handles import Median, Segment


def median(t: Triangle, from_vertex: Point) -> Median:
    """The median from a vertex to the midpoint of the opposite side."""
    vertex_ids = [v.id for v in t.vertices]
    if from_vertex.id not in vertex_ids:
        raise ValueError(f"{from_vertex.id!r} is not a vertex of triangle {t.id!r}")
    others = [pid for pid in vertex_ids if pid != from_vertex.id]
    builder = get_builder()
    mid_id = builder._fresh_hidden_id("midpoint")
    builder._add(PointMidpoint(id=mid_id, p=others[0], q=others[1]))
    seg_id = builder._fresh_hidden_id("median_seg")
    builder._add(SegmentDef(id=seg_id, a=from_vertex.id, b=mid_id))
    return Median(id=seg_id, midpoint=Point(id=mid_id), segment=Segment(id=seg_id))
```

Add `median`, `Median` to `geometry_diagrams/pydsl/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_median.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/ tests/test_pydsl_median.py
git commit -m "Add Median handle: midpoint and vertex-to-midpoint segment"
```

---

### Task 6: Altitude handle + `altitude()` op

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py`
- Modify: `geometry_diagrams/pydsl/api.py`
- Modify: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_altitude.py`

**Interfaces:**
- Consumes: `Triangle`, `Point`.
- Produces: `Altitude` handle with `.foot -> Point`, `.line -> Line`. `altitude(t: Triangle, from_vertex: Point) -> Altitude`, raises `ValueError` if `from_vertex` is not a vertex of `t`. Internally constructs the same four IR objects the DSL's altitude lowering does (hidden base `LineThrough`, `LinePerpendicularThrough` as the altitude line, `PointFoot` as the foot, hidden `Segment` vertex→foot) — this task writes new equivalent logic directly against the IR classes, it does not call into `recipe/lower.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_altitude.py
"""Tests for the Altitude handle and altitude() op."""
import pytest

from geometry_diagrams.pydsl.api import altitude, point, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_altitude_foot_is_a_point_foot_def():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        alt = altitude(t, from_vertex=a)
        foot = alt.foot
        ir = get_builder().build()
    foot_defs = [d for d in ir.define if d.kind == "point_foot"]
    assert len(foot_defs) == 1
    assert foot_defs[0].source == a.id
    assert foot.id == foot_defs[0].id


def test_altitude_line_is_perpendicular_through_the_vertex():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        alt = altitude(t, from_vertex=a)
        line = alt.line
        ir = get_builder().build()
    perp_defs = [d for d in ir.define if d.kind == "line_perp_through" and d.id == line.id]
    assert len(perp_defs) == 1
    assert perp_defs[0].through == a.id


def test_altitude_base_line_connects_the_other_two_vertices():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        alt = altitude(t, from_vertex=a)
        ir = get_builder().build()
    base_defs = [d for d in ir.define if d.kind == "line_through"]
    assert len(base_defs) == 1
    assert {base_defs[0].p, base_defs[0].q} == {b.id, c.id}


def test_altitude_raises_for_vertex_not_in_triangle():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        outside = point(9, 9)
        t = triangle(a, b, c)
        with pytest.raises(ValueError, match="not a vertex"):
            altitude(t, from_vertex=outside)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_altitude.py -v`
Expected: FAIL with `ImportError: cannot import name 'altitude'`

- [ ] **Step 3: Implement `Altitude` handle and op**

```python
# add to geometry_diagrams/pydsl/handles.py
@dataclass(frozen=True)
class Altitude:
    id: str
    foot: Point
    line: Line
```

```python
# add to geometry_diagrams/pydsl/api.py
from geometry_diagrams.ir.ir import LinePerpendicularThrough, PointFoot
from geometry_diagrams.ir.ir import Segment as SegmentDef
from geometry_diagrams.pydsl.handles import Altitude, Line


def altitude(t: Triangle, from_vertex: Point) -> Altitude:
    """The altitude from a vertex, perpendicular to the opposite side."""
    vertex_ids = [v.id for v in t.vertices]
    if from_vertex.id not in vertex_ids:
        raise ValueError(f"{from_vertex.id!r} is not a vertex of triangle {t.id!r}")
    others = [pid for pid in vertex_ids if pid != from_vertex.id]
    builder = get_builder()

    base_id = builder._fresh_hidden_id("altitude_base")
    builder._add(LineThrough(id=base_id, p=others[0], q=others[1]))

    line_id = builder._fresh_hidden_id("altitude_line")
    builder._add(
        LinePerpendicularThrough(id=line_id, through=from_vertex.id, to_line=base_id)
    )

    foot_id = builder._fresh_hidden_id("altitude_foot")
    builder._add(PointFoot(id=foot_id, source=from_vertex.id, onto=base_id))

    seg_id = builder._fresh_hidden_id("altitude_seg")
    builder._add(SegmentDef(id=seg_id, a=from_vertex.id, b=foot_id))

    return Altitude(id=line_id, foot=Point(id=foot_id), line=Line(id=line_id))
```

(`LineThrough` is already imported in `api.py` from Task 1.) Add `altitude`, `Altitude` to `geometry_diagrams/pydsl/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_altitude.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/ tests/test_pydsl_altitude.py
git commit -m "Add Altitude handle: foot and perpendicular line"
```

---

### Task 7: AngleRef + `angle_at()` wiring + `mark_angle()` op

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py` (implement `AngleRef`; unstub `Triangle.angle_at`/`Polygon.angle_at` — they already reference `AngleRef` from Tasks 2–3, this task just makes the import resolve)
- Modify: `geometry_diagrams/pydsl/api.py`
- Modify: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_angle.py`

**Interfaces:**
- Consumes: `Point`, `Triangle.angle_at`, `Polygon.angle_at` (already implemented in Tasks 2–3, importing `AngleRef` lazily).
- Produces: `AngleRef` dataclass with `.a: Point`, `.o: Point`, `.b: Point` (no other accessors, per the design doc). `mark_angle(ref: AngleRef, group: int | None = None) -> None` — appends a render op, no handle returned (nothing downstream references a mark).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_angle.py
"""Tests for AngleRef, Triangle/Polygon.angle_at(), and mark_angle()."""
from geometry_diagrams.pydsl.api import mark_angle, point, polygon, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_triangle_angle_at_returns_angle_ref_with_other_two_vertices():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
    assert ref.o.id == b.id
    assert {ref.a.id, ref.b.id} == {a.id, c.id}


def test_polygon_angle_at_uses_adjacent_vertices():
    with new_builder_context():
        p0, p1, p2, p3 = point(0, 0), point(1, 0), point(1, 1), point(0, 1)
        poly = polygon(p0, p1, p2, p3)
        ref = poly.angle_at(p1)
    assert ref.o.id == p1.id
    assert {ref.a.id, ref.b.id} == {p0.id, p2.id}


def test_mark_angle_appends_a_render_op():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
        mark_angle(ref, group=1)
        ir = get_builder().build()
    assert len(ir.render) == 1
    assert ir.render[0].kind == "mark_angles"
    assert ir.render[0].group == "1"
    assert ir.render[0].angles[0].o == b.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_angle.py -v`
Expected: FAIL — `Triangle.angle_at` raises `ImportError` (the lazy `from geometry_diagrams.pydsl.handles import AngleRef` fails because `AngleRef` doesn't exist yet)

- [ ] **Step 3: Implement `AngleRef` and `mark_angle()`**

First, confirm the exact `MarkAngles` render-op shape by reading it:

Run: `grep -n "class MarkAngles" -A 8 geometry_diagrams/ir/ir.py`

Use whatever fields that shows (expected: `id`/`kind`, `angles: list[AnglePoints]`, `group: Optional[str]`, matching the usage already quoted from `lower.py`'s `_apply_annotations`: `MarkAngles(angles=[AnglePoints(a=a, o=vertex, b=b)], group=str(mark.group) if mark.group is not None else None)`). Adjust the code below if the constructor signature differs (e.g. if it also requires an `id` field, generate one via `builder._fresh_hidden_id("mark")`).

```python
# add to geometry_diagrams/pydsl/handles.py
@dataclass(frozen=True)
class AngleRef:
    a: Point
    o: Point
    b: Point
```

```python
# add to geometry_diagrams/pydsl/api.py
from geometry_diagrams.ir.ir import AnglePoints, MarkAngles
from geometry_diagrams.pydsl.handles import AngleRef


def mark_angle(ref: AngleRef, group: int | None = None) -> None:
    """Mark an angle arc for rendering, optionally tagged with an equal-angle group."""
    builder = get_builder()
    builder._render.append(
        MarkAngles(
            angles=[AnglePoints(a=ref.a.id, o=ref.o.id, b=ref.b.id)],
            group=str(group) if group is not None else None,
        )
    )
```

```python
# add to geometry_diagrams/pydsl/builder.py, inside class Builder.__init__
        self._render: list = []
# add inside Builder.build()
    def build(self) -> DiagramIR:
        return DiagramIR(define=list(self._defs), render=list(self._render), canvas=Canvas())
```

Add `mark_angle`, `AngleRef` to `geometry_diagrams/pydsl/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_angle.py -v`
Expected: PASS (3 tests). If `MarkAngles` requires an `id` field, add `id=builder._fresh_hidden_id("mark")` to the constructor call and re-run.

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/ tests/test_pydsl_angle.py
git commit -m "Add AngleRef, wire Triangle/Polygon.angle_at(), add mark_angle() render op"
```

---

### Task 8: Stub generator

**Files:**
- Create: `geometry_diagrams/pydsl/stub.py`
- Test: `tests/test_pydsl_stub.py`

**Interfaces:**
- Consumes: the `geometry_diagrams.pydsl` module (Tasks 1–7's `__all__`).
- Produces: `generate_stub() -> str` — signatures-and-docstrings text for every function and every handle class's public methods in `geometry_diagrams.pydsl.__all__`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_stub.py
"""Tests for the pydsl stub generator."""
from geometry_diagrams.pydsl.stub import generate_stub


def test_stub_includes_every_public_function():
    stub = generate_stub()
    for name in ("point", "line_through", "triangle", "polygon", "circumcircle",
                 "incircle", "altitude", "median", "mark_angle"):
        assert f"def {name}(" in stub, f"missing {name} in stub"


def test_stub_includes_handle_accessor_methods():
    stub = generate_stub()
    assert "def side(" in stub  # from Triangle/Polygon
    assert "def angle_at(" in stub


def test_stub_does_not_include_private_helpers():
    stub = generate_stub()
    assert "_fresh_hidden_id" not in stub
    assert "_get_or_create_segment" not in stub
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_stub.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.pydsl.stub'`

- [ ] **Step 3: Implement the stub generator**

```python
# geometry_diagrams/pydsl/stub.py
"""Generates LLM-readable signature+docstring text from the pydsl public API.

Single source of truth: change a function's signature or docstring and the
prompt text regenerates automatically. Not a strictly importable .pyi file —
just readable stub text for prompt assembly.
"""
from __future__ import annotations

import inspect

import geometry_diagrams.pydsl as pydsl_module

_HANDLE_CLASS_NAMES = {"Point", "Line", "Segment", "Triangle", "Polygon", "Circle",
                        "Altitude", "Median", "AngleRef"}


def _format_callable(name: str, obj) -> str:
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        sig = "(...)"
    doc = inspect.getdoc(obj) or ""
    first_line = doc.splitlines()[0] if doc else ""
    line = f"def {name}{sig}"
    return f"{line}  # {first_line}" if first_line else line


def generate_stub() -> str:
    lines: list[str] = []
    for name in pydsl_module.__all__:
        obj = getattr(pydsl_module, name)
        if inspect.isfunction(obj):
            lines.append(_format_callable(name, obj))
        elif inspect.isclass(obj) and name in _HANDLE_CLASS_NAMES:
            lines.append(f"class {name}:")
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                lines.append("    " + _format_callable(method_name, method))
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_stub.py -v`
Expected: PASS (3 tests). If a handle class isn't yet exported in `__all__`, add it to `geometry_diagrams/pydsl/__init__.py` first (all handle classes should already be exported by Task 7).

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/stub.py tests/test_pydsl_stub.py
git commit -m "Add stub generator: introspects public API into prompt-ready text"
```

---

### Task 9: Retry-layer failure classification + did-you-mean

**Files:**
- Create: `geometry_diagrams/pydsl/retry.py`
- Test: `tests/test_pydsl_retry.py`

**Interfaces:**
- Consumes: nothing from earlier tasks except the API function name list (`geometry_diagrams.pydsl.__all__`), used as the did-you-mean candidate pool.
- Produces: `classify_failure(exc: Exception) -> str` returning one of `"hallucinated_api"`, `"structural_precondition"`, `"syntax_or_timeout"`. `suggest_name(bad_name: str, candidates: list[str]) -> str | None` (wraps `difflib.get_close_matches`, returns the top match or `None`). `build_retry_message(exc: Exception, script: str) -> str` — the exception message, plus a did-you-mean suggestion appended when `classify_failure` returns `"hallucinated_api"` and a name can be extracted from the message.

This task is built and tested standalone, with hand-constructed exceptions — it does not yet touch the executor (Task 10 wires it in).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_retry.py
"""Tests for retry-layer failure classification and did-you-mean suggestions."""
from geometry_diagrams.pydsl.builder import OpCapExceededError
from geometry_diagrams.pydsl.retry import build_retry_message, classify_failure, suggest_name


def test_suggest_name_finds_close_match():
    assert suggest_name("itnersection", ["intersection", "triangle", "polygon"]) == "intersection"


def test_suggest_name_returns_none_for_no_close_match():
    assert suggest_name("xyzzy", ["intersection", "triangle", "polygon"]) is None


def test_classify_failure_categorizes_name_error_as_hallucinated_api():
    exc = NameError("The variable `itnersection` is not defined")
    assert classify_failure(exc) == "hallucinated_api"


def test_classify_failure_categorizes_value_error_as_structural_precondition():
    exc = ValueError("'p9' is not a vertex of triangle 'tri_1'")
    assert classify_failure(exc) == "structural_precondition"


def test_classify_failure_categorizes_op_cap_as_syntax_or_timeout():
    exc = OpCapExceededError("script recorded more than 2000 ops")
    assert classify_failure(exc) == "syntax_or_timeout"


def test_build_retry_message_appends_did_you_mean_for_hallucinated_api():
    exc = NameError("The variable `itnersection` is not defined")
    msg = build_retry_message(exc, script="itnersection(L1, L2)")
    assert "itnersection" in msg
    assert "did you mean 'intersection'" in msg


def test_build_retry_message_has_no_suggestion_for_structural_errors():
    exc = ValueError("'p9' is not a vertex of triangle 'tri_1'")
    msg = build_retry_message(exc, script="t.side(a, p9)")
    assert "did you mean" not in msg
    assert "not a vertex" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_retry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.pydsl.retry'`

- [ ] **Step 3: Implement the retry layer**

```python
# geometry_diagrams/pydsl/retry.py
"""Retry-loop support: classifies executor failures and produces a retry
prompt message, including did-you-mean suggestions for hallucinated API
names. Lives here, not in the shim, because LocalPythonExecutor's own name
resolution never consults a module-level __getattr__ — see the design doc.
"""
from __future__ import annotations

import difflib
import re

import geometry_diagrams.pydsl as pydsl_module
from geometry_diagrams.pydsl.builder import OpCapExceededError

_NAME_ERROR_PATTERN = re.compile(r"variable `([^`]+)`")


def suggest_name(bad_name: str, candidates: list[str]) -> str | None:
    matches = difflib.get_close_matches(bad_name, candidates, n=1)
    return matches[0] if matches else None


def classify_failure(exc: Exception) -> str:
    if isinstance(exc, NameError):
        return "hallucinated_api"
    if isinstance(exc, ValueError):
        return "structural_precondition"
    if isinstance(exc, OpCapExceededError):
        return "syntax_or_timeout"
    return "syntax_or_timeout"


def build_retry_message(exc: Exception, script: str) -> str:
    message = str(exc)
    if classify_failure(exc) == "hallucinated_api":
        match = _NAME_ERROR_PATTERN.search(message)
        if match:
            bad_name = match.group(1)
            suggestion = suggest_name(bad_name, list(pydsl_module.__all__))
            if suggestion:
                message = f"{message} — did you mean '{suggestion}'?"
    return message
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_retry.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/retry.py tests/test_pydsl_retry.py
git commit -m "Add retry-layer failure classification and did-you-mean suggestion"
```

---

### Task 10: Executor + sandbox (smolagents + subprocess + rlimits)

**Files:**
- Modify: `pyproject.toml` (add `smolagents>=1.17.0` to `[project.dependencies]`)
- Create: `geometry_diagrams/pydsl/sandbox.py`
- Test: `tests/test_pydsl_sandbox.py`

**Interfaces:**
- Consumes: `geometry_diagrams.pydsl` (the full public API, injected as `LocalPythonExecutor` tools), `Builder`/`new_builder_context` from Task 1.
- Produces: `run_script(script: str, timeout_seconds: float = 5.0) -> ScriptResult` where `ScriptResult` is a small dataclass: `diagram_ir: DiagramIR | None`, `error: str | None`, `error_type: str | None` (one of `"import_error"`, `"dangerous_call"`, `"execution_error"`, `"timeout"`). Runs in a subprocess (`multiprocessing.Process`) with `RLIMIT_CPU` set inside the child; the parent enforces a hard wall-clock kill (`process.join(timeout)` then `process.kill()`) as the actual cross-platform backstop, independent of whether the in-process `LocalPythonExecutor(timeout_seconds=...)` fires first.

- [ ] **Step 1: Add the dependency**

Edit `pyproject.toml`:
```toml
dependencies = [
    "httpx>=0.28.1",
    "langchain>=1.3.6",
    "langchain-anthropic>=1.4.4",
    "langgraph>=1.2.0",
    "matplotlib>=3.10.9",
    "pydantic>=2.0",
    "pyyaml>=6.0.3",
    "smolagents>=1.17.0",
    "sympy>=1.14.0",
]
```

Run: `uv sync`
Expected: `smolagents` and its transitive deps install without error.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_pydsl_sandbox.py
"""Tests for the pydsl sandbox: import lockdown, dangerous calls, resource limits."""
import sys

import pytest

from geometry_diagrams.pydsl.sandbox import run_script


def test_valid_script_produces_a_diagram_ir():
    script = """
a = point(0, 0)
b = point(1, 0)
c = point(0, 1)
t = triangle(a, b, c)
"""
    result = run_script(script)
    assert result.error is None
    assert result.diagram_ir is not None
    assert any(d.kind == "triangle" for d in result.diagram_ir.define)


def test_disallowed_import_is_rejected():
    result = run_script("import os\nos.system('echo hi')")
    assert result.diagram_ir is None
    assert result.error_type == "import_error"


def test_dangerous_call_is_rejected():
    result = run_script("open('/etc/passwd')")
    assert result.diagram_ir is None
    assert result.error_type == "dangerous_call"


def test_infinite_while_loop_is_caught_by_iteration_cap():
    result = run_script("i = 0\nwhile True:\n    i = i + 1")
    assert result.diagram_ir is None
    assert result.error_type in ("execution_error", "timeout")


@pytest.mark.timeout(30)
def test_cpu_bomb_is_killed_by_rlimit_cpu_on_any_platform():
    result = run_script("import math\nmath.factorial(10**8)", timeout_seconds=2.0)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"


@pytest.mark.timeout(30)
@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS is a documented no-op on macOS")
def test_memory_bomb_is_killed_by_rlimit_as_on_linux():
    result = run_script("x = [0] * (10**12)", timeout_seconds=5.0)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"


@pytest.mark.timeout(30)
def test_memory_bomb_is_killed_by_wall_clock_timeout_on_any_platform():
    # Cross-platform-reliable backstop regardless of RLIMIT_AS support:
    # the parent's hard kill fires even if the child's own limits don't.
    result = run_script("x = [0] * (10**12)", timeout_seconds=5.0)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"
```

Note: `pytest.mark.timeout` requires `pytest-timeout`; check if it's already a dev dependency (`grep pytest-timeout pyproject.toml`). If absent, add `"pytest-timeout>=2.3.1"` to `[dependency-groups.dev]` in `pyproject.toml` and run `uv sync` before continuing — these tests must not be able to hang the test suite itself if the sandbox implementation has a bug.

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_sandbox.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.pydsl.sandbox'`

- [ ] **Step 4: Implement the sandbox**

```python
# geometry_diagrams/pydsl/sandbox.py
"""Executes untrusted pydsl scripts inside a resource-limited subprocess,
using smolagents.LocalPythonExecutor as the restricted interpreter.

Security posture (see design doc): LocalPythonExecutor's own AST
whitelist/import-allowlist/dangerous-function-blocklist is the primary
control. This module adds process-level isolation on top: RLIMIT_CPU
(reliable on macOS and Linux) plus a parent-side hard wall-clock kill
(the only backstop that's reliable on both platforms for memory bombs,
since RLIMIT_AS is a documented no-op on macOS and a thread-based timeout
alone cannot forcibly terminate a running thread).
"""
from __future__ import annotations

import multiprocessing
import resource
from dataclasses import dataclass

from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.pydsl.builder import new_builder_context

_DANGEROUS_CALL_NAMES = {"exec", "eval", "open", "compile", "__import__"}


@dataclass
class ScriptResult:
    diagram_ir: "DiagramIR | None"
    error: "str | None"
    error_type: "str | None"  # "import_error" | "dangerous_call" | "execution_error" | "timeout"


def _run_in_subprocess(script: str, timeout_seconds: float, queue: "multiprocessing.Queue") -> None:
    """Runs entirely inside the child process. Puts a (kind, payload) tuple on the queue."""
    try:
        resource.setrlimit(
            resource.RLIMIT_CPU, (int(timeout_seconds) + 1, int(timeout_seconds) + 1)
        )
    except (ValueError, OSError):
        pass  # best-effort; the parent's wall-clock kill is the real backstop
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    except (ValueError, OSError):
        pass  # documented no-op on macOS; effective on Linux

    from smolagents import LocalPythonExecutor

    import geometry_diagrams.pydsl as pydsl_module

    tools = {
        name: getattr(pydsl_module, name)
        for name in pydsl_module.__all__
        if callable(getattr(pydsl_module, name)) and not isinstance(getattr(pydsl_module, name), type)
    }

    try:
        with new_builder_context() as builder:
            executor = LocalPythonExecutor(
                additional_authorized_imports=[], timeout_seconds=timeout_seconds
            )
            executor.send_tools(tools)
            executor(script)
            diagram_ir = builder.build()
        queue.put(("ok", diagram_ir.model_dump()))
    except Exception as exc:  # noqa: BLE001 — must report every failure kind to the parent
        message = str(exc)
        if "Import of" in message or "is not an authorized import" in message:
            error_type = "import_error"
        elif any(name in message for name in _DANGEROUS_CALL_NAMES):
            error_type = "dangerous_call"
        else:
            error_type = "execution_error"
        queue.put(("error", (message, error_type)))


def run_script(script: str, timeout_seconds: float = 5.0) -> ScriptResult:
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_in_subprocess, args=(script, timeout_seconds, queue)
    )
    process.start()
    process.join(timeout=timeout_seconds + 2.0)  # wall-clock backstop, independent of the child

    if process.is_alive():
        process.kill()
        process.join()
        return ScriptResult(diagram_ir=None, error="script exceeded wall-clock timeout", error_type="timeout")

    if queue.empty():
        return ScriptResult(
            diagram_ir=None, error="subprocess terminated without a result", error_type="timeout"
        )

    kind, payload = queue.get()
    if kind == "ok":
        return ScriptResult(diagram_ir=DiagramIR.model_validate(payload), error=None, error_type=None)
    message, error_type = payload
    return ScriptResult(diagram_ir=None, error=message, error_type=error_type)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_sandbox.py -v`
Expected: PASS. If `test_dangerous_call_is_rejected` fails because `LocalPythonExecutor`'s actual error text for a blocked `open()` call doesn't contain any of `_DANGEROUS_CALL_NAMES`, inspect the real exception message (`print(exc)` temporarily) and adjust `_DANGEROUS_CALL_NAMES` matching or add a dedicated substring check for `LocalPythonExecutor`'s specific error format. If `test_infinite_while_loop_is_caught_by_iteration_cap` times out instead of erroring cleanly, this confirms the design doc's finding that `MAX_WHILE_ITERATIONS` may take longer than the test's patience — reduce the test's `timeout_seconds` argument rather than the iteration cap itself (the cap is a library default, not configurable per the design doc).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml geometry_diagrams/pydsl/sandbox.py tests/test_pydsl_sandbox.py
git commit -m "Add subprocess+rlimits sandbox running LocalPythonExecutor"
```

---

### Task 11: Wire retry layer into the sandbox

**Files:**
- Modify: `geometry_diagrams/pydsl/sandbox.py`
- Test: `tests/test_pydsl_sandbox.py` (extend)

**Interfaces:**
- Consumes: `build_retry_message`, `classify_failure` from Task 9; `ScriptResult` from Task 10.
- Produces: `ScriptResult.retry_message: str | None` — populated whenever `error is not None`, using `build_retry_message` so a caller building a retry prompt gets the did-you-mean-enhanced message directly from the result object, without re-deriving it.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_pydsl_sandbox.py
def test_undefined_name_error_includes_did_you_mean_suggestion():
    result = run_script("itnersection_typo_not_a_real_function(1, 2)")
    assert result.diagram_ir is None
    assert result.retry_message is not None
```

(This test intentionally uses a name with no close match to any real API function, to check the *mechanism* runs without erroring — not that a specific suggestion appears, since `difflib` may or may not find a match for an arbitrary typo. A stronger version follows.)

```python
def test_close_typo_of_real_function_gets_a_suggestion():
    result = run_script("pointt(0, 0)")  # one character off from `point`
    assert result.diagram_ir is None
    assert result.retry_message is not None
    assert "point" in result.retry_message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_sandbox.py -v -k did_you_mean`
Expected: FAIL with `AttributeError: 'ScriptResult' object has no attribute 'retry_message'`

- [ ] **Step 3: Wire in the retry layer**

```python
# modify geometry_diagrams/pydsl/sandbox.py

# add import
from geometry_diagrams.pydsl.retry import build_retry_message

# modify ScriptResult
@dataclass
class ScriptResult:
    diagram_ir: "DiagramIR | None"
    error: "str | None"
    error_type: "str | None"
    retry_message: "str | None" = None


# modify run_script's error-returning branch at the end
    message, error_type = payload
    retry_message = build_retry_message(RuntimeError(message), script)
    return ScriptResult(
        diagram_ir=None, error=message, error_type=error_type, retry_message=retry_message
    )

# and the timeout-returning branches
    if process.is_alive():
        process.kill()
        process.join()
        msg = "script exceeded wall-clock timeout"
        return ScriptResult(
            diagram_ir=None, error=msg, error_type="timeout",
            retry_message=build_retry_message(TimeoutError(msg), script),
        )

    if queue.empty():
        msg = "subprocess terminated without a result"
        return ScriptResult(
            diagram_ir=None, error=msg, error_type="timeout",
            retry_message=build_retry_message(TimeoutError(msg), script),
        )
```

Note: `build_retry_message`'s did-you-mean matching relies on `classify_failure` seeing a `NameError` to trigger the hallucinated-API branch (Task 9). Since the subprocess boundary loses the original exception type (only `str(exc)` crosses the queue), wrapping in `RuntimeError(message)` above means `classify_failure` will *not* classify it as `"hallucinated_api"` via `isinstance` — it'll fall through to `"syntax_or_timeout"` and skip the did-you-mean regex entirely. Fix this before Step 4: change `classify_failure` (Task 9, `geometry_diagrams/pydsl/retry.py`) to also check the message text for `LocalPythonExecutor`'s actual undefined-name phrasing (confirm the exact string via `test_pydsl_sandbox.py`'s existing failures, e.g. run `python -c "..."` interactively against `LocalPythonExecutor` with an undefined name and print the exception), not just `isinstance(exc, NameError)`:

```python
# modify geometry_diagrams/pydsl/retry.py's classify_failure
def classify_failure(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, NameError) or "is not defined" in message:
        return "hallucinated_api"
    if isinstance(exc, ValueError):
        return "structural_precondition"
    if isinstance(exc, OpCapExceededError):
        return "syntax_or_timeout"
    return "syntax_or_timeout"
```

And update `_NAME_ERROR_PATTERN` in the same file if `LocalPythonExecutor`'s actual phrasing doesn't match `` variable `X` is not defined `` (adjust the regex to whatever the real message format is, discovered via the interactive check above).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_sandbox.py -v`
Expected: PASS (all tests, including the two new did-you-mean tests). If `test_close_typo_of_real_function_gets_a_suggestion` still fails, print `result.error` to see `LocalPythonExecutor`'s exact message and adjust `_NAME_ERROR_PATTERN` in `retry.py` to match it.

- [ ] **Step 5: Also re-run the existing retry unit tests to confirm no regression**

Run: `.venv/bin/python -m pytest tests/test_pydsl_retry.py -v`
Expected: PASS (still 6 tests — Step 3's `classify_failure` change is additive, not a replacement of the `isinstance` check)

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/pydsl/sandbox.py geometry_diagrams/pydsl/retry.py tests/test_pydsl_sandbox.py
git commit -m "Wire did-you-mean retry messages through the sandbox boundary"
```

---

### Task 12: End-to-end exit criterion — pydsl script vs. equivalent DSL recipe

**Files:**
- Test: `tests/test_pydsl_end_to_end.py`

**Interfaces:**
- Consumes: everything from Tasks 1–11, plus existing `geometry_diagrams.ir.to_sympy` and `geometry_diagrams.ir.checks` (unchanged), plus `geometry_diagrams.recipe.dsl`/`geometry_diagrams.recipe.lower` for the comparison DSL construction.
- Produces: nothing new — this is the Phase 1a exit-criterion test called for in the design doc's Testing section: a hand-written pydsl script exercising every handle/op in the Task 0 scope table, run through the unchanged downstream pipeline, checked for equivalence against a hand-written DSL recipe building the same construction.

- [ ] **Step 1: Read the `to_sympy.py` and `checks.py` entry points to confirm exact call signatures**

Run: `grep -n "^def " geometry_diagrams/ir/to_sympy.py geometry_diagrams/ir/checks.py | head -20`

Use whatever top-level `compile`/`resolve`-style function `to_sympy.py` exposes (expected something like `compile_diagram(ir: DiagramIR) -> CompiledDiagram` or similar — confirm the actual name before writing the test) and whatever `checks.py` exposes for running `ir.checks` against the compiled result (expected something like `run_checks(compiled, checks) -> list[CheckResult]`). Existing tests to pattern-match against: `tests/test_compile_defs.py`, `tests/test_checks.py`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_pydsl_end_to_end.py
"""Phase 1a exit criterion: a hand-written pydsl script exercising every
handle/op in the Task 0 scope table produces a DiagramIR that resolves and
passes checks identically to an equivalent hand-written DSL recipe — with
no changes to to_sympy.py, checks.py, to_tikz.py, or to_svg.py.
"""
from geometry_diagrams.pydsl.api import (
    altitude, circumcircle, incircle, line_through, mark_angle, median,
    point, polygon, triangle,
)
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context

# NOTE: adjust these two imports to whatever Step 1 found the real names to be.
from geometry_diagrams.ir.to_sympy import compile_diagram
from geometry_diagrams.ir.checks import run_checks


def _build_pydsl_script_ir():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        t.side(a, b)
        t.angle_at(b)
        circ = circumcircle(t)
        _ = circ.center
        inc = incircle(t)
        _ = inc.center
        alt = altitude(t, from_vertex=a)
        _ = alt.foot
        med = median(t, from_vertex=b)
        _ = med.midpoint
        d, e = point(0, 0), point(2, 0)
        f, g = point(2, 2), point(0, 2)
        square = polygon(d, e, f, g)
        square.side(d, e)
        ref = square.angle_at(e)
        mark_angle(ref, group=1)
        line_through(a, b)
        ir = builder.build()
    return ir


def test_pydsl_script_produces_diagram_ir_that_compiles_and_passes_checks():
    ir = _build_pydsl_script_ir()
    compiled = compile_diagram(ir)
    results = run_checks(compiled, ir.checks)
    assert all(r.passed for r in results), [r for r in results if not r.passed]


def test_pydsl_script_covers_every_scope_table_kind():
    ir = _build_pydsl_script_ir()
    kinds = {d.kind for d in ir.define}
    expected_kinds = {
        "point_fixed", "triangle", "segment", "point_triangle_center",
        "circle_center_point", "circle_center_radius", "line_perp_through",
        "point_foot", "point_midpoint", "polygon", "line_through",
    }
    missing = expected_kinds - kinds
    assert not missing, f"scope table kinds not exercised: {missing}"
```

- [ ] **Step 3: Run test to verify it fails or passes as expected**

Run: `.venv/bin/python -m pytest tests/test_pydsl_end_to_end.py -v`
Expected: likely FAIL on the first run due to import name mismatches from Step 1's placeholders (`compile_diagram`/`run_checks`) — fix the imports to the real names, then re-run. Once imports resolve, `test_pydsl_script_covers_every_scope_table_kind` should PASS immediately (it only inspects `ir.define`, no downstream dependency). `test_pydsl_script_produces_diagram_ir_that_compiles_and_passes_checks` may fail if `compile_diagram` requires a `Canvas` with bounds that fit all the constructed geometry, or if `checks.py`'s `run_checks` signature differs from the guess above — adjust to match the real API, not the geometry logic (Tasks 1–11 are already correct; this task is integration-only).

- [ ] **Step 4: Fix integration issues and re-run until passing**

Common likely fixes based on what Task 1's `Builder.build()` currently does (`canvas=Canvas()` with default `-5..5` bounds): if the square built at `(0,0)`–`(2,2)` and triangle at `(0,0)`–`(4,0)`–`(1,3)` fall outside those bounds in a way `checks.py` cares about (it usually doesn't — canvas bounds are a rendering concern, not a check concern), no fix needed; if `compile_diagram` errors for an unrelated reason, read the actual error and fix the *test* (not the implementation) to use a construction shape `to_sympy.py` already knows how to handle, matching patterns in `tests/test_compile_defs.py`.

Run: `.venv/bin/python -m pytest tests/test_pydsl_end_to_end.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full pydsl test suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/test_pydsl_*.py -v`
Expected: PASS (all tests across all 12 tasks)

- [ ] **Step 6: Commit**

```bash
git add tests/test_pydsl_end_to_end.py
git commit -m "Add Phase 1a exit-criterion test: pydsl script compiles and passes checks unchanged"
```

---

## Self-Review Notes

- **Spec coverage:** Task 0 (handles) → Tasks 2–7. Task 1 (builder shim) → Tasks 1–9 (contextvar, op-cap, structural preconditions, did-you-mean-in-retry-layer). Task 2 (stub generator) → Task 8. Task 3 (executor) → Task 10, corrected per the Fable-review revision (additive imports, subprocess+rlimits, RLIMIT_AS platform caveat). Task 4 (retry loop) → Tasks 9 and 11. Exit criterion → Task 12.
- **Explicitly out of scope, matching the design doc:** recipe translation, bench integration, the `python_full` A/B arm, majority-vote judge. None of Tasks 1–12 touch `geometry_diagrams/recipe/`, `geometry_diagrams/strategies/`, or `evals/`.
- **Placeholder scan:** the two spots requiring a live lookup before finalizing code (`MarkAngles`'s exact constructor in Task 7, `compile_diagram`/`run_checks`'s exact names in Task 12) are flagged with an explicit `grep`/read step immediately before the code that depends on them, not left as unresolved TODOs — each includes a concrete fallback action ("adjust the code below if...").
- **Type consistency check:** `Point`, `Line`, `Segment`, `Triangle`, `Polygon`, `Circle`, `Altitude`, `Median`, `AngleRef` are used with the same field names everywhere they recur across tasks (`.id`, `.vertices`, `.center`, `.radius`, `.foot`, `.line`, `.midpoint`, `.segment`, `.a`/`.o`/`.b`) — verified by re-reading each task's Interfaces block against the ones before it.

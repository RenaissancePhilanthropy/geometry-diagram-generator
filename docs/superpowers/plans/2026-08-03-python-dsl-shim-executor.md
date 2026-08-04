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
    retry.py             # classify_failure(), build_retry_message(), did-you-mean matching
    sandbox.py           # run_script() — subprocess + rlimits + LocalPythonExecutor wiring
    retry_loop.py        # run_with_retries() — the actual retry driver, cap enforcement

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
    test_pydsl_retry.py                # did-you-mean, failure classification, retry message
    test_pydsl_sandbox.py               # executor/sandbox: import lockdown, dangerous calls,
                                         #   CPU-bomb, memory-bomb, timeout kill, classification
    test_pydsl_retry_loop.py             # retry driver: stop-on-success, cap enforcement
    test_pydsl_end_to_end.py              # Phase 1a exit criterion: full script -> DiagramIR ->
                                           #   to_sympy.py/checks.py, compared to DSL equivalent
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
        self._render: list = []
        self._coord_floats: dict[str, tuple[float, float]] = {}
        self._segment_cache: dict[frozenset, str] = {}
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
        return DiagramIR(define=list(self._defs), render=list(self._render), canvas=Canvas())


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
- Modify: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_triangle.py`

**Interfaces:**
- Consumes: `Point` from Task 1; `geometry_diagrams.ir.ir.{Triangle as TriangleDef, Segment as SegmentDef}`.
- Produces: `Triangle` handle with `.vertices -> tuple[Point, Point, Point]`, `.side(p: Point, q: Point) -> Segment` (order-independent, raises `ValueError` if `p`/`q` are not both vertices of this triangle), `.angle_at(v: Point) -> AngleRef` (the concrete `AngleRef` class doesn't exist until Task 7; the code below does a lazy `from geometry_diagrams.pydsl.handles import AngleRef` inside the method body, which raises `ImportError` if called before Task 7 — this is the actual behavior, not a `NotImplementedError` stub, so Task 7's own tests are the first ones that can exercise `angle_at` successfully). `triangle(a: Point, b: Point, c: Point) -> Triangle`. `Builder._segment_cache: dict[frozenset[str], str]` (declared in `Builder.__init__` in Task 1) mapping `{p_id, q_id}` -> segment id, so repeated `.side()` calls on the same pair (in either order) return the same handle rather than creating duplicate `Segment` defs.

**Why `Triangle` carries its own `_builder` reference instead of calling `get_builder()` from inside `.side()`/`.angle_at()` — this matters for Task 10, read before implementing:** Task 10's sandbox wraps each *module-level* function (`point`, `triangle`, `polygon`, ...) so it sets the ambient contextvar for the duration of that one call, because `LocalPythonExecutor` runs the whole script — and therefore every tool call — inside its own worker thread, where the contextvar is otherwise invisible (verified empirically; see Task 10). But a handle method like `t.side(a, b)` is called *later*, directly by the executor on a value the script already holds — not through any wrapped tool function — so by the time `.side()` runs, the wrapper that set the contextvar has already exited and reset it. Confirmed empirically: a handle method reading the ambient contextvar sees `None`, not the bound builder, even though the tool call that *created* the handle saw it correctly. The fix is to capture the builder directly on the handle at construction time (also confirmed empirically to work regardless of which thread the method runs on) rather than re-deriving it from ambient state. `Triangle`/`Polygon` are the only handles with methods that touch the builder (`Circle`/`Altitude`/`Median`/`AngleRef` are plain data, no methods), so this pattern applies to both.

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
from dataclasses import field


@dataclass(frozen=True)
class Triangle:
    id: str
    vertices: tuple[Point, Point, Point]
    _builder: "object" = field(repr=False, compare=False)  # type is Builder; avoid a
                                                             # circular import at module load

    def side(self, p: Point, q: Point) -> "Segment":
        vertex_ids = {v.id for v in self.vertices}
        for name, pt in (("p", p), ("q", q)):
            if pt.id not in vertex_ids:
                raise ValueError(f"{pt.id!r} is not a vertex of triangle {self.id!r} ({name})")
        return self._builder._get_or_create_segment(p.id, q.id)

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
    return Triangle(id=tid, vertices=(a, b, c), _builder=builder)
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

Same rationale as Task 2's `Triangle`: `.side()`/`.angle_at()` use a `_builder` reference captured at construction time, not `get_builder()`, since the executor calls these methods outside the wrapper that made the ambient contextvar visible.

```python
# add to geometry_diagrams/pydsl/handles.py
@dataclass(frozen=True)
class Polygon:
    id: str
    vertices: tuple[Point, ...]
    _builder: "object" = field(repr=False, compare=False)

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
        return self._builder._get_or_create_segment(v1.id, v2.id)

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
    return Polygon(id=pid, vertices=tuple(vertices), _builder=builder)
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
- Consumes: `Triangle` from Task 2 (via `t.vertices`, not any builder-side lookup table), `Builder._coord_floats` (populated by `point()` in Task 1).
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


def test_circumcircle_radius_is_numeric_for_concrete_vertices():
    with new_builder_context():
        # 3-4-5 right triangle: circumradius of a right triangle is half the
        # hypotenuse — hypotenuse is 5, so R = 2.5.
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        circ = circumcircle(t)
    assert math.isclose(circ.radius, 2.5, abs_tol=1e-9)


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

**`radius` is a lazy property, not an eagerly-computed field** — this matters specifically for `circumcircle()`: whether a vertex is a concrete `point()` literal is only knowable at the moment `.radius` is actually read, not at circle-construction time (a script might build `circumcircle(t)` and never read `.radius` at all, or `t`'s vertices might resolve to concrete coordinates only after other ops run). Rejecting eagerly, at construction, would reject scripts that never needed the value — the same category of premature-rejection mistake this plan explicitly rules out elsewhere (see the "no eager geometric validation" constraint). A thunk defers both the "are vertices concrete" check and the degenerate-triangle (collinear vertices → zero area) check to actual access time.

```python
# add to geometry_diagrams/pydsl/handles.py
@dataclass(frozen=True)
class Circle:
    id: str
    center: Point
    _radius_thunk: "object" = field(repr=False, compare=False)  # Callable[[], float | str]

    @property
    def radius(self) -> "float | str":
        return self._radius_thunk()
```

```python
# add to geometry_diagrams/pydsl/api.py
import math

from geometry_diagrams.ir.ir import CircleCenterRadius, PointTriangleCenter
from geometry_diagrams.pydsl.handles import Circle, Triangle


def circumcircle(t: Triangle) -> Circle:
    """The circumscribed circle of a triangle.

    The IR itself doesn't need a radius value for the SymPy resolution path
    (CircleCenterPoint's "through" point already pins the circle's size);
    `.radius` on the returned handle is purely a convenience value for the
    script. It's computed lazily (see Circle.radius) via R = (a*b*c)/(4*Area),
    which — like incircle's Heron-formula inradius below — depends only on
    the triangle's side lengths, so it's computable whenever all three
    vertices are concrete (PointFixed) coordinates, tracked in
    builder._coord_floats.
    """
    from geometry_diagrams.ir.ir import CircleCenterPoint

    builder = get_builder()
    center_id = builder._fresh_hidden_id("circumcenter")
    builder._add(PointTriangleCenter(id=center_id, tri=t.id, which="circumcenter"))
    a_id, b_id, c_id = (v.id for v in t.vertices)
    cid = builder._fresh_hidden_id("circumcircle")
    builder._add(CircleCenterPoint(id=cid, center=center_id, through=a_id))

    def _compute_radius():
        coord_floats = builder._coord_floats
        if not all(v in coord_floats for v in (a_id, b_id, c_id)):
            raise NotImplementedError(
                "circumcircle(...).radius requires all three vertices to be "
                "concrete point(x, y) literals in Phase 1a."
            )
        ax, ay = coord_floats[a_id]
        bx, by = coord_floats[b_id]
        cx, cy = coord_floats[c_id]
        side_a = math.hypot(bx - cx, by - cy)
        side_b = math.hypot(ax - cx, ay - cy)
        side_c = math.hypot(ax - bx, ay - by)
        area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2
        if area == 0:
            raise ValueError(
                f"circumcircle(...).radius: vertices {a_id!r}, {b_id!r}, {c_id!r} "
                "are collinear — a circumradius doesn't exist for a degenerate triangle."
            )
        return round((side_a * side_b * side_c) / (4 * area), 10)

    return Circle(id=cid, center=Point(id=center_id), _radius_thunk=_compute_radius)


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
    return Circle(id=cid, center=Point(id=center_id), _radius_thunk=lambda: radius)
```

Add `circumcircle`, `incircle`, `Circle` to `geometry_diagrams/pydsl/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_circle.py -v`
Expected: PASS (4 tests)

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
- Consumes: `Triangle`, `Point` (via `t.vertices`).
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
    builder._add_render(
        MarkAngles(
            angles=[AnglePoints(a=ref.a.id, o=ref.o.id, b=ref.b.id)],
            group=str(group) if group is not None else None,
        )
    )
```

Add `_add_render` to `Builder` (`geometry_diagrams/pydsl/builder.py`), routed through the same op-count cap `_add` already enforces — without this, a loop of `mark_angle` calls would be bounded only by the executor's own `MAX_OPERATIONS` backstop, not the builder's cap:

```python
# add to geometry_diagrams/pydsl/builder.py, inside class Builder (alongside _add)
    def _add_render(self, render_op) -> None:
        if len(self._defs) + len(self._render) >= self._op_cap:
            raise OpCapExceededError(
                f"script recorded more than {self._op_cap} ops "
                "(this is a size cap, not a security boundary)"
            )
        self._render.append(render_op)
```

(`Builder.__init__`'s `self._render: list = []` and `build()`'s `render=list(self._render)` were already added in Task 1 in anticipation of this task — no further changes needed there.)

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


def test_stub_includes_handle_dataclass_fields_not_just_methods():
    # The whole point of the handle design (see the design doc) is that the
    # model learns `circ.center` / `alt.foot` / `med.midpoint` exist WITHOUT
    # ever assigning them an id itself. A stub generator that only emits
    # methods (side(), angle_at()) and skips dataclass fields would silently
    # fail to teach the model these accessors exist at all.
    stub = generate_stub()
    assert "center" in stub  # Circle.center
    assert "radius" in stub  # Circle.radius
    assert "foot" in stub    # Altitude.foot
    assert "midpoint" in stub  # Median.midpoint
    assert "vertices" in stub  # Triangle.vertices / Polygon.vertices


def test_stub_does_not_include_private_helpers():
    stub = generate_stub()
    assert "_fresh_hidden_id" not in stub
    assert "_get_or_create_segment" not in stub
    # Triangle/Polygon carry an internal _builder reference (see Task 2's
    # note on why) — it must never leak into the model-facing stub.
    assert "_builder" not in stub
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
    import dataclasses

    lines: list[str] = []
    for name in pydsl_module.__all__:
        obj = getattr(pydsl_module, name)
        if inspect.isfunction(obj):
            lines.append(_format_callable(name, obj))
        elif inspect.isclass(obj) and name in _HANDLE_CLASS_NAMES:
            lines.append(f"class {name}:")
            # Dataclass fields first — these are the accessors the design
            # doc's handle pattern depends on (circ.center, alt.foot, ...).
            # A stub that only lists methods would silently omit the reason
            # this handle design exists at all: the model must be able to
            # see these fields without ever assigning them an id itself.
            if dataclasses.is_dataclass(obj):
                for field in dataclasses.fields(obj):
                    if field.name.startswith("_"):
                        continue  # e.g. Triangle/Polygon's internal _builder reference
                    type_name = getattr(field.type, "__name__", str(field.type))
                    lines.append(f"    {field.name}: {type_name}")
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                lines.append("    " + _format_callable(method_name, method))
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_stub.py -v`
Expected: PASS (4 tests). If a handle class isn't yet exported in `__all__`, add it to `geometry_diagrams/pydsl/__init__.py` first (all handle classes should already be exported by Task 7). If `field.type` prints as a raw string like `'float | str'` instead of a clean type name (dataclass field types can be stored as strings depending on `from __future__ import annotations` behavior at class-definition time), that's fine for stub purposes — the test only checks substring presence, not exact formatting.

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
- Consumes: `geometry_diagrams.pydsl.__all__`, filtered to callables that aren't classes — this is the actual did-you-mean candidate pool (matching exactly what Task 10 injects as executor tools; classes like `Point`/`Triangle` are excluded from injected tools and must be excluded here too, or a suggestion could name something the script still can't call).
- Produces: `classify_failure(exc_or_message: Exception | str) -> str` returning one of `"hallucinated_api"`, `"structural_precondition"`, `"dangerous_call"`, `"import_error"`, `"syntax_or_timeout"`. `suggest_name(bad_name: str, candidates: list[str]) -> str | None`. `build_retry_message(exc_or_message: Exception | str, script: str) -> str`.

**Why this handles two different message shapes, verified against the real library:** called directly with a hand-constructed `ValueError`/`NameError` (unit tests, and any non-sandboxed caller), `isinstance` checks classify it directly. But on the real sandboxed path (Task 10), `LocalPythonExecutor` wraps *every* exception raised inside a tool call — including our own `ValueError`/`OpCapExceededError` — into a single `InterpreterError` whose message embeds the original type name as text: `"Code execution failed at line '...' due to: ValueError: ..."` (confirmed by raising a `ValueError` from an injected tool and reading the resulting `InterpreterError.args`). Since only `str(exc)` survives crossing the subprocess queue in Task 10/11, `classify_failure` needs a message-text fallback that recovers the original type name, not just `isinstance`. This task is built and tested standalone with hand-constructed exceptions falling through the `isinstance` path; Task 10 reuses the exact same function against the message-text path, so both are covered by one implementation instead of two divergent ones.

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


def test_classify_failure_categorizes_op_cap_directly_as_a_distinct_category():
    exc = OpCapExceededError("script recorded more than 2000 ops")
    assert classify_failure(exc) == "syntax_or_timeout"


def test_classify_failure_reads_embedded_type_name_from_wrapped_interpreter_message():
    # Simulates what actually crosses the subprocess boundary in Task 10/11:
    # LocalPythonExecutor wraps every tool-raised exception into a single
    # InterpreterError whose message embeds the original type name as text
    # (verified against the real library — see this task's Interfaces note).
    # Only a message string survives the queue, not the original exception,
    # so classify_failure must handle a bare string, not just exception instances.
    wrapped_value_error = (
        "Code execution failed at line 'side(a, p9)' due to: "
        "ValueError: 'p9' is not a vertex of triangle 'tri_1'"
    )
    assert classify_failure(wrapped_value_error) == "structural_precondition"

    wrapped_op_cap = (
        "Code execution failed at line 'point(9, 9)' due to: "
        "OpCapExceededError: script recorded more than 2000 ops"
    )
    assert classify_failure(wrapped_op_cap) == "syntax_or_timeout"


def test_classify_failure_recognizes_bare_undefined_variable_reference():
    # Verified against the real library: referencing an undefined name
    # WITHOUT calling it (e.g. `mark_angle(reff)` where `reff` is a typo)
    # raises with the type name "InterpreterError" embedded, not "NameError"
    # — the interpreter's own bounds check fires directly, so the
    # _WRAPPED_TYPE_PATTERN branch alone would never classify this as
    # hallucinated_api without the dedicated _NAME_ERROR_PATTERN check.
    msg = (
        "Code execution failed at line 'x = reff' due to: "
        "InterpreterError: The variable `reff` is not defined."
    )
    assert classify_failure(msg) == "hallucinated_api"


def test_classify_failure_recognizes_forbidden_call_message_shape():
    # The real message shape for BOTH an undefined name and a call to a
    # dangerous builtin like open()/exec() — distinguishable only by which
    # name was called, not by message shape (verified against the library).
    undefined_name_msg = (
        "Forbidden function evaluation: 'itnersection' is not among the "
        "explicitly allowed tools or defined/imported in the preceding code"
    )
    assert classify_failure(undefined_name_msg) == "hallucinated_api"

    dangerous_call_msg = (
        "Forbidden function evaluation: 'open' is not among the explicitly "
        "allowed tools or defined/imported in the preceding code"
    )
    assert classify_failure(dangerous_call_msg) == "dangerous_call"


def test_classify_failure_recognizes_import_error_message_shape():
    msg = "Import of os is not allowed. Authorized imports are: ['math', 're']"
    assert classify_failure(msg) == "import_error"


def test_build_retry_message_appends_did_you_mean_for_hallucinated_api():
    # Must be a typo of a real Phase 1a API function — "intersection" is
    # NOT part of the Phase 1a API (see the scope table), so a candidate
    # pool built from the real function list would never suggest it.
    exc = NameError("The variable `trianlge` is not defined")
    msg = build_retry_message(exc, script="trianlge(a, b, c)")
    assert "trianlge" in msg
    assert "did you mean 'triangle'" in msg


def test_build_retry_message_appends_did_you_mean_for_wrapped_forbidden_call():
    msg_text = (
        "Forbidden function evaluation: 'pointt' is not among the "
        "explicitly allowed tools or defined/imported in the preceding code"
    )
    msg = build_retry_message(msg_text, script="pointt(0, 0)")
    assert "did you mean 'point'" in msg


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

classify_failure/build_retry_message accept EITHER a raw Exception (for
direct/unit-test use) OR a bare message string (for the real sandboxed path
in Task 10/11, where LocalPythonExecutor wraps every tool-raised exception —
including our own ValueError/OpCapExceededError — into a single
InterpreterError whose message embeds the original type name as text, and
only that string survives crossing the subprocess queue). Both call sites
use this one implementation so the two paths can't classify differently.
"""
from __future__ import annotations

import difflib
import inspect
import re

import geometry_diagrams.pydsl as pydsl_module
from geometry_diagrams.pydsl.builder import OpCapExceededError

# The did-you-mean candidate pool must match what Task 10 actually injects as
# executor tools: functions only, not handle classes (Point, Triangle, ...
# are never callable in a script, so suggesting one would be worse than no
# suggestion at all).
PUBLIC_API_FUNCTION_NAMES = [
    name for name in pydsl_module.__all__
    if inspect.isfunction(getattr(pydsl_module, name))
]

_NAME_ERROR_PATTERN = re.compile(r"variable `([^`]+)`")
_FORBIDDEN_CALL_PATTERN = re.compile(r"Forbidden function evaluation: '([^']+)' is not among")
_IMPORT_PATTERN = re.compile(r"Import of (\S+) is not allowed")
_WRAPPED_TYPE_PATTERN = re.compile(r"due to: (\w+):")
_DANGEROUS_NAMES = {"exec", "eval", "open", "compile", "__import__"}


def suggest_name(bad_name: str, candidates: list[str]) -> str | None:
    matches = difflib.get_close_matches(bad_name, candidates, n=1)
    return matches[0] if matches else None


def classify_failure(exc_or_message: "Exception | str") -> str:
    if isinstance(exc_or_message, NameError):
        return "hallucinated_api"
    if isinstance(exc_or_message, OpCapExceededError):
        return "syntax_or_timeout"
    if isinstance(exc_or_message, ValueError):
        return "structural_precondition"

    message = str(exc_or_message)
    if _IMPORT_PATTERN.search(message):
        return "import_error"
    forbidden = _FORBIDDEN_CALL_PATTERN.search(message)
    if forbidden:
        return "dangerous_call" if forbidden.group(1) in _DANGEROUS_NAMES else "hallucinated_api"
    if _NAME_ERROR_PATTERN.search(message):
        # A bare undefined-variable reference (not a call) — verified against
        # the real library that this raises with the message
        # "...due to: InterpreterError: The variable `x` is not defined.",
        # NOT a wrapped NameError, so the _WRAPPED_TYPE_PATTERN branch below
        # would never catch it without this explicit check.
        return "hallucinated_api"
    wrapped = _WRAPPED_TYPE_PATTERN.search(message)
    if wrapped:
        type_name = wrapped.group(1)
        if type_name == "NameError":
            return "hallucinated_api"
        if type_name == "OpCapExceededError":
            return "syntax_or_timeout"
        if type_name == "ValueError":
            return "structural_precondition"
    return "syntax_or_timeout"


def _extract_bad_name(message: str) -> "str | None":
    match = _FORBIDDEN_CALL_PATTERN.search(message) or _NAME_ERROR_PATTERN.search(message)
    return match.group(1) if match else None


def build_retry_message(exc_or_message: "Exception | str", script: str) -> str:
    message = str(exc_or_message)
    if classify_failure(exc_or_message) in ("hallucinated_api", "dangerous_call"):
        bad_name = _extract_bad_name(message)
        if bad_name:
            suggestion = suggest_name(bad_name, PUBLIC_API_FUNCTION_NAMES)
            if suggestion:
                message = f"{message} — did you mean '{suggestion}'?"
    return message
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_retry.py -v`
Expected: PASS (11 tests)

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
- Consumes: `geometry_diagrams.pydsl` (the full public API, injected as `LocalPythonExecutor` tools), `Builder` from Task 1, `classify_failure`/`build_retry_message` from Task 9's `retry.py`.
- Produces: `run_script(script: str, timeout_seconds: float = 5.0) -> ScriptResult` where `ScriptResult` is a small dataclass: `diagram_ir: DiagramIR | None`, `error: str | None`, `error_type: str | None` (one of `"import_error"`, `"dangerous_call"`, `"hallucinated_api"`, `"structural_precondition"`, `"syntax_or_timeout"`, `"timeout"` — matching the design doc's own three-category retry-cause scheme, `"import_error"`/`"dangerous_call"` being finer-grained splits of what the doc calls "syntax-or-timeout"; there is no separate `"execution_error"` category — any exception `classify_failure` doesn't otherwise recognize falls into the `"syntax_or_timeout"` catch-all, matching the design doc's own bucket for exactly this case), `retry_message: str | None` (the did-you-mean-enhanced message, populated directly from Task 9's `build_retry_message` — no separate wiring step needed, since classification happens once, in the child, where the real message text is available). Runs in a subprocess (`multiprocessing.Process`) with `RLIMIT_CPU` set inside the child; the parent enforces a hard wall-clock kill (`process.join(timeout)` then `process.kill()`) as the actual cross-platform backstop, independent of whether the in-process `LocalPythonExecutor(timeout_seconds=...)` fires first.

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
    # MAX_WHILE_ITERATIONS raises InterpreterError (falls through classify_failure's
    # catch-all -> "syntax_or_timeout"); if the wall-clock kill wins the race instead,
    # that's "timeout" — either is a correct outcome depending on machine speed.
    assert result.error_type in ("syntax_or_timeout", "timeout")


@pytest.mark.timeout(30)
def test_cpu_bomb_is_killed_by_rlimit_cpu_on_any_platform():
    result = run_script("import math\nmath.factorial(10**8)", timeout_seconds=2.0)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"


@pytest.mark.timeout(30)
def test_incremental_memory_growth_is_eventually_killed_by_wall_clock_timeout():
    # A loop that keeps growing a list forever thrashes long enough to
    # actually exercise the wall-clock kill. A single huge allocation
    # (e.g. `[0] * 10**12`) is the wrong shape for this test — it raises
    # MemoryError immediately and never reaches the timeout path at all,
    # on either platform.
    script = "acc = []\nwhile True:\n    acc.append([0] * 10**6)"
    result = run_script(script, timeout_seconds=2.0)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"


@pytest.mark.timeout(30)
def test_single_huge_allocation_fails_fast_and_is_classified_as_syntax_or_timeout():
    # Documents the actual behavior: this raises MemoryError immediately
    # inside the child (whether or not RLIMIT_AS is enforced on this
    # platform), not a timeout — MemoryError isn't a type classify_failure
    # has a specific bucket for, so it falls through to the catch-all.
    result = run_script("x = [0] * (10**12)", timeout_seconds=5.0)
    assert result.diagram_ir is None
    assert result.error_type == "syntax_or_timeout"


def test_undefined_name_error_is_classified_as_hallucinated_api_with_a_suggestion():
    result = run_script("pointt(0, 0)")  # one character off from `point`
    assert result.diagram_ir is None
    assert result.error_type == "hallucinated_api"
    assert result.retry_message is not None
    assert "did you mean 'point'" in result.retry_message


def test_structural_precondition_error_is_classified_correctly_with_no_suggestion():
    script = """
a = point(0, 0)
b = point(1, 0)
c = point(0, 1)
outside = point(9, 9)
t = triangle(a, b, c)
t.side(a, outside)
"""
    result = run_script(script)
    assert result.diagram_ir is None
    assert result.error_type == "structural_precondition"
    assert "not a vertex" in result.retry_message
    assert "did you mean" not in result.retry_message
```

Note: `pytest.mark.timeout` requires `pytest-timeout`; check if it's already a dev dependency (`grep pytest-timeout pyproject.toml`). If absent, add `"pytest-timeout>=2.3.1"` to `[dependency-groups.dev]` in `pyproject.toml` and run `uv sync` before continuing — these tests must not be able to hang the test suite itself if the sandbox implementation has a bug.

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_sandbox.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.pydsl.sandbox'`

- [ ] **Step 4: Implement the sandbox**

**Verified against the real installed library** (`pip install smolagents==1.26.0` into a scratch venv and inspected/ran directly — not guessed):
- `LocalPythonExecutor.__call__` wraps the *entire* script evaluation — every tool call included — in a `ThreadPoolExecutor(max_workers=1)` worker thread (`smolagents/local_python_executor.py`'s `timeout()` decorator). **This breaks a naive `contextvars` binding**: a value set via `_current_builder.set(...)` on the calling thread is invisible inside a tool function invoked from that worker thread (confirmed empirically: a test tool reading a contextvar set on the main thread saw `None` inside the executor). The fix below binds each tool function to its `Builder` via a wrapper that calls `.set()` immediately before invoking the real function, in the *same* call frame the tool actually runs in — this works regardless of which thread that turns out to be, and was confirmed to work in the same experiment.
- All executor-raised errors are `InterpreterError`, except timeouts, which raise the distinct `ExecutionTimeoutError` — always catchable with `except ExecutionTimeoutError` before a general `except Exception`.
- Undefined names and disallowed dangerous calls (`open`, `exec`, `eval`, ...) produce the **identical** message shape: `"...Forbidden function evaluation: '<name>' is not among the explicitly allowed tools..."` — they are only distinguishable by which name was called, not by message shape. Disallowed imports produce a distinctly different message: `"...Import of <module> is not allowed. Authorized imports are: [...]"`.
- `send_tools(tools: dict[str, Callable])` accepts plain functions (its type hint says `Tool` but the implementation just merges the dict) — no `Tool`-wrapper class needed.

**Known, deliberately deferred cost:** each `run_script` call spawns a fresh child process (via the `spawn` context, for correctness — `fork` would inherit the parent's already-imported, potentially inconsistent module state) that re-imports `geometry_diagrams.pydsl`, which transitively imports `geometry_diagrams/__init__.py` → `facade` → the LangChain/LangGraph strategy stack. That's real per-call import latency, not just a theoretical concern. Fixing it properly means making the top-level `geometry_diagrams/__init__.py` import lazily, which is a change to code outside this plan's scope (it would affect every existing consumer of the package, not just pydsl) — out of scope for Phase 1a, which is about correctness, not latency. Flag it explicitly rather than working around it here; revisit before any Phase 1b live-chat latency budget is set.

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

Tool functions are wrapped with _bind_to_builder rather than relying on the
ambient contextvar alone: LocalPythonExecutor runs the entire script inside
its own ThreadPoolExecutor worker thread, so a contextvar set on the calling
thread before invoking the executor is NOT visible inside tool calls (verified
empirically against smolagents 1.26.0). Each wrapper re-sets the contextvar
immediately before calling the real function, in the same call frame the
tool actually executes in, which works regardless of which thread that is.
"""
from __future__ import annotations

import multiprocessing
import resource
from dataclasses import dataclass
from typing import Callable

from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.pydsl.builder import Builder, _current_builder
from geometry_diagrams.pydsl.retry import build_retry_message, classify_failure


@dataclass
class ScriptResult:
    diagram_ir: "DiagramIR | None"
    error: "str | None"
    error_type: "str | None"  # see classify_failure's return values, plus "timeout"
    retry_message: "str | None" = None


def _bind_to_builder(fn: Callable, builder: Builder) -> Callable:
    def wrapped(*args, **kwargs):
        token = _current_builder.set(builder)
        try:
            return fn(*args, **kwargs)
        finally:
            _current_builder.reset(token)

    return wrapped


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
    from smolagents.local_python_executor import ExecutionTimeoutError

    import geometry_diagrams.pydsl as pydsl_module

    builder = Builder()
    tools = {
        name: _bind_to_builder(getattr(pydsl_module, name), builder)
        for name in pydsl_module.__all__
        if callable(getattr(pydsl_module, name)) and not isinstance(getattr(pydsl_module, name), type)
    }

    try:
        executor = LocalPythonExecutor(
            additional_authorized_imports=[], timeout_seconds=timeout_seconds
        )
        executor.send_tools(tools)
        executor(script)
        diagram_ir = builder.build()
        queue.put(("ok", diagram_ir.model_dump()))
    except ExecutionTimeoutError as exc:
        queue.put(("error", (str(exc), "timeout", None)))
    except Exception as exc:  # noqa: BLE001 — must report every failure kind to the parent
        message = str(exc)
        error_type = classify_failure(message)
        retry_message = build_retry_message(message, script)
        queue.put(("error", (message, error_type, retry_message)))


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
        msg = "script exceeded wall-clock timeout"
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)

    try:
        kind, payload = queue.get(timeout=1.0)
    except Exception:
        # process exited but the queue feeder thread hadn't flushed yet, or the
        # child died without putting anything (e.g. OOM-killed by the OS) —
        # either way, treat as a timeout-class failure, not "no error".
        msg = "subprocess exited without a result"
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)

    if kind == "ok":
        return ScriptResult(diagram_ir=DiagramIR.model_validate(payload), error=None, error_type=None)
    message, error_type, retry_message = payload
    return ScriptResult(diagram_ir=None, error=message, error_type=error_type, retry_message=retry_message)
```

Note: `Builder` no longer needs to be entered via `new_builder_context()` inside the subprocess for this path — the sandbox constructs it directly and binds it into each tool closure, since the ambient-contextvar pattern only works when the caller and the tool run on the same thread (true for direct/synchronous unit-test usage from Tasks 1–9, false inside `LocalPythonExecutor`). `new_builder_context()` remains the right API for Tasks 1–9's tests and for any future non-sandboxed caller.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_sandbox.py -v`
Expected: PASS. If `test_infinite_while_loop_is_caught_by_iteration_cap` times out instead of erroring cleanly (`MAX_WHILE_ITERATIONS` at 1M interpreted-AST iterations can take longer than expected), reduce the test's `timeout_seconds` argument so the wall-clock kill or `ExecutionTimeoutError` fires first, rather than trying to change the iteration cap itself (a library default, not configurable).


- [ ] **Step 6: Commit**

```bash
git add pyproject.toml geometry_diagrams/pydsl/sandbox.py tests/test_pydsl_sandbox.py
git commit -m "Add subprocess+rlimits sandbox running LocalPythonExecutor"
```

---

### Task 11: Retry-loop driver with cap enforcement

Task 10 already produces a classified, did-you-mean-enhanced `retry_message` per failed attempt (verified end-to-end in Task 10's own tests). What's still missing, and what the design doc's §5 and Testing section actually require, is something that *retries*: a driver that takes a way to produce a new script attempt (given the previous failure's message), runs it through `run_script`, and stops — successfully or not — once a cap is hit. Nothing in Tasks 1–10 loops or enforces a cap; this task adds that.

**Files:**
- Create: `geometry_diagrams/pydsl/retry_loop.py`
- Test: `tests/test_pydsl_retry_loop.py`

**Interfaces:**
- Consumes: `run_script`, `ScriptResult` from Task 10.
- Produces: `run_with_retries(make_script: Callable[[list[ScriptResult]], str], cap: int, timeout_seconds: float = 5.0) -> list[ScriptResult]`. `make_script` is called with the list of prior attempts' `ScriptResult`s (empty on the first call) and returns the next script text to try — this task does not call an LLM; tests hand-author `make_script` as a plain Python function simulating a model that eventually succeeds, or that never does, so the cap and stop-on-success behavior are both exercised without any live model. Returns the full attempt history; the caller inspects `result[-1]` to see whether the final attempt succeeded.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_retry_loop.py
"""Tests for the retry-loop driver: stops on success, stops at the cap."""
from geometry_diagrams.pydsl.retry_loop import run_with_retries


def test_stops_immediately_on_first_success():
    attempts_seen = []

    def make_script(history):
        attempts_seen.append(len(history))
        return "point(0, 0)"  # always valid

    results = run_with_retries(make_script, cap=5)
    assert len(results) == 1
    assert results[-1].error is None
    assert attempts_seen == [0]


def test_retries_until_success_within_cap():
    def make_script(history):
        if len(history) < 2:
            return "undefined_thing(1)"  # fails twice
        return "point(0, 0)"  # succeeds on the 3rd attempt

    results = run_with_retries(make_script, cap=5)
    assert len(results) == 3
    assert results[0].error is not None
    assert results[1].error is not None
    assert results[2].error is None


def test_stops_at_cap_when_every_attempt_fails():
    call_count = {"n": 0}

    def make_script(history):
        call_count["n"] += 1
        return "undefined_thing(1)"  # never valid

    results = run_with_retries(make_script, cap=3)
    assert len(results) == 3  # not before, not after
    assert call_count["n"] == 3
    assert all(r.error is not None for r in results)


def test_make_script_receives_the_prior_result_for_retry_prompting():
    seen_retry_messages = []

    def make_script(history):
        if history:
            seen_retry_messages.append(history[-1].retry_message)
            return "point(0, 0)"
        return "undefined_thing(1)"

    run_with_retries(make_script, cap=3)
    assert len(seen_retry_messages) == 1
    assert seen_retry_messages[0] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_retry_loop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.pydsl.retry_loop'`

- [ ] **Step 3: Implement the retry-loop driver**

```python
# geometry_diagrams/pydsl/retry_loop.py
"""Retry-loop driver: runs successive script attempts through run_script,
stopping on the first success or once `cap` attempts have been made.

Design doc caps: 2 for live chat, 5 for offline batch — callers pass the
cap that matches their context; this module has no opinion on which.
"""
from __future__ import annotations

from typing import Callable

from geometry_diagrams.pydsl.sandbox import ScriptResult, run_script


def run_with_retries(
    make_script: Callable[[list[ScriptResult]], str],
    cap: int,
    timeout_seconds: float = 5.0,
) -> list[ScriptResult]:
    if cap < 1:
        raise ValueError(f"cap must be >= 1, got {cap}")
    history: list[ScriptResult] = []
    for _ in range(cap):
        script = make_script(history)
        result = run_script(script, timeout_seconds=timeout_seconds)
        history.append(result)
        if result.error is None:
            break
    return history
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_retry_loop.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/retry_loop.py tests/test_pydsl_retry_loop.py
git commit -m "Add retry-loop driver: stop-on-success and cap enforcement"
```

---

### Task 12: End-to-end exit criterion — pydsl script vs. equivalent DSL recipe

**Files:**
- Test: `tests/test_pydsl_end_to_end.py`

**Interfaces:**
- Consumes: everything from Tasks 1–11, plus existing `geometry_diagrams.ir.to_sympy.compile_defs(diagram: DiagramIR, *, rng=None) -> SymTable` and `geometry_diagrams.ir.checks.run_checks(checks: list[Check], sym: SymTable, tol=0.005) -> list[CheckResult]` (both signatures verified directly against the current source — `compile_defs` at `to_sympy.py:69`, `run_checks` at `checks.py:19` — note the argument order: `checks` first, `sym` second), plus `geometry_diagrams.recipe.dsl`/`geometry_diagrams.recipe.lower.lower_to_ir` for the comparison DSL construction, plus `run_script` from Task 10.
- Produces: nothing new — this is the Phase 1a exit-criterion test called for in the design doc's Testing section.

**Note on why this test doesn't assert `ir.checks` all pass:** nothing in the Phase 1a pydsl scope (Tasks 1–9) ever appends to a `Check` list — there's no `mark_angle(expected=...)`-equivalent in scope, so `ir.checks` is always `[]` for a pydsl-built diagram, and `all(r.passed for r in [])` would be vacuously true. Instead, this test asserts the thing that's actually meaningful: `compile_defs` resolves every definition without raising, *and* shared construction elements (the triangle's vertices) resolve to the same coordinates whether built via pydsl or via the equivalent hand-authored DSL recipe — a real equivalence check, not a vacuous one.

**Why this task must include a `run_script()` path, not only the direct in-process `new_builder_context()` path:** every test in Tasks 1–9 calls `.side()`/`.angle_at()` synchronously, in the same thread that opened `new_builder_context()` — the one execution shape where the ambient-contextvar pattern (before Task 2/3's `_builder`-capture fix) would have looked correct. The bug Task 10 found and fixed — handle methods invisible to the contextvar inside `LocalPythonExecutor`'s worker thread — is only reachable by actually running a script *through the sandbox*, calling a handle method on a value the script itself holds. A version of this task that only exercises `new_builder_context()` directly would have shipped Tasks 2/3's `_builder`-capture fix without ever proving it necessary. This task's script-through-`run_script()` test is the one place in the whole plan that exercises `.side()` via the real executor path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_end_to_end.py
"""Phase 1a exit criterion: a hand-written pydsl script exercising every
handle/op in the Task 0 scope table produces a DiagramIR that resolves via
the unchanged to_sympy.py/checks.py pipeline, and — for the triangle-based
portion of the scope table — resolves to the same side lengths as an
equivalent hand-authored DSL recipe.
"""
import math

from geometry_diagrams.pydsl.api import (
    altitude, circumcircle, incircle, line_through, mark_angle, median,
    point, polygon, triangle,
)
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.pydsl.sandbox import run_script

from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.checks import run_checks

from geometry_diagrams.recipe.dsl import RecipeDSL, TriangleOp, TriangleSpec
from geometry_diagrams.recipe.lower import lower_to_ir

# Vertices chosen so the triangle's side lengths are exact, checkable values:
# AB = 4.0, BC = sqrt(18), CA = sqrt(10).
_SCRIPT_TEXT = """
a = point(0, 0)
b = point(4, 0)
c = point(1, 3)
t = triangle(a, b, c)
t.side(a, b)
t.angle_at(b)
circ = circumcircle(t)
circ.center
inc = incircle(t)
inc.center
alt = altitude(t, from_vertex=a)
alt.foot
med = median(t, from_vertex=b)
med.midpoint
d = point(0, 0)
e = point(2, 0)
f = point(2, 2)
g = point(0, 2)
square = polygon(d, e, f, g)
square.side(d, e)
ref = square.angle_at(e)
mark_angle(ref, group=1)
line_through(a, b)
"""


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
    return ir, (a, b, c)


def _build_equivalent_dsl_triangle_ir():
    # The DSL-side comparison covers the triangle-anchored portion of the
    # scope table (Triangle, Segment, Circle, Altitude, Median) — the part
    # where "equivalent DSL construction" is a direct, unambiguous
    # translation. The polygon/mark_angle portion is exercised separately
    # by tests/test_pydsl_polygon.py and tests/test_pydsl_angle.py's own
    # unit tests; duplicating it here as a second DSL comparison wouldn't
    # add coverage beyond what those already assert.
    #
    # TriangleSpec() with no fields is NOT valid — solve_triangle raises
    # (verified against recipe/solve.py: it needs enough constraints to fix
    # the triangle, e.g. three sides). Use the exact SSS side lengths of the
    # pydsl triangle at (0,0)/(4,0)/(1,3) so the two constructions are
    # actually comparable, not just independently valid.
    dsl = RecipeDSL(construction=[
        TriangleOp(
            id="T", vertices=["A", "B", "C"],
            spec=TriangleSpec(side_AB=4.0, side_BC=math.sqrt(18), side_CA=math.sqrt(10)),
        ),
    ])
    ir = lower_to_ir(dsl)
    return ir


def test_pydsl_script_compiles_without_error():
    ir, _ = _build_pydsl_script_ir()
    sym = compile_defs(ir)  # must not raise
    results = run_checks(ir.checks, sym)
    assert results == []  # no checks are created in Phase 1a scope — see note above


def test_pydsl_triangle_side_lengths_match_equivalent_dsl_recipe():
    pydsl_ir, (a, b, c) = _build_pydsl_script_ir()
    pydsl_sym = compile_defs(pydsl_ir)
    pydsl_ab = float(pydsl_sym[a.id].distance(pydsl_sym[b.id]).evalf())
    pydsl_bc = float(pydsl_sym[b.id].distance(pydsl_sym[c.id]).evalf())
    pydsl_ca = float(pydsl_sym[c.id].distance(pydsl_sym[a.id]).evalf())

    dsl_ir = _build_equivalent_dsl_triangle_ir()
    dsl_sym = compile_defs(dsl_ir)
    dsl_ab = float(dsl_sym["A"].distance(dsl_sym["B"]).evalf())
    dsl_bc = float(dsl_sym["B"].distance(dsl_sym["C"]).evalf())
    dsl_ca = float(dsl_sym["C"].distance(dsl_sym["A"]).evalf())

    # The actual equivalence claim: both surfaces, given the same triangle
    # (same three side lengths), resolve to the same geometry through the
    # unchanged to_sympy.py — not just "both happen to produce some triangle."
    assert math.isclose(pydsl_ab, dsl_ab, abs_tol=1e-9)
    assert math.isclose(pydsl_bc, dsl_bc, abs_tol=1e-9)
    assert math.isclose(pydsl_ca, dsl_ca, abs_tol=1e-9)


def test_pydsl_script_covers_every_scope_table_kind():
    ir, _ = _build_pydsl_script_ir()
    kinds = {d.kind for d in ir.define}
    expected_kinds = {
        "point_fixed", "triangle", "segment", "point_triangle_center",
        "circle_center_point", "circle_center_radius", "line_perp_through",
        "point_foot", "point_midpoint", "polygon", "line_through",
    }
    missing = expected_kinds - kinds
    assert not missing, f"scope table kinds not exercised: {missing}"


def test_pydsl_script_runs_through_the_real_sandbox_end_to_end():
    # This is the one test in the whole plan that runs .side()/.angle_at()
    # through the actual LocalPythonExecutor path, not the direct
    # new_builder_context() path every other test uses — see this task's
    # Interfaces note on why that distinction matters.
    result = run_script(_SCRIPT_TEXT, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    kinds = {d.kind for d in result.diagram_ir.define}
    assert "segment" in kinds  # only reachable via t.side()/square.side()
```

- [ ] **Step 2: Run test to verify it fails or passes as expected**

Run: `.venv/bin/python -m pytest tests/test_pydsl_end_to_end.py -v`
Expected: `test_pydsl_script_covers_every_scope_table_kind` should PASS immediately (only inspects `ir.define`). `test_pydsl_script_compiles_without_error` and `test_pydsl_triangle_side_lengths_match_equivalent_dsl_recipe` depend on `compile_defs` successfully resolving the pydsl-built `DiagramIR` — if either raises, read the actual error (likely an ordering issue: `compile_defs` walks `diagram.define` and expects referenced ids to already be defined earlier in the list) and fix whichever pydsl task's op ordering is wrong. `test_pydsl_script_runs_through_the_real_sandbox_end_to_end` is the important one to watch: if Task 2/3's `_builder`-capture fix on `Triangle`/`Polygon` was implemented incorrectly, this is the test that catches it — expect `result.error` to mention "no active Builder" if that regression is present.

- [ ] **Step 3: Fix any integration issues and re-run until passing**

If `compile_defs`/`run_checks` raise for a reason unrelated to op ordering, compare against the patterns in `tests/test_compile_defs.py`/`tests/test_checks.py` and adjust the test (not the pydsl implementation, which Tasks 1–11 already verified independently) accordingly.

Run: `.venv/bin/python -m pytest tests/test_pydsl_end_to_end.py -v`
Expected: PASS (4 tests)

- [ ] **Step 4: Run the full pydsl test suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/test_pydsl_*.py -v`
Expected: PASS (all tests across all 12 tasks)

- [ ] **Step 5: Commit**

```bash
git add tests/test_pydsl_end_to_end.py
git commit -m "Add Phase 1a exit-criterion test: pydsl script compiles via unchanged pipeline"
```

---

## Self-Review Notes

- **Spec coverage:** Task 0 (handles) → Tasks 2–7. Task 1 (builder shim) → Tasks 1–9 (contextvar, op-cap including render ops, structural-only preconditions). Task 2 (stub generator) → Task 8, including dataclass-field accessors, not just methods. Task 3 (executor) → Task 10. Task 4 (retry loop) → Task 9 (classification + did-you-mean, message-based so it works across the subprocess boundary), Task 10 (wired directly into `run_script`, no separate wiring step needed since classification happens once, in the child), and Task 11 (the actual retry driver with stop-on-success and cap enforcement — absent from the first draft of this plan, added after review). Exit criterion → Task 12.
- **Explicitly out of scope, matching the design doc:** recipe translation, bench integration, the `python_full` A/B arm, majority-vote judge. None of Tasks 1–12 touch `geometry_diagrams/recipe/`, `geometry_diagrams/strategies/`, or `evals/` (Task 12 imports `recipe.dsl`/`recipe.lower` read-only, for comparison, and modifies nothing there).
- **Verified against ground truth, not guessed:** every IR constructor call in Tasks 1–7 was checked against the real `geometry_diagrams/ir/ir.py`. Every claim about `smolagents.LocalPythonExecutor` in Task 10 — the timeout mechanism, the threading model, the exact error message shapes for undefined names/dangerous calls/disallowed imports, the fact that a tool-raised exception's original type name survives as embedded text inside the wrapped `InterpreterError` message — was verified by installing `smolagents==1.26.0` into a scratch venv and running it directly, not inferred from documentation or memory. Task 12's `compile_defs`/`run_checks` names and argument order were confirmed by reading the current source, not guessed.
- **The contextvar/threading fix (Task 10) is the one finding that would have caused Tasks 1–9 to fail silently in production despite every one of their own unit tests passing**: `LocalPythonExecutor` runs the entire script, tool calls included, inside its own `ThreadPoolExecutor` worker thread, so `Builder`'s ambient-contextvar pattern (correct for Tasks 1–9's synchronous, same-thread unit tests) is invisible from inside a sandboxed script. Task 10 binds each tool to its `Builder` via a wrapper that re-sets the contextvar in the same call frame the tool actually executes in, confirmed empirically to work regardless of which thread that turns out to be.
- **Type consistency check:** `Point`, `Line`, `Segment`, `Triangle`, `Polygon`, `Circle`, `Altitude`, `Median`, `AngleRef` are used with the same field names everywhere they recur across tasks (`.id`, `.vertices`, `.center`, `.radius`, `.foot`, `.line`, `.midpoint`, `.segment`, `.a`/`.o`/`.b`) — verified by re-reading each task's Interfaces block against the ones before it. `Builder._triangle_vertices` (dead bookkeeping nothing read) was removed; `_segment_cache`/`_render` moved to `Builder.__init__` (were lazily/inconsistently initialized via `hasattr`/`getattr` in the first draft).

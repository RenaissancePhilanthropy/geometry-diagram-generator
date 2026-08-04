# pydsl Label Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let pydsl scripts label points, segments, angles, and free-standing
text, by exposing IR label ops (`LabelPoint`/`LabelSegment`/`LabelAngle`/
`LabelFreeText`) that already exist and are already rendered — while fixing
a pre-existing sandbox bug that would otherwise break every new method the
same way it already silently breaks `Point.__add__`/`__sub__`/`__mul__`.

**Architecture:** No IR or renderer changes. `Point`, `Segment`, and
`AngleRef` gain a `_builder` field (mirroring the existing `Triangle`/
`Polygon` pattern) so their new `.label()` methods — and the pre-existing
arithmetic operators — call `self._builder._add_render(...)` directly
instead of the ambient-contextvar `get_builder()`, which is the only path
that actually works once code executes outside a `_bind_to_builder`-wrapped
top-level call inside the real sandbox. Two new top-level functions,
`segment(p, q)` and `label_text(...)`, are added to `api.py` the same way
every other constructor/render function there is.

**Tech Stack:** Python, pydantic (IR), pytest (TDD), smolagents
`LocalPythonExecutor` (the sandbox).

## Global Constraints

- No IR changes and no renderer (`to_tikz.py`/`to_svg.py`) changes — every
  label `RenderOp` kind already exists and is already rendered.
- Every handle method added here (`.label()` on `Point`/`Segment`/
  `AngleRef`) must use the handle's own captured `self._builder` reference,
  never `get_builder()` — that is the actual fix for the sandbox bug this
  plan closes, not just an added field.
- No `_builder` field gets a default value. Every construction site listed
  in Task 1 must be updated to pass it explicitly; a default would silently
  reintroduce the bug the next time a call site is missed.
- `text` is a required argument (no default, no `None` fallback) on
  `Point.label()`, `Segment.label()`, and `AngleRef.label()` — pydsl point
  ids are internal names like `__pydsl_pt_5` and must never be what a
  rendered diagram falls back to showing.
- `label_text()`'s "exactly one of `at`/`centroid_of`" check must run
  *before* `get_builder()` is called, so calling it wrong raises
  `ValueError`, never a `RuntimeError` about a missing builder.
- New functions callable from a script (`segment`, `label_text`) must be
  added to `geometry_diagrams/pydsl/__init__.py`'s `__all__` — both the stub
  generator and the sandbox's tool-injection key off that list, so skipping
  it makes a function exist in `api.py` but be uncallable from any real
  script.
- At least one test must exercise the real sandbox
  (`geometry_diagrams.pydsl.sandbox.run_script`), not only
  `new_builder_context()` — that direct-context-only blind spot is exactly
  how the pre-existing `Point.__add__` bug shipped undetected.

---

### Task 1: Fix the pre-existing sandbox `_builder` bug

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py:14-91` (`_record_literal_point`,
  `Point`, `Triangle.angle_at`, `Polygon.angle_at`)
- Modify: `geometry_diagrams/pydsl/builder.py:59-69`
  (`Builder._get_or_create_segment`)
- Modify: `geometry_diagrams/pydsl/api.py:16-224` (every function that
  constructs a `Point`, `Segment`, or uses `_record_literal_point`)
- Test: `tests/test_pydsl_point_ergonomics.py` (extend)

**Interfaces:**
- Produces: `Point`, `Segment`, and `AngleRef` all carry a `_builder` field
  (type annotated `"object"`, actual runtime type `Builder` from
  `builder.py` — same pattern as `Triangle._builder`/`Polygon._builder`
  already use, avoiding a module-load-order issue if the annotation were
  eagerly evaluated). `_record_literal_point(builder, x, y)` changes
  signature to take `builder` as its first argument instead of calling
  `get_builder()` internally.
- Consumes: nothing from a later task — this task is foundational; every
  later task's `.label()` method depends on the handle having a working
  `_builder` reference.

This task has no user-visible behavior change beyond making
`Point.__add__`/`__sub__`/`__mul__` work inside the real sandbox — it does
not add labeling yet. Confirm the bug first, so the "before" state is on
record:

- [ ] **Step 1: Reproduce the pre-existing bug as a failing test**

Add to the bottom of `tests/test_pydsl_point_ergonomics.py`:

```python
def test_point_arithmetic_works_through_the_real_sandbox():
    """Regression test: Point.__add__ previously called get_builder(), which
    only succeeds inside a _bind_to_builder-wrapped top-level call — a
    script's own top-level `a + b` statement is not one, so this raised
    RuntimeError: no active Builder in the real sandbox despite passing
    every direct-new_builder_context() test above."""
    from geometry_diagrams.pydsl.sandbox import run_script

    script = "a = point(0, 0)\nb = point(4, 0)\nc = a + b\ndraw_points(a, b, c)\n"
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_point_ergonomics.py::test_point_arithmetic_works_through_the_real_sandbox -v`
Expected: FAIL — `result.error` is
`"Code execution failed at line 'c = a + b' due to: RuntimeError: no active Builder — call inside new_builder_context()"`.

- [ ] **Step 3: Add `_builder` to `Point`, and switch its arithmetic
  operators to use it**

In `geometry_diagrams/pydsl/handles.py`, replace the `Point` class and
`_record_literal_point` (lines 14–66) with:

```python
def _record_literal_point(builder: "object", x: float, y: float) -> "Point":
    """Record a new point_fixed def for a coordinate computed via Point
    arithmetic (e.g. `center + k * (source - center)`), the same way api.py's
    point() does — kept here rather than imported from api.py to avoid a
    handles<->api circular import. Takes `builder` explicitly (the caller's
    own captured `self._builder`) rather than calling get_builder(): this
    runs from inside Point.__add__/__sub__/__mul__, which execute as a
    script's own top-level statements, not nested inside a
    _bind_to_builder-wrapped tool call — get_builder()'s ambient contextvar
    is not set at that point when running inside the real sandbox."""
    from geometry_diagrams.ir.ir import PointFixed

    pid = builder._fresh_hidden_id("pt")
    builder._add(PointFixed(id=pid, x=x, y=y))
    builder._coord_floats[pid] = (float(x), float(y))
    return Point(id=pid, _builder=builder, x=float(x), y=float(y))


@dataclass(frozen=True)
class Point:
    id: str
    _builder: "object" = field(repr=False, compare=False)  # type is Builder; avoid a
                                                             # circular import at module load
    # Known only for point(x, y) literals (and points derived from them via
    # arithmetic) — never for constructed points (point_on, rotate_point,
    # dilate_point, reflect_point, ...), whose coordinates aren't resolved
    # until later via SymPy. None here, not a wrong guess, is the honest
    # answer for those; arithmetic on them raises rather than silently
    # producing a bogus result.
    x: float | None = None
    y: float | None = None

    def _known(self, other: "Point | None" = None) -> None:
        for pt in (self, other):
            if pt is not None and (pt.x is None or pt.y is None):
                raise ValueError(
                    f"Point {pt.id!r} has no known coordinates (only point(x, y) "
                    "literals — and points derived from them via +, -, * — carry "
                    "coordinates back to the script; a point from point_on()/"
                    "rotate_point()/dilate_point()/reflect_point()/etc. does not, "
                    "since its position isn't resolved until later). Use "
                    "dilate_point()/rotate_point()/reflect_point() instead of "
                    "arithmetic when either point's coordinates aren't known."
                )

    def __add__(self, other: "Point") -> "Point":
        self._known(other)
        return _record_literal_point(self._builder, self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        self._known(other)
        return _record_literal_point(self._builder, self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Point":
        self._known()
        return _record_literal_point(self._builder, self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def label(self, text: str, pos: str = "auto", show_coords: bool = False) -> None:
        """Label this point with text, e.g. p.label("A")."""
        from geometry_diagrams.ir.ir import LabelPoint

        self._builder._add_render(
            LabelPoint(p=self.id, text=text, pos=pos, show_coords=show_coords)
        )
```

(`Point.label()` is included here, in the same edit, because it can't be
tested in isolation without `_builder` already existing on `Point` — Task 2
below only adds its test.)

- [ ] **Step 4: Add `_builder` to `Segment` and `AngleRef`**

In `geometry_diagrams/pydsl/handles.py`, change:

```python
@dataclass(frozen=True)
class Segment:
    id: str
```

to:

```python
@dataclass(frozen=True)
class Segment:
    id: str
    _builder: "object" = field(repr=False, compare=False)
```

and change:

```python
@dataclass(frozen=True)
class AngleRef:
    a: Point
    o: Point
    b: Point
```

to:

```python
@dataclass(frozen=True)
class AngleRef:
    a: Point
    o: Point
    b: Point
    _builder: "object" = field(repr=False, compare=False)
```

- [ ] **Step 5: Update `Triangle.angle_at` and `Polygon.angle_at` to pass
  `_builder` through**

Only possible now that `AngleRef` (Step 4) accepts a `_builder` argument —
doing this before Step 4 would raise `TypeError: unexpected keyword
argument '_builder'`.

In `geometry_diagrams/pydsl/handles.py`, `Triangle.angle_at` (originally
lines 93–100) becomes:

```python
    def angle_at(self, v: Point) -> "AngleRef":
        from geometry_diagrams.pydsl.handles import AngleRef  # Task 7

        vertex_ids = [vert.id for vert in self.vertices]
        if v.id not in vertex_ids:
            raise ValueError(f"{v.id!r} is not a vertex of triangle {self.id!r}")
        others = [pid for pid in vertex_ids if pid != v.id]
        return AngleRef(
            a=Point(id=others[0], _builder=self._builder),
            o=v,
            b=Point(id=others[1], _builder=self._builder),
            _builder=self._builder,
        )
```

`Polygon.angle_at` (originally lines 133–142) gets the identical change
(same shape, `self._builder` already in scope there too):

```python
    def angle_at(self, v: Point) -> "AngleRef":
        from geometry_diagrams.pydsl.handles import AngleRef  # Task 7

        ids = [vert.id for vert in self.vertices]
        if v.id not in ids:
            raise ValueError(f"{v.id!r} is not a vertex of polygon {self.id!r}")
        n = len(ids)
        i = ids.index(v.id)
        prev_id, next_id = ids[(i - 1) % n], ids[(i + 1) % n]
        return AngleRef(
            a=Point(id=prev_id, _builder=self._builder),
            o=v,
            b=Point(id=next_id, _builder=self._builder),
            _builder=self._builder,
        )
```

- [ ] **Step 6: Update `Builder._get_or_create_segment`**

In `geometry_diagrams/pydsl/builder.py`, replace lines 59–69 with:

```python
    def _get_or_create_segment(self, p_id: str, q_id: str) -> "Segment":
        from geometry_diagrams.ir.ir import Segment as SegmentDef
        from geometry_diagrams.pydsl.handles import Segment

        key = frozenset((p_id, q_id))
        if key in self._segment_cache:
            return Segment(id=self._segment_cache[key], _builder=self)
        sid = self._fresh_hidden_id("seg")
        self._add(SegmentDef(id=sid, a=p_id, b=q_id))
        self._segment_cache[key] = sid
        return Segment(id=sid, _builder=self)
```

- [ ] **Step 7: Update every `Point`/`Segment` construction in `api.py`**

In `geometry_diagrams/pydsl/api.py`:

`point()` (line 22) — change `return Point(id=pid, x=float(x), y=float(y))`
to `return Point(id=pid, _builder=builder, x=float(x), y=float(y))`.

`circumcircle()` (line 93) — change
`return Circle(id=cid, center=Point(id=center_id), _radius_thunk=_compute_radius)`
to
`return Circle(id=cid, center=Point(id=center_id, _builder=builder), _radius_thunk=_compute_radius)`.

`incircle()` (line 131) — change
`return Circle(id=cid, center=Point(id=center_id), _radius_thunk=lambda: radius)`
to
`return Circle(id=cid, center=Point(id=center_id, _builder=builder), _radius_thunk=lambda: radius)`.

`median()` (line 145) — change
`return Median(id=seg_id, midpoint=Point(id=mid_id), segment=Segment(id=seg_id))`
to
`return Median(id=seg_id, midpoint=Point(id=mid_id, _builder=builder), segment=Segment(id=seg_id, _builder=builder))`.

`altitude()` (lines 170–173) — change:
```python
    return Altitude(
        id=line_id, foot=Point(id=foot_id), line=Line(id=line_id),
        segment=Segment(id=seg_id),
    )
```
to:
```python
    return Altitude(
        id=line_id, foot=Point(id=foot_id, _builder=builder), line=Line(id=line_id),
        segment=Segment(id=seg_id, _builder=builder),
    )
```

`point_on()` (line 195) — change `return Point(id=pid)` to
`return Point(id=pid, _builder=builder)`.

`rotate_point()` (line 203) — same change: `return Point(id=pid, _builder=builder)`.

`reflect_point()` (line 211) — same change: `return Point(id=pid, _builder=builder)`.

`dilate_point()` (line 224) — same change: `return Point(id=pid, _builder=builder)`.

Every one of these functions already has `builder = get_builder()` earlier
in its body — this step only ever reuses that existing local variable, it
never obtains a builder from anywhere new.

- [ ] **Step 8: Run the full pydsl test suite**

Run: `.venv/bin/python -m pytest tests/test_pydsl_point_ergonomics.py tests/test_pydsl_end_to_end.py tests/test_pydsl_draw.py tests/test_pydsl_angle.py tests/test_pydsl_polygon.py -v`
Expected: all PASS, including the new
`test_point_arithmetic_works_through_the_real_sandbox` from Step 1.

- [ ] **Step 9: Commit**

```bash
git add geometry_diagrams/pydsl/handles.py geometry_diagrams/pydsl/builder.py geometry_diagrams/pydsl/api.py tests/test_pydsl_point_ergonomics.py
git commit -m "fix: thread _builder through Point/Segment/AngleRef, fixing sandbox arithmetic bug"
```

---

### Task 2: `Point.label()` test coverage

`Point.label()` itself already shipped in Task 1 (it couldn't be split out
without `_builder` existing first) — this task is purely its test coverage,
kept separate so it gets its own review gate.

**Files:**
- Test: `tests/test_pydsl_labels.py` (new file)

**Interfaces:**
- Consumes: `Point.label(text: str, pos: str = "auto", show_coords: bool = False) -> None` (Task 1).
- Produces: `tests/test_pydsl_labels.py`, the file every later task in this
  plan adds tests to.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pydsl_labels.py`:

```python
# tests/test_pydsl_labels.py
"""Tests for pydsl label support: Point.label(), segment()/Segment.label(),
AngleRef.label(), and label_text() — all wrapping IR RenderOp kinds
(LabelPoint/LabelSegment/LabelAngle/LabelFreeText) that already exist and
are already rendered by to_tikz.py/to_svg.py."""
import pytest

from geometry_diagrams.pydsl.api import point
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.ir.ir import LabelPoint


def test_point_label_records_label_point():
    with new_builder_context() as builder:
        p = point(1, 2)
        p.label("A")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelPoint) and r.p == p.id]
    assert len(matches) == 1
    assert matches[0].text == "A"
    assert matches[0].pos == "auto"
    assert matches[0].show_coords is False


def test_point_label_with_pos_and_show_coords():
    with new_builder_context() as builder:
        p = point(1, 2)
        p.label("A", pos="above left", show_coords=True)
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelPoint) and r.p == p.id]
    assert matches[0].pos == "above left"
    assert matches[0].show_coords is True
```

- [ ] **Step 2: Run it to verify it passes (`.label()` already exists from Task 1)**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py -v`
Expected: PASS — this step confirms Task 1's `Point.label()` addition is
correct; there's nothing left to implement here.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pydsl_labels.py
git commit -m "test: add Point.label() coverage"
```

---

### Task 3: `segment(p, q)` and `Segment.label()`

**Files:**
- Modify: `geometry_diagrams/pydsl/api.py` (add `segment()`)
- Modify: `geometry_diagrams/pydsl/handles.py` (`Segment.label()` — note: line
  numbers shifted after Task 1's edits, locate by the `class Segment:` name)
- Modify: `geometry_diagrams/pydsl/__init__.py` (register `segment`)
- Test: `tests/test_pydsl_labels.py` (extend)

**Interfaces:**
- Consumes: `Builder._get_or_create_segment(p_id, q_id)` (existing, Task 1
  gave its return value a working `_builder`); `Segment` handle (Task 1).
- Produces: `segment(p: Point, q: Point) -> Segment` in `api.py`;
  `Segment.label(text: str, pos: float | None = None) -> None` in
  `handles.py`. Both consumed by Task 6's sandbox-path test.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pydsl_labels.py`:

```python
from geometry_diagrams.pydsl.api import segment, triangle
from geometry_diagrams.ir.ir import LabelSegment


def test_segment_between_two_points_is_a_segment_def():
    from geometry_diagrams.ir.ir import Segment as SegmentDef

    with new_builder_context() as builder:
        a = point(0, 0)
        b = point(4, 0)
        s = segment(a, b)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, SegmentDef) and d.id == s.id]
    assert len(defs) == 1
    assert {defs[0].a, defs[0].b} == {a.id, b.id}


def test_segment_dedups_with_itself_regardless_of_argument_order():
    with new_builder_context():
        a = point(0, 0)
        b = point(4, 0)
        s1 = segment(a, b)
        s2 = segment(b, a)
    assert s1.id == s2.id


def test_segment_rejects_the_same_point_twice():
    with new_builder_context():
        a = point(0, 0)
        with pytest.raises(ValueError, match="two distinct points"):
            segment(a, a)


def test_segment_label_from_standalone_segment():
    with new_builder_context() as builder:
        a = point(0, 0)
        b = point(4, 0)
        s = segment(a, b)
        s.label("r")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelSegment) and r.seg == s.id]
    assert len(matches) == 1
    assert matches[0].text == "r"
    assert matches[0].pos is None


def test_segment_label_from_triangle_side():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        s = t.side(a, b)
        s.label("AB")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelSegment) and r.seg == s.id]
    assert len(matches) == 1
    assert matches[0].text == "AB"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py -v`
Expected: FAIL — `segment` doesn't exist yet (`ImportError`), and
`Segment` has no `.label()` method.

- [ ] **Step 3: Add `segment()` to `api.py`**

Add to `geometry_diagrams/pydsl/api.py`, after `polygon()`:

```python
def segment(p: Point, q: Point) -> Segment:
    """A segment between any two points (deduplicated with segments already
    obtained via Triangle.side()/Polygon.side() for the same pair)."""
    if p.id == q.id:
        raise ValueError(f"segment() needs two distinct points, got {p.id!r} twice")
    builder = get_builder()
    return builder._get_or_create_segment(p.id, q.id)
```

- [ ] **Step 4: Add `Segment.label()` to `handles.py`**

Change:

```python
@dataclass(frozen=True)
class Segment:
    id: str
    _builder: "object" = field(repr=False, compare=False)
```

to:

```python
@dataclass(frozen=True)
class Segment:
    id: str
    _builder: "object" = field(repr=False, compare=False)

    def label(self, text: str, pos: "float | None" = None) -> None:
        """Label this segment with text, e.g. seg.label("r")."""
        from geometry_diagrams.ir.ir import LabelSegment

        self._builder._add_render(LabelSegment(seg=self.id, text=text, pos=pos))
```

- [ ] **Step 5: Register `segment` in `pydsl/__init__.py`**

In `geometry_diagrams/pydsl/__init__.py`, add `segment` to the import line
(alphabetically among the other constructors — after `polygon`):

```python
from geometry_diagrams.pydsl.api import altitude, circumcircle, dilate_point, draw, draw_points, incircle, line_through, mark_angle, median, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
```

and add `"segment"` to `__all__`, after `"polygon"`:

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
    "mark_angle",
    "draw",
    "draw_points",
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

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/handles.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_labels.py
git commit -m "feat: add segment(p, q) constructor and Segment.label()"
```

---

### Task 4: `AngleRef.label()`

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py` (`AngleRef.label()`)
- Test: `tests/test_pydsl_labels.py` (extend)

**Interfaces:**
- Consumes: `AngleRef` (Task 1 gave it a working `_builder`);
  `Triangle.angle_at(v)` (existing).
- Produces: `AngleRef.label(text: str, pos: float | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pydsl_labels.py`:

```python
from geometry_diagrams.ir.ir import LabelAngle


def test_angle_ref_label_records_label_angle():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
        ref.label("θ")
        ir = builder.build()
    matches = [
        r for r in ir.render
        if isinstance(r, LabelAngle) and r.angle.o == b.id
    ]
    assert len(matches) == 1
    assert matches[0].text == "θ"
    assert {matches[0].angle.a, matches[0].angle.b} == {a.id, c.id}
    assert matches[0].pos is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py::test_angle_ref_label_records_label_angle -v`
Expected: FAIL — `AngleRef` has no `.label()` method.

- [ ] **Step 3: Add `AngleRef.label()` to `handles.py`**

Change:

```python
@dataclass(frozen=True)
class AngleRef:
    a: Point
    o: Point
    b: Point
    _builder: "object" = field(repr=False, compare=False)
```

to:

```python
@dataclass(frozen=True)
class AngleRef:
    a: Point
    o: Point
    b: Point
    _builder: "object" = field(repr=False, compare=False)

    def label(self, text: str, pos: "float | None" = None) -> None:
        """Label this angle with text, e.g. ref.label("theta")."""
        from geometry_diagrams.ir.ir import AnglePoints, LabelAngle

        self._builder._add_render(LabelAngle(
            angle=AnglePoints(a=self.a.id, o=self.o.id, b=self.b.id),
            text=text, pos=pos,
        ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/pydsl/handles.py tests/test_pydsl_labels.py
git commit -m "feat: add AngleRef.label()"
```

---

### Task 5: `label_text()`

**Files:**
- Modify: `geometry_diagrams/pydsl/api.py` (add `label_text()`)
- Modify: `geometry_diagrams/pydsl/__init__.py` (register `label_text`)
- Test: `tests/test_pydsl_labels.py` (extend)

**Interfaces:**
- Consumes: nothing from earlier tasks in this plan (independent of
  `Point`/`Segment`/`AngleRef`'s `_builder` field — `label_text()` calls
  `get_builder()` itself, since it's a top-level tool function that runs
  wrapped by `_bind_to_builder` in the sandbox, same as `point()`/`draw()`).
- Produces: `label_text(text: str, at: tuple[float, float] | None = None, centroid_of: Triangle | Polygon | None = None) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pydsl_labels.py`:

```python
from geometry_diagrams.pydsl.api import label_text
from geometry_diagrams.ir.ir import LabelFreeText


def test_label_text_at_explicit_coordinates():
    with new_builder_context() as builder:
        label_text("h", at=(1.0, 2.0))
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(matches) == 1
    assert matches[0].text == "h"
    assert matches[0].at == [1.0, 2.0]
    assert matches[0].centroid_of is None


def test_label_text_at_triangle_centroid():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        label_text("T", centroid_of=t)
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(matches) == 1
    assert matches[0].text == "T"
    assert matches[0].at is None
    assert matches[0].centroid_of == t.id


def test_label_text_requires_exactly_one_of_at_or_centroid_of():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        with pytest.raises(ValueError, match="exactly one"):
            label_text("h", at=(0, 0), centroid_of=t)


def test_label_text_neither_at_nor_centroid_of_raises_without_a_builder():
    # No new_builder_context() at all — proves the exactly-one-of check
    # runs before get_builder(), so this is ValueError, not RuntimeError.
    with pytest.raises(ValueError, match="exactly one"):
        label_text("h")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py -v`
Expected: FAIL — `label_text` doesn't exist yet (`ImportError`).

- [ ] **Step 3: Add `label_text()` to `api.py`**

Add to `geometry_diagrams/pydsl/api.py`, after `draw_points()`:

```python
def label_text(
    text: str,
    at: "tuple[float, float] | None" = None,
    centroid_of: "Triangle | Polygon | None" = None,
) -> None:
    """Place free-standing text at explicit (x, y) coordinates, or at the
    centroid of a triangle/polygon. Exactly one of `at`/`centroid_of` must
    be given."""
    from geometry_diagrams.ir.ir import LabelFreeText

    has_at = at is not None
    has_centroid = centroid_of is not None
    if has_at == has_centroid:
        raise ValueError("label_text() requires exactly one of 'at' or 'centroid_of'")
    builder = get_builder()
    builder._add_render(LabelFreeText(
        text=text,
        at=[float(at[0]), float(at[1])] if has_at else None,
        centroid_of=centroid_of.id if has_centroid else None,
    ))
```

- [ ] **Step 4: Register `label_text` in `pydsl/__init__.py`**

Add `label_text` to the import line (after `incircle`, before
`line_through`, keeping the existing alphabetical-ish grouping):

```python
from geometry_diagrams.pydsl.api import altitude, circumcircle, dilate_point, draw, draw_points, incircle, label_text, line_through, mark_angle, median, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
```

and add `"label_text"` to `__all__`, after `"draw_points"`:

```python
    "draw",
    "draw_points",
    "label_text",
    "point_on",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_labels.py
git commit -m "feat: add label_text()"
```

---

### Task 6: Sandbox integration test, SVG end-to-end test, and instructions doc

**Files:**
- Test: `tests/test_pydsl_labels.py` (extend — sandbox-path test)
- Test: `tests/test_pydsl_end_to_end.py` (extend — SVG render assertion)
- Modify: `geometry_diagrams/strategies/instructions_python_full.py:24-45`

**Interfaces:**
- Consumes: every function/method from Tasks 1–5 (`Point.label()`,
  `segment()`, `Segment.label()`, `AngleRef.label()`, `label_text()`).
- Produces: nothing new for later tasks — this is the plan's final,
  wrap-up task.

This is the task that satisfies the spec's "Sandbox-path coverage" testing
requirement: proving `.label()` and `segment()` work together through the
*real* sandboxed execution path, not just direct `new_builder_context()`
calls — the same category of test that would have caught the Task 1 bug
before it shipped.

- [ ] **Step 1: Write the failing sandbox-path test**

Append to `tests/test_pydsl_labels.py`:

```python
def test_labels_and_segment_work_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script
    from geometry_diagrams.ir.ir import LabelPoint, LabelSegment

    script = (
        "a = point(0, 0)\n"
        "b = point(4, 0)\n"
        "a.label('A')\n"
        "s = segment(a, b)\n"
        "s.label('r')\n"
        "draw(s)\n"
        "draw_points(a, b)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    point_labels = [r for r in result.diagram_ir.render if isinstance(r, LabelPoint)]
    seg_labels = [r for r in result.diagram_ir.render if isinstance(r, LabelSegment)]
    assert any(r.text == "A" for r in point_labels)
    assert any(r.text == "r" for r in seg_labels)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py::test_labels_and_segment_work_through_the_real_sandbox -v`
Expected: PASS already, since Tasks 1–5 are complete by this point in the
plan — this step is a direct confirmation, not a red-then-green cycle
(there is no remaining implementation gap for it to expose). If it fails,
stop and treat it as a signal that an earlier task's fix is incomplete —
do not patch around it in this task.

- [ ] **Step 3: Write and run the SVG end-to-end test**

Append to `tests/test_pydsl_end_to_end.py`:

```python
def test_pydsl_labels_render_as_svg_text():
    from geometry_diagrams.pydsl.api import draw, draw_points, label_text, segment
    from geometry_diagrams.ir.renderer import SVGRenderer

    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        a.label("A")
        s = segment(a, b)
        s.label("r")
        label_text("T", centroid_of=t)
        draw(t)
        draw(s)
        draw_points(a, b, c)
        ir = builder.build()

    sym = compile_defs(ir)
    result = SVGRenderer().render(ir, sym)
    svg = result.output
    for expected_text in ("A", "r", "T"):
        assert expected_text in svg, f"expected label {expected_text!r} not found in rendered SVG"
```

`SVGRenderer.render(diagram, sym, warnings=None)` returns a
`RenderResult(output=svg, format="svg", intermediate="")` (see
`geometry_diagrams/ir/renderer.py:61-75`) — the SVG string is
`result.output`, not the return value itself. The assertion checks for the
label text appearing anywhere in the output rather than the exact
`>text<` substring, since `to_svg.py`'s label placement may wrap text in a
`<tspan>` or add attributes between the tag and the text content.

Run: `.venv/bin/python -m pytest tests/test_pydsl_end_to_end.py::test_pydsl_labels_render_as_svg_text -v`
Expected: PASS.

- [ ] **Step 4: Add the labeling example to the Rules section**

In `geometry_diagrams/strategies/instructions_python_full.py`, in the
`## Rules` section (currently lines 26–44), add one bullet after the
`mark_angle` bullet:

```python
- Use `segment(p, q)` to get a segment between any two points that aren't
  already a Triangle/Polygon side (e.g. a circle's radius from its center to
  a point on its edge). Call `.label(text)` on a Point, Segment, or AngleRef
  to name it or mark a length/angle — e.g. `p.label("A")`,
  `segment(center, edge).label("r")`, `t.angle_at(b).label("θ")`. Use
  `label_text(text, at=(x, y))` or `label_text(text, centroid_of=shape)` for
  free-standing text not tied to one specific object.
```

- [ ] **Step 5: Run the full pydsl + strategy test suite**

Run: `.venv/bin/python -m pytest tests/test_pydsl_labels.py tests/test_pydsl_end_to_end.py tests/test_python_full_strategy.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_pydsl_labels.py tests/test_pydsl_end_to_end.py geometry_diagrams/strategies/instructions_python_full.py
git commit -m "test: add sandbox and SVG end-to-end label coverage; document labeling in prompt"
```

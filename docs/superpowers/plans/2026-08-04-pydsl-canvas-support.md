# pydsl Canvas/Grid Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let pydsl scripts request a canvas with explicit bounds and an
optional grid/axes, closing the gap where models currently hand-fake a grid
using the same stroke as real geometry, with no way to tell them apart.

**Architecture:** One new top-level function, `canvas(...)`, in `api.py`,
mirroring `ir.Canvas` almost field-for-field. It stores the resulting
`ir.Canvas` on a new `Builder._canvas` field; `Builder.build()` passes that
through instead of its current hardcoded `canvas=None`. No IR or renderer
changes — every field this plan exposes is already defined in `ir.Canvas`
and already rendered, with grid lines already styled distinctly
(`stroke="#ccc"`, thin) from ordinary drawn geometry, by both `to_svg.py`
and `to_tikz.py`.

**Tech Stack:** Python, pydantic (IR), pytest (TDD).

## Global Constraints

- No IR or renderer changes — every field `canvas()` sets already exists on
  `ir.Canvas` and is already rendered by both `to_tikz.py` and `to_svg.py`.
- `x_range`/`y_range` have no defaults — bounds must be explicit. Both
  tuples and lists must work (the function only unpacks/indexes; no
  tuple-specific behavior).
- `grid_step`/`tick_step` default to `None`, auto-computed via `_nice_step`
  (a "nice number" — 1, 2, or 5 times a power of 10 — targeting roughly 10
  lines across the larger of the x/y span) when not given. This is the
  actual fix for grid density, not merely a guard: a fixed literal default
  of `1.0` would force a hard reject on any sufficiently large canvas that
  didn't override it.
- Calling `canvas()` a second time in the same script raises `ValueError`
  immediately, naming the conflict — this is a deliberate divergence from
  the recipe DSL's own `CanvasOp`, which silently lets the last call win.
- Four validation checks, each raising `ValueError` immediately: inverted
  or degenerate bounds (`x_range[0] >= x_range[1]`, same for `y_range`);
  non-positive *explicit* `grid_step`/`tick_step` (the auto-computed default
  is never checked against this, since `_nice_step` cannot produce a
  non-positive value); and a line-count backstop (`_MAX_GRID_LINES = 500`)
  that only fires when an *explicit* `grid_step`/`tick_step` would produce
  an excessive number of lines — the auto-computed default (~10-20 lines
  total) never comes close to it.
- `canvas` must be added to `geometry_diagrams/pydsl/__init__.py`'s import
  line and `__all__` — both the stub generator and the sandbox's
  tool-injection key off `__all__`; skipping this makes the function exist
  in `api.py` but be uncallable from any real script. `_nice_step`,
  `_TARGET_LINES`, and `_MAX_GRID_LINES` are private and must NOT be added
  to `__all__`.
- At least one test must exercise the real sandbox
  (`geometry_diagrams.pydsl.sandbox.run_script`), not only
  `new_builder_context()` directly — including a sandbox-path double-call
  case, since that's the case that actually pins down what error a model
  sees when it makes this mistake for real.

---

### Task 1: `canvas()`, `_nice_step()`, and `Builder` wiring

**Files:**
- Modify: `geometry_diagrams/pydsl/builder.py:24-30,56-57` (`Builder.__init__`,
  `Builder.build`)
- Modify: `geometry_diagrams/pydsl/api.py` (add `_nice_step`, `canvas`)
- Modify: `geometry_diagrams/pydsl/__init__.py` (register `canvas`)
- Test: `tests/test_pydsl_canvas.py` (new file)

**Interfaces:**
- Consumes: `Builder._add`/`Builder._add_render` are NOT used here —
  `canvas()` writes directly to a new `Builder._canvas` field, since a
  canvas is neither a `DefStmt` nor a `RenderOp`, it's `DiagramIR.canvas`
  itself.
- Produces: `Builder._canvas: "ir.Canvas | None"` (new field, default
  `None`); `canvas(x_range, y_range, grid=False, grid_step=None,
  axes=False, tick_step=None, show_ticks=False, show_tick_labels=False,
  show_axis_labels=False) -> None` in `api.py`; `_nice_step(span: float,
  target_lines: float = 10) -> float` in `api.py` (private, used only by
  `canvas()`, but tested directly as a unit). Task 2 consumes `canvas()`
  and the sandbox/`__all__` wiring this task sets up.

- [ ] **Step 1: Write the failing unit tests for `_nice_step`**

Create `tests/test_pydsl_canvas.py`:

```python
# tests/test_pydsl_canvas.py
"""Tests for pydsl canvas/grid support: canvas() records an ir.Canvas onto
Builder._canvas, and Builder.build() passes it through to DiagramIR.canvas
(replacing the previous hardcoded canvas=None). _nice_step() is the
auto-computed grid/tick spacing heuristic canvas() uses when grid_step/
tick_step aren't given explicitly."""
import pytest

from geometry_diagrams.pydsl.api import _nice_step, canvas, point
from geometry_diagrams.pydsl.builder import new_builder_context


def test_nice_step_small_span():
    assert _nice_step(8) == 1.0


def test_nice_step_medium_span():
    assert _nice_step(500) == 50.0


def test_nice_step_large_span():
    assert _nice_step(1000) == 100.0


def test_nice_step_zero_or_negative_span_returns_one():
    assert _nice_step(0) == 1.0
    assert _nice_step(-5) == 1.0


def test_nice_step_residual_thresholds():
    # raw = span / 10. residual = raw / magnitude, magnitude = 10**floor(log10(raw)).
    # residual < 1.5 -> nice=1; < 3 -> nice=2; < 7 -> nice=5; else -> nice=10.
    assert _nice_step(10) == 1.0    # raw=1.0, magnitude=1, residual=1.0  (<1.5 -> 1)
    assert _nice_step(20) == 2.0    # raw=2.0, magnitude=1, residual=2.0  (<3 -> 2)
    assert _nice_step(40) == 5.0    # raw=4.0, magnitude=1, residual=4.0  (<7 -> 5)
    assert _nice_step(80) == 10.0   # raw=8.0, magnitude=1, residual=8.0  (>=7 -> 10)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_canvas.py -v`
Expected: FAIL — `ImportError: cannot import name '_nice_step'` (and
`canvas`, `point` will import fine since `point` already exists).

- [ ] **Step 3: Implement `_nice_step` in `api.py`**

Add near the top of `geometry_diagrams/pydsl/api.py`, after the existing
imports (the file already has `import math` at line 6 — no new import
needed):

```python
_TARGET_LINES = 10        # nice-step heuristic aims for roughly this many grid/tick lines
_MAX_GRID_LINES = 500     # backstop for an explicit override, not the common path


def _nice_step(span: float, target_lines: float = _TARGET_LINES) -> float:
    """Round span/target_lines up to a 'nice' number: 1, 2, or 5 times a power
    of 10 — the same heuristic chart libraries use for axis tick spacing.
    E.g. span=8 -> 1.0; span=500 -> 50.0; span=1000 -> 100.0."""
    if span <= 0:
        return 1.0
    raw = span / target_lines
    magnitude = 10 ** math.floor(math.log10(raw))
    residual = raw / magnitude
    if residual < 1.5:
        nice = 1
    elif residual < 3:
        nice = 2
    elif residual < 7:
        nice = 5
    else:
        nice = 10
    return nice * magnitude
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_canvas.py -v`
Expected: the 5 `_nice_step` tests PASS; remaining tests (not yet written)
don't exist yet, so this file has only these 5 collected so far.

- [ ] **Step 5: Write the failing tests for all of `canvas()`'s behavior —
  recording, overrides, and every validation path**

`canvas()` is one small, cohesively-designed function where the validation
branches aren't meaningfully separable sub-features — write every test
against it now, before any of `canvas()` exists, rather than writing a
first batch, implementing, and then adding more tests against code that
already satisfies them (which wouldn't be TDD for those later tests).

Append to `tests/test_pydsl_canvas.py`:

```python
def test_canvas_records_ir_canvas_with_auto_computed_step():
    with new_builder_context() as builder:
        canvas(x_range=(0, 8), y_range=(0, 6), grid=True)
        ir = builder.build()
    assert ir.canvas is not None
    assert ir.canvas.xmin == 0
    assert ir.canvas.xmax == 8
    assert ir.canvas.ymin == 0
    assert ir.canvas.ymax == 6
    assert ir.canvas.grid is True
    assert ir.canvas.grid_step == 1.0   # auto-computed: max(8, 6) -> _nice_step(8) == 1.0
    assert ir.canvas.axes is False
    assert ir.canvas.tick_step == 1.0   # also auto-computed, independently
    assert ir.canvas.show_ticks is False
    assert ir.canvas.show_tick_labels is False
    assert ir.canvas.show_axis_labels is False
    assert ir.canvas.clip is True       # untouched, ir.Canvas's own default


def test_canvas_grid_step_auto_computes_from_larger_span():
    with new_builder_context() as builder:
        canvas(x_range=(0, 500), y_range=(0, 10), grid=True)
        ir = builder.build()
    assert ir.canvas.grid_step == 50.0  # driven by the larger span (500), not the smaller (10)


def test_canvas_explicit_grid_step_and_tick_step_override_auto_compute():
    with new_builder_context() as builder:
        canvas(x_range=(0, 8), y_range=(0, 6), grid=True, grid_step=2.0,
               axes=True, tick_step=0.5, show_ticks=True,
               show_tick_labels=True, show_axis_labels=True)
        ir = builder.build()
    assert ir.canvas.grid_step == 2.0
    assert ir.canvas.tick_step == 0.5
    assert ir.canvas.axes is True
    assert ir.canvas.show_ticks is True
    assert ir.canvas.show_tick_labels is True
    assert ir.canvas.show_axis_labels is True


def test_canvas_accepts_lists_not_just_tuples():
    with new_builder_context() as builder:
        canvas(x_range=[0, 8], y_range=[0, 6])
        ir = builder.build()
    assert ir.canvas.xmin == 0
    assert ir.canvas.xmax == 8


def test_builder_without_canvas_call_still_has_none_canvas():
    with new_builder_context() as builder:
        point(1, 2)
        ir = builder.build()
    assert ir.canvas is None


def test_canvas_called_twice_raises():
    with new_builder_context():
        canvas(x_range=(0, 8), y_range=(0, 6))
        with pytest.raises(ValueError, match="already called once"):
            canvas(x_range=(0, 4), y_range=(0, 4))


def test_canvas_inverted_x_range_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="x_range"):
            canvas(x_range=(8, 0), y_range=(0, 6))


def test_canvas_degenerate_x_range_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="x_range"):
            canvas(x_range=(4, 4), y_range=(0, 6))


def test_canvas_inverted_y_range_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="y_range"):
            canvas(x_range=(0, 8), y_range=(6, 0))


@pytest.mark.parametrize("bad_step", [0, -1])
def test_canvas_non_positive_grid_step_raises(bad_step):
    with new_builder_context():
        with pytest.raises(ValueError, match="grid_step"):
            canvas(x_range=(0, 8), y_range=(0, 6), grid_step=bad_step)


@pytest.mark.parametrize("bad_step", [0, -1])
def test_canvas_non_positive_tick_step_raises(bad_step):
    with new_builder_context():
        with pytest.raises(ValueError, match="tick_step"):
            canvas(x_range=(0, 8), y_range=(0, 6), tick_step=bad_step)


def test_canvas_excessive_grid_density_from_explicit_step_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="grid lines"):
            canvas(x_range=(0, 8), y_range=(0, 6), grid=True, grid_step=0.001)


def test_canvas_excessive_tick_density_from_explicit_step_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="ticks"):
            canvas(x_range=(0, 8), y_range=(0, 6), show_ticks=True, tick_step=0.001)


def test_canvas_large_span_with_auto_computed_step_does_not_raise():
    # Confirms the density backstop only fires on a bad EXPLICIT override,
    # never on the auto-computed default — a large canvas with grid=True
    # and no grid_step given must succeed.
    with new_builder_context() as builder:
        canvas(x_range=(0, 10000), y_range=(0, 10000), grid=True)
        ir = builder.build()
    assert ir.canvas.grid_step == 1000.0
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_canvas.py -v`
Expected: FAIL — `ImportError: cannot import name 'canvas'` (every test in
this batch imports/calls `canvas`, which doesn't exist yet). The one
exception is `test_builder_without_canvas_call_still_has_none_canvas`,
which passes already since `Builder.build()` already hardcodes
`canvas=None` — that's fine, it's a regression guard for behavior that
must stay true after this task's changes, not new behavior to build.

- [ ] **Step 7: Add `Builder._canvas` and update `Builder.build()`**

In `geometry_diagrams/pydsl/builder.py`, change `Builder.__init__` (lines
24-30) from:

```python
    def __init__(self, op_cap: int = DEFAULT_OP_CAP) -> None:
        self._defs: list[DefStmt] = []
        self._render: list = []
        self._coord_floats: dict[str, tuple[float, float]] = {}
        self._segment_cache: dict[frozenset, str] = {}
        self._op_cap = op_cap
        self._hidden_id_counter = 0
```

to:

```python
    def __init__(self, op_cap: int = DEFAULT_OP_CAP) -> None:
        self._defs: list[DefStmt] = []
        self._render: list = []
        self._coord_floats: dict[str, tuple[float, float]] = {}
        self._segment_cache: dict[frozenset, str] = {}
        self._op_cap = op_cap
        self._hidden_id_counter = 0
        self._canvas = None  # set at most once, by canvas(); type is ir.Canvas | None
```

and change `Builder.build()` (lines 56-57) from:

```python
    def build(self) -> DiagramIR:
        return DiagramIR(define=list(self._defs), render=list(self._render), canvas=None)
```

to:

```python
    def build(self) -> DiagramIR:
        return DiagramIR(define=list(self._defs), render=list(self._render), canvas=self._canvas)
```

- [ ] **Step 8: Implement `canvas()` in `api.py`**

Add to `geometry_diagrams/pydsl/api.py`, after `label_text()` (the last
function in the file):

```python
def canvas(
    x_range: "tuple[float, float] | list[float]",
    y_range: "tuple[float, float] | list[float]",
    grid: bool = False,
    grid_step: "float | None" = None,
    axes: bool = False,
    tick_step: "float | None" = None,
    show_ticks: bool = False,
    show_tick_labels: bool = False,
    show_axis_labels: bool = False,
) -> None:
    """Set canvas bounds and optional grid/axes styling for the diagram.
    Call at most once per script. grid_step/tick_step default to an
    automatically chosen 'nice' number (1, 2, 5, 10, ...) based on the
    canvas size if not given. Note: if axes=True, the displayed bounds
    expand to include the origin even if x_range/y_range don't."""
    from geometry_diagrams.ir.ir import Canvas as CanvasDef

    builder = get_builder()
    if builder._canvas is not None:
        raise ValueError(
            "canvas() was already called once in this script — only one call is allowed"
        )
    xmin, xmax = x_range
    ymin, ymax = y_range
    if xmin >= xmax:
        raise ValueError(f"canvas(): x_range must satisfy x_range[0] < x_range[1], got {list(x_range)!r}")
    if ymin >= ymax:
        raise ValueError(f"canvas(): y_range must satisfy y_range[0] < y_range[1], got {list(y_range)!r}")
    if grid_step is not None and grid_step <= 0:
        raise ValueError(f"canvas(): grid_step must be > 0, got {grid_step!r}")
    if tick_step is not None and tick_step <= 0:
        raise ValueError(f"canvas(): tick_step must be > 0, got {tick_step!r}")

    span = max(xmax - xmin, ymax - ymin)
    effective_grid_step = grid_step if grid_step is not None else _nice_step(span)
    effective_tick_step = tick_step if tick_step is not None else _nice_step(span)

    if grid:
        n_grid_lines = (xmax - xmin) / effective_grid_step + (ymax - ymin) / effective_grid_step
        if n_grid_lines > _MAX_GRID_LINES:
            raise ValueError(
                f"canvas(): grid_step={effective_grid_step!r} over this range would draw "
                f"~{int(n_grid_lines)} grid lines (limit {_MAX_GRID_LINES}) — use a larger grid_step"
            )
    if show_ticks or show_tick_labels:
        n_tick_lines = (xmax - xmin) / effective_tick_step + (ymax - ymin) / effective_tick_step
        if n_tick_lines > _MAX_GRID_LINES:
            raise ValueError(
                f"canvas(): tick_step={effective_tick_step!r} over this range would draw "
                f"~{int(n_tick_lines)} ticks (limit {_MAX_GRID_LINES}) — use a larger tick_step"
            )
    builder._canvas = CanvasDef(
        xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax,
        grid=grid, grid_step=effective_grid_step,
        axes=axes, tick_step=effective_tick_step,
        show_ticks=show_ticks, show_tick_labels=show_tick_labels,
        show_axis_labels=show_axis_labels,
    )
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_canvas.py -v`
Expected: all tests PASS (19 total: 5 `_nice_step` unit tests + 14 `canvas()`
tests covering recording, overrides, lists, the no-call regression guard,
and every validation path).

- [ ] **Step 10: Register `canvas` in `pydsl/__init__.py`**

In `geometry_diagrams/pydsl/__init__.py`, change the import line from:

```python
from geometry_diagrams.pydsl.api import altitude, circumcircle, dilate_point, draw, draw_points, incircle, label_text, line_through, mark_angle, median, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
```

to (adding `canvas` in alphabetical position, after `altitude`):

```python
from geometry_diagrams.pydsl.api import altitude, canvas, circumcircle, dilate_point, draw, draw_points, incircle, label_text, line_through, mark_angle, median, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
```

and add `"canvas"` to `__all__`, after `"altitude"`:

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

- [ ] **Step 11: Run the pydsl test suite to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/test_pydsl_canvas.py tests/test_pydsl_labels.py tests/test_pydsl_end_to_end.py tests/test_pydsl_point_ergonomics.py tests/test_pydsl_draw.py -v`
Expected: all PASS.

- [ ] **Step 12: Commit**

```bash
git add geometry_diagrams/pydsl/builder.py geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_canvas.py
git commit -m "feat: add canvas() with auto-computed grid/tick step"
```

---

### Task 2: Sandbox integration test, SVG grid-styling test, and instructions doc

**Files:**
- Test: `tests/test_pydsl_canvas.py` (extend — sandbox-path tests)
- Test: `tests/test_pydsl_end_to_end.py` (extend — SVG grid-styling assertion)
- Modify: `geometry_diagrams/strategies/instructions_python_full.py:24-52`

**Interfaces:**
- Consumes: `canvas()` (Task 1), already registered in `pydsl.__all__`.
- Produces: nothing new for later tasks — this is the plan's final,
  wrap-up task.

- [ ] **Step 1: Write the failing sandbox-path tests**

Append to `tests/test_pydsl_canvas.py`:

```python
def test_canvas_works_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = (
        "canvas(x_range=(0, 8), y_range=(0, 6), grid=True)\n"
        "a = point(1, 2)\n"
        "b = point(7, 6)\n"
        "draw_points(a, b)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    assert result.diagram_ir.canvas is not None
    assert result.diagram_ir.canvas.grid is True
    assert result.diagram_ir.canvas.xmin == 0
    assert result.diagram_ir.canvas.xmax == 8


def test_canvas_double_call_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = (
        "canvas(x_range=(0, 8), y_range=(0, 6))\n"
        "canvas(x_range=(0, 4), y_range=(0, 4))\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is not None
    assert "already called once" in result.error
    assert result.diagram_ir is None
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_canvas.py::test_canvas_works_through_the_real_sandbox tests/test_pydsl_canvas.py::test_canvas_double_call_through_the_real_sandbox -v`
Expected: PASS already, since Task 1's implementation is complete and
`canvas` is registered in `__all__` — this step is a direct confirmation
that the real sandbox path works, not a red-then-green cycle. If either
fails, treat it as a signal that Task 1's `__all__` registration or
`canvas()` implementation is incomplete — do not patch around it here.

- [ ] **Step 3: Write and run the SVG grid-styling end-to-end test**

Append to `tests/test_pydsl_end_to_end.py`:

```python
def test_pydsl_canvas_grid_renders_with_distinct_styling():
    from geometry_diagrams.pydsl.api import canvas, draw, triangle
    from geometry_diagrams.ir.renderer import SVGRenderer

    with new_builder_context() as builder:
        canvas(x_range=(0, 8), y_range=(0, 6), grid=True)
        a, b, c = point(0, 0), point(4, 0), point(2, 3)
        draw(triangle(a, b, c))
        ir = builder.build()

    sym = compile_defs(ir)
    result = SVGRenderer().render(ir, sym)
    svg = result.output
    assert 'stroke="#ccc"' in svg, "expected grid lines with distinct light-gray styling"
```

Run: `.venv/bin/python -m pytest tests/test_pydsl_end_to_end.py::test_pydsl_canvas_grid_renders_with_distinct_styling -v`
Expected: PASS. (`compile_defs`, `new_builder_context`, and `point`/
`triangle` are already imported at the top of this file from earlier
tasks — no new imports needed beyond the `canvas`/`draw`/`SVGRenderer`
ones shown inside the test.)

- [ ] **Step 4: Add the canvas bullet to the Rules section**

In `geometry_diagrams/strategies/instructions_python_full.py`, in the
`## Rules` section, add one bullet immediately after the existing
`segment`/`.label()` bullet (the one starting `- Use \`segment(p, q)\`
to get a segment...`):

```python
- Call `canvas(x_range=(xmin, xmax), y_range=(ymin, ymax), grid=True)` if the
  request needs a coordinate grid or axes — do NOT hand-draw a grid out of
  individual `segment()`/`line_through()` calls, since those would render in
  the same stroke as your actual geometry and be indistinguishable from it.
  `grid_step`/`tick_step` are optional and auto-sized to the canvas if
  omitted. Note: with `axes=True`, the displayed bounds expand to include
  the origin even if `x_range`/`y_range` don't.
```

- [ ] **Step 5: Run the full pydsl + strategy test suite**

Run: `.venv/bin/python -m pytest tests/test_pydsl_canvas.py tests/test_pydsl_end_to_end.py tests/test_pydsl_labels.py tests/test_python_full_strategy.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_pydsl_canvas.py tests/test_pydsl_end_to_end.py geometry_diagrams/strategies/instructions_python_full.py
git commit -m "test: add sandbox and SVG grid-styling coverage for canvas(); document in prompt"
```

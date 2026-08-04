# python_full Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `PythonFullStrategy`, a new geometry-diagram strategy where an LLM writes a pydsl Python script (instead of `DiagramIR` JSON) that runs through the existing sandbox to produce a diagram, retried via a `StateGraph` on failure — structurally equivalent to `StructureStrategy`.

**Architecture:** One LLM call (`with_structured_output(PydslScriptOutput)`) produces a script string; `sandbox.run_script()` executes it in the existing subprocess sandbox to get a `DiagramIR`; the same deterministic pipeline `structured.py` already uses (`compile_defs` → `resolve_angle_pairs` → `run_checks` → render) — extracted into a shared `ir_pipeline.py` — compiles and renders it. A `StateGraph` retries the whole thing (`MAX_RETRIES = 3`) on any of: script-generation failure, sandbox failure, a "nothing was drawn" guard, or pipeline failure.

**Tech Stack:** Python 3.11, LangGraph `StateGraph`, LangChain `with_structured_output`, Pydantic 2.x, the existing `geometry_diagrams/pydsl/` sandbox (Phase 1a, already complete and committed on this branch).

## Global Constraints

- `MAX_RETRIES = 3`, matching `structured.py`/`recipe.py`'s existing convention exactly.
- Drawing is **mandatory and explicit** via new `draw()`/`draw_points()` pydsl ops — no auto-draw fallback in this PoC (a script that builds geometry but never calls `draw()`/`draw_points()` must fail with a retryable error, not silently render blank).
- Not registered in `evals/run.py`'s `_STRATEGY_MAP` — this stays a standalone strategy for this PoC.
- The retry loop is a `StateGraph` (`generate_script` node → `run_script` node → conditional retry edge), not a reuse of `geometry_diagrams/pydsl/retry_loop.py`'s `run_with_retries` (that driver's own tests assume a synchronous, non-LLM `make_script` and must not be repurposed here).
- `structured.py`'s `_run_ir_pipeline`/`StructuredRunResult` move to a new shared `geometry_diagrams/strategies/ir_pipeline.py` as `run_ir_pipeline`/`StructuredRunResult`. **Both** `structured.py` and `recipe.py` must keep re-exporting the pipeline function under the exact old private name (`_run_ir_pipeline`) in their own module namespace — `tests/test_structured_strategy.py` and `tests/test_recipe_strategy.py`/`test_recipe_retry.py` patch `geometry_diagrams.strategies.structured._run_ir_pipeline` / `geometry_diagrams.strategies.recipe._run_ir_pipeline` directly by that module-qualified name, and updating call sites to a new public name instead of re-exporting would silently break those patches.
- `last_error` must never be empty on a sandbox failure: use `result.retry_message or result.error` (sandbox.py's `ExecutionTimeoutError` branch always sets `retry_message=None`).
- A script-generation failure and a sandbox/pipeline failure must each cost exactly **one** retry attempt — never double-counted (the same invariant `structured.py`'s `test_ir_gen_failure_costs_one_attempt` guards; `_run_script_node` must not increment `attempt` again when `state["script"] is None`, since `_generate_script_node` already did).

---

## File Structure

```
geometry_diagrams/pydsl/
    builder.py            # MODIFY: Builder.build() emits canvas=None, not Canvas()
    handles.py             # MODIFY: Altitude gains a `segment: Segment` field
    api.py                  # MODIFY: add draw(), draw_points()
    __init__.py              # MODIFY: export draw, draw_points

geometry_diagrams/strategies/
    ir_pipeline.py            # NEW: run_ir_pipeline(), StructuredRunResult (moved from structured.py)
    structured.py              # MODIFY: import + re-export from ir_pipeline.py instead of defining locally
    recipe.py                   # MODIFY: import StructuredRunResult/_run_ir_pipeline from ir_pipeline.py directly
    instructions_python_full.py  # NEW: build_python_full_instructions()
    python_full.py                # NEW: PydslScriptOutput, PythonFullPipelineState, the StateGraph, PythonFullStrategy

tests/
    test_pydsl_builder.py           # MODIFY: add canvas=None regression test
    test_pydsl_altitude.py           # MODIFY: add Altitude.segment test
    test_pydsl_draw.py                # NEW: draw()/draw_points() unit tests
    test_instructions_python_full.py   # NEW: prompt-assembly test
    test_python_full_strategy.py        # NEW: strategy-level tests, LLM mocked, real sandbox/pipeline
```

---

### Task 1: Fix `Builder.build()`'s hardcoded canvas

**Files:**
- Modify: `geometry_diagrams/pydsl/builder.py`
- Test: `tests/test_pydsl_builder.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Builder.build()` now emits `canvas=None` on the returned `DiagramIR` instead of a hardcoded `Canvas()` (fixed −5..5 bounds). Both `to_svg.py` (`ir_to_svg`, canvas-is-None branch) and `to_tikz.py` already auto-size bounds from resolved geometry when `diagram.canvas is None` — this is an existing, exercised code path, not new behavior being added to either renderer.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_pydsl_builder.py
def test_build_emits_none_canvas_so_renderers_auto_size():
    """Builder.build() must not hardcode a fixed canvas — a small construction
    would render tiny and zoomed-out inside an unnecessarily large fixed
    -5..5 canvas, since both renderers only ever expand those bounds outward,
    never shrink them. canvas=None lets each renderer auto-size from the
    actual resolved geometry instead (both already support this)."""
    from geometry_diagrams.ir.ir import PointFixed

    with new_builder_context() as builder:
        builder._add(PointFixed(id="p1", x=0, y=0))
        ir = builder.build()
    assert ir.canvas is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_builder.py::test_build_emits_none_canvas_so_renderers_auto_size -v`
Expected: FAIL — `assert Canvas(...) is None`

- [ ] **Step 3: Fix `Builder.build()`**

```python
# geometry_diagrams/pydsl/builder.py — change the import line:
from geometry_diagrams.ir.ir import DefBase, DefStmt, DiagramIR
# (drop the now-unused `Canvas` import)

# change build():
    def build(self) -> DiagramIR:
        return DiagramIR(define=list(self._defs), render=list(self._render), canvas=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_builder.py -v`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Run the full pydsl test suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -k pydsl -q`
Expected: all pass (this changes shared behavior every existing pydsl test's `DiagramIR` output depends on downstream, but no existing test asserts a specific `canvas` value, so none should break)

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/pydsl/builder.py tests/test_pydsl_builder.py
git commit -m "Fix Builder.build() to emit canvas=None so renderers auto-size

Canvas() hardcoded a fixed -5..5 viewport that both renderers only ever
expand outward, never shrink — every pydsl diagram rendered inside an
unnecessarily large canvas regardless of how small the construction was.
Both to_svg.py and to_tikz.py already auto-size from resolved geometry
when canvas is None; this was an existing, unused-by-pydsl code path."
```

---

### Task 2: Expose the altitude's vertex-to-foot segment on the `Altitude` handle

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py`
- Modify: `geometry_diagrams/pydsl/api.py`
- Test: `tests/test_pydsl_altitude.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Altitude.segment -> Segment` — the vertex-to-foot segment `altitude()` already constructs internally (`altitude_seg`) but never exposed. Without this, nothing in a pydsl script can `draw()` the actual altitude segment (only the *infinite* perpendicular line via `.line`, or the bare foot point via `.foot`) — a real gap caught during design review, not cosmetic.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_pydsl_altitude.py
def test_altitude_segment_connects_vertex_to_foot():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        alt = altitude(t, from_vertex=a)
        seg = alt.segment
        ir = get_builder().build()
    seg_defs = [d for d in ir.define if d.kind == "segment" and d.id == seg.id]
    assert len(seg_defs) == 1
    assert seg_defs[0].a == a.id
    assert seg_defs[0].b == alt.foot.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_altitude.py::test_altitude_segment_connects_vertex_to_foot -v`
Expected: FAIL with `AttributeError: 'Altitude' object has no attribute 'segment'`

- [ ] **Step 3: Add the field and wire it up**

```python
# geometry_diagrams/pydsl/handles.py — change the Altitude class:
@dataclass(frozen=True)
class Altitude:
    id: str
    foot: Point
    line: Line
    segment: "Segment"
```

```python
# geometry_diagrams/pydsl/api.py — change altitude()'s return statement
# (the seg_id / SegmentDef construction two lines above is already there, unchanged):
    return Altitude(
        id=line_id, foot=Point(id=foot_id), line=Line(id=line_id),
        segment=Segment(id=seg_id),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_altitude.py -v`
Expected: PASS (all 5 tests in the file)

- [ ] **Step 5: Run the full pydsl test suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -k pydsl -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/pydsl/handles.py geometry_diagrams/pydsl/api.py tests/test_pydsl_altitude.py
git commit -m "Expose Altitude.segment (vertex-to-foot) — was constructed but unreachable"
```

---

### Task 3: `draw()` / `draw_points()` pydsl ops

**Files:**
- Modify: `geometry_diagrams/pydsl/api.py`
- Modify: `geometry_diagrams/pydsl/__init__.py`
- Test: `tests/test_pydsl_draw.py`

**Interfaces:**
- Consumes: `Builder._add_render()` (existing, from Task 7 of the Phase 1a plan), `Point`/`AngleRef` handles (existing).
- Produces: `draw(obj) -> None` — appends a `Draw(obj=obj.id)` render op; raises `ValueError` if `obj` is a `Point` (use `draw_points` instead) or an `AngleRef` (use `mark_angle` instead). `draw_points(*points: Point) -> None` — appends a `DrawPoints(points=[...])` render op.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydsl_draw.py
"""Tests for the draw() and draw_points() pydsl ops."""
import pytest

from geometry_diagrams.pydsl.api import draw, draw_points, point, triangle
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.ir.ir import Draw, DrawPoints


def test_draw_appends_draw_op_referencing_the_object_id():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        draw(t)
        ir = builder.build()
    draw_ops = [r for r in ir.render if isinstance(r, Draw)]
    assert len(draw_ops) == 1
    assert draw_ops[0].obj == t.id


def test_draw_points_appends_draw_points_op_with_all_ids():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(1, 0)
        draw_points(a, b)
        ir = builder.build()
    draw_points_ops = [r for r in ir.render if isinstance(r, DrawPoints)]
    assert len(draw_points_ops) == 1
    assert draw_points_ops[0].points == [a.id, b.id]


def test_draw_rejects_a_point_handle():
    with new_builder_context():
        a = point(0, 0)
        with pytest.raises(ValueError, match="draw_points"):
            draw(a)


def test_draw_rejects_an_angle_ref():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
        with pytest.raises(ValueError, match="mark_angle"):
            draw(ref)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pydsl_draw.py -v`
Expected: FAIL with `ImportError: cannot import name 'draw'`

- [ ] **Step 3: Implement `draw()` / `draw_points()`**

```python
# geometry_diagrams/pydsl/api.py — change the top import line to add Draw, DrawPoints:
from geometry_diagrams.ir.ir import AnglePoints, CircleCenterRadius, Draw, DrawPoints, LinePerpendicularThrough, LineThrough, MarkAngles, PointFixed, PointFoot, PointMidpoint, PointTriangleCenter
```

```python
# add to the end of geometry_diagrams/pydsl/api.py:
def draw(obj) -> None:
    """Draw a constructed object (triangle, polygon, circle, line, or segment)."""
    if isinstance(obj, Point):
        raise ValueError("draw() doesn't take a Point — use draw_points(...) instead")
    if isinstance(obj, AngleRef):
        raise ValueError("draw() doesn't take an AngleRef — use mark_angle(...) instead")
    builder = get_builder()
    builder._add_render(Draw(obj=obj.id))


def draw_points(*points: Point) -> None:
    """Draw one or more points as visible markers."""
    builder = get_builder()
    builder._add_render(DrawPoints(points=[p.id for p in points]))
```

```python
# geometry_diagrams/pydsl/__init__.py — full replacement:
"""Python fluent API surface for the geometry construction pipeline (Phase 1a).

Re-exports handles and op functions so callers (and the stub generator) have
one place to introspect the public surface.
"""
from geometry_diagrams.pydsl.api import altitude, circumcircle, draw, draw_points, incircle, line_through, mark_angle, median, point, polygon, triangle
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Circle, Line, Median, Point, Polygon, Segment, Triangle

__all__ = [
    "point",
    "line_through",
    "triangle",
    "polygon",
    "circumcircle",
    "incircle",
    "median",
    "altitude",
    "mark_angle",
    "draw",
    "draw_points",
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

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pydsl_draw.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full pydsl test suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -k pydsl -q`
Expected: all pass — including `test_pydsl_stub.py`, since `stub.py`'s introspection over `pydsl_module.__all__` picks up `draw`/`draw_points` automatically

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_draw.py
git commit -m "Add draw()/draw_points() pydsl ops for explicit, mandatory rendering"
```

---

### Task 4: Extract shared `run_ir_pipeline()` into `ir_pipeline.py`

**Files:**
- Create: `geometry_diagrams/strategies/ir_pipeline.py`
- Modify: `geometry_diagrams/strategies/structured.py`
- Modify: `geometry_diagrams/strategies/recipe.py`

**Interfaces:**
- Consumes: `geometry_diagrams.ir.ir.DiagramIR`, `geometry_diagrams.ir.to_sympy.compile_defs`, `geometry_diagrams.ir.checks.{run_checks, check_render_angles}`, `geometry_diagrams.ir.angle_pairs.resolve_angle_pairs`, `geometry_diagrams.ir.renderer.{Renderer, TikZRenderer}` — all moving verbatim from `structured.py`, behavior unchanged.
- Produces: `run_ir_pipeline(diagram_ir: DiagramIR, renderer: Renderer | None = None) -> StructuredRunResult` and the `StructuredRunResult` dataclass, both now living in `ir_pipeline.py`. `structured.py` re-exports both under their old names (`_run_ir_pipeline`, `StructuredRunResult`) so every existing import/patch of `geometry_diagrams.strategies.structured.{_run_ir_pipeline,StructuredRunResult}` keeps working unchanged. `recipe.py` imports both directly from `ir_pipeline.py` (not transitively via `structured.py`), re-exporting `_run_ir_pipeline` under its own module's old name for the same reason.

This is a pure refactor — no behavior change. There is no new test to write; the existing test suites for `structured.py` and `recipe.py` are the regression check.

- [ ] **Step 1: Create `ir_pipeline.py`**

```python
# geometry_diagrams/strategies/ir_pipeline.py
"""Shared deterministic pipeline: compile a DiagramIR, resolve pending angle
pairs, run geometric checks, then render. Used by every strategy that
produces a DiagramIR by whatever means (LLM-authored JSON in structured.py,
sandboxed pydsl script in python_full.py, recipe-lowered IR in recipe.py) —
this stage is identical regardless of how the DiagramIR was produced.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import sympy.geometry as spg

from ..ir.ir import DiagramIR
from ..ir.to_sympy import compile_defs
from ..ir.checks import run_checks, check_render_angles
from ..ir.angle_pairs import resolve_angle_pairs
from ..ir.renderer import Renderer, TikZRenderer

logger = logging.getLogger(__name__)


@dataclass
class StructuredRunResult:
    diagram_ir: DiagramIR
    tikz: str
    svg: str
    sym_table: dict  # id -> (float, float) coords
    sym_full: dict   # id -> sympy object
    input_tokens: int = 0
    output_tokens: int = 0
    recipe_metadata: Any = None
    retries: int = 0


async def run_ir_pipeline(
    diagram_ir: DiagramIR,
    renderer: Renderer | None = None,
) -> StructuredRunResult:
    """Compile DiagramIR -> SymPy -> checks -> TikZ/SVG. Raises RuntimeError on failure."""
    if renderer is None:
        renderer = TikZRenderer()

    # SymPy compilation and checks are CPU-bound — run off the event loop thread
    # so they don't block async timeouts or concurrent eval runs.
    sym = await asyncio.to_thread(compile_defs, diagram_ir)

    diagram_ir = await asyncio.to_thread(resolve_angle_pairs, diagram_ir, sym)

    results = await asyncio.to_thread(run_checks, diagram_ir.checks, sym)
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    if must_failures:
        msgs = "; ".join(r.message for r in must_failures)
        raise RuntimeError(f"Geometric checks failed: {msgs}")

    for r in results:
        if not r.passed and r.check.level == "prefer":
            logger.warning("Preferred check not satisfied: %s", r.message)

    angle_failures = await asyncio.to_thread(check_render_angles, diagram_ir, sym)
    if angle_failures:
        triples = ", ".join(str(t) for t in angle_failures)
        raise RuntimeError(f"Invalid angle triples (not three distinct points): {triples}")

    render_result = await asyncio.to_thread(renderer.render, diagram_ir, sym)

    sym_table = {k: (float(v.x), float(v.y)) for k, v in sym.items() if isinstance(v, spg.Point)}

    return StructuredRunResult(
        diagram_ir=diagram_ir,
        tikz=render_result.intermediate,
        svg=render_result.output,
        sym_table=sym_table,
        sym_full=sym,
    )
```

- [ ] **Step 2: Remove the moved code from `structured.py`, re-export instead**

Delete these exact lines from `geometry_diagrams/strategies/structured.py`:
- `import sympy.geometry as spg` (line 9 — now unused; `spg` was only referenced inside the moved function)
- `from ..ir.to_sympy import compile_defs` (line 19 — now unused)
- `from ..ir.checks import run_checks, check_render_angles, CheckResult` (line 20 — now unused; `CheckResult` was already unused before this change too)
- `from ..ir.angle_pairs import resolve_angle_pairs` (line 21 — now unused)
- The entire `@dataclass class StructuredRunResult:` block
- The entire `async def _run_ir_pipeline(...)` function body (everything between its `# ── IR pipeline (deterministic, no LLM) ──` comment header and the next `# ── query dispatch ──` comment header)

Add this import in their place (right after the existing `from .instructions import STRUCTURED_STRATEGY_IR_INSTRUCTIONS` line):

```python
from .ir_pipeline import StructuredRunResult, run_ir_pipeline as _run_ir_pipeline
```

Leave everything else in `structured.py` untouched — `Renderer`/`TikZRenderer`/`IRCompileError`/`DiagramIR` imports all stay (still used elsewhere in the file: `Renderer` in type hints, `TikZRenderer()` in `build_agent`, `IRCompileError` in `_run_pipeline_node`'s except clause, `DiagramIR` in state typing and `_prepare_modification_prompt`).

- [ ] **Step 3: Update `recipe.py`'s import**

Change:
```python
from .structured import StructuredRunResult, _run_ir_pipeline, dispatch_query
```
to:
```python
from .structured import dispatch_query
from .ir_pipeline import StructuredRunResult, run_ir_pipeline as _run_ir_pipeline
```

- [ ] **Step 4: Run the regression suite**

Run: `.venv/bin/python -m pytest tests/test_structured_strategy.py tests/test_recipe_strategy.py tests/test_recipe_retry.py -v`
Expected: PASS, unchanged from before the refactor (these tests patch `geometry_diagrams.strategies.structured._run_ir_pipeline` and `geometry_diagrams.strategies.recipe._run_ir_pipeline` by module-qualified name — both must still resolve correctly after the re-export)

- [ ] **Step 5: Run the full test suite to confirm no wider regressions**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: same pass count as before this task (no new tests added in this task; a pure refactor)

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/strategies/ir_pipeline.py geometry_diagrams/strategies/structured.py geometry_diagrams/strategies/recipe.py
git commit -m "Extract run_ir_pipeline()/StructuredRunResult into shared ir_pipeline.py

Pure refactor, no behavior change. structured.py and recipe.py both
re-export the pipeline function under its old private name (_run_ir_pipeline)
since existing tests patch that exact module-qualified name directly.
Needed so the upcoming python_full strategy can reuse the same
compile/check/render pipeline instead of duplicating it."
```

---

### Task 5: `instructions_python_full.py` — prompt template

**Files:**
- Create: `geometry_diagrams/strategies/instructions_python_full.py`
- Test: `tests/test_instructions_python_full.py`

**Interfaces:**
- Consumes: `geometry_diagrams.pydsl.stub.generate_stub()` (existing, Phase 1a Task 8).
- Produces: `build_python_full_instructions() -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_instructions_python_full.py
"""Tests for the python_full strategy's prompt-assembly."""
from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions
from geometry_diagrams.pydsl.stub import generate_stub


def test_build_python_full_instructions_embeds_live_stub_text():
    """The API reference in the prompt must come from generate_stub() at call
    time, not a stale hand-copied string — a signature/docstring change to
    any pydsl op should update this prompt automatically."""
    instructions = build_python_full_instructions()
    assert generate_stub() in instructions


def test_build_python_full_instructions_states_the_mandatory_draw_rule():
    instructions = build_python_full_instructions()
    assert "draw(obj)" in instructions
    assert "draw_points" in instructions


def test_build_python_full_instructions_states_the_sandbox_constraint():
    instructions = build_python_full_instructions()
    assert "no imports" in instructions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_instructions_python_full.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.strategies.instructions_python_full'`

- [ ] **Step 3: Implement the prompt template**

```python
# geometry_diagrams/strategies/instructions_python_full.py
"""Prompt template for the python_full strategy (pydsl script generation)."""
from __future__ import annotations


def build_python_full_instructions() -> str:
    """Assemble the system prompt, embedding the live pydsl API stub text.

    Dynamic by design: calls generate_stub() at build time (not a static,
    hand-copied string) — a docstring/signature change to any pydsl op
    updates this prompt automatically, matching the stub generator's stated
    single-source-of-truth purpose.
    """
    from ..pydsl.stub import generate_stub

    return f"""\
You are a geometry diagram assistant. Given a user request, write a Python script \
that constructs the diagram using ONLY the functions and classes below — no other \
calls, no imports. The script runs in a restricted sandbox; only this API is available.

## Available API

{generate_stub()}

## Rules

- Call `point(x, y)` for every point with concrete, literal coordinates you choose.
- Build the construction using the handle-returning ops above (triangle, polygon,
  circumcircle, incircle, altitude, median, ...). Handle accessors (e.g. `circ.center`,
  `alt.foot`, `t.side(a, b)`) give you the sub-objects you need without inventing names.
- IMPORTANT — nothing is visible in the rendered diagram unless you explicitly say so.
  Call `draw(obj)` on every triangle/polygon/circle/line/segment you want shown, and
  `draw_points(...)` on every point you want marked, as your LAST steps. A script that
  builds geometry but never calls draw()/draw_points() will fail with no visible output.
- Use `mark_angle(ref)` (from `t.angle_at(v)` / `poly.angle_at(v)`) to mark an angle.
- The script is plain top-level statements — no function defs required, no return value.
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_instructions_python_full.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/strategies/instructions_python_full.py tests/test_instructions_python_full.py
git commit -m "Add python_full strategy prompt template (dynamic stub embedding)"
```

---

### Task 6: `PythonFullStrategy`

**Files:**
- Create: `geometry_diagrams/strategies/python_full.py`
- Test: `tests/test_python_full_strategy.py`

**Interfaces:**
- Consumes: `geometry_diagrams.pydsl.sandbox.{run_script, ScriptResult}` (Phase 1a), `geometry_diagrams.strategies.ir_pipeline.{run_ir_pipeline, StructuredRunResult}` (Task 4), `geometry_diagrams.strategies.instructions_python_full.build_python_full_instructions` (Task 5), `geometry_diagrams.strategies.base.{DEFAULT_AGENT_MODEL, SubstanceStrategy}`, `geometry_diagrams.strategies.llm.{get_chat_model, is_gemini_model, extract_usage, make_system_message}`, `geometry_diagrams.ir.errors.IRCompileError`, `geometry_diagrams.ir.renderer.{Renderer, TikZRenderer}`.
- Produces: `PydslScriptOutput` (Pydantic model, one field: `script: str`), `MAX_RETRIES = 3`, `SANDBOX_TIMEOUT_SECONDS = 10.0`, `PythonFullStrategy(SubstanceStrategy)` with `.run(prompt, model, renderer) -> StructuredRunResult` and a `.build_agent()` that raises `NotImplementedError` (no conversational agent in this PoC). Internal (still importable/patchable for tests, matching `structured.py`'s convention): `_generate_script_node`, `_run_script_node`, `_pipeline_router`, `_build_python_full_graph`.

- [ ] **Step 1: Write the failing test file (all cases up front)**

```python
# tests/test_python_full_strategy.py
"""Tests for PythonFullStrategy and its LangGraph pipeline.

Only the LLM call is mocked — the real pydsl sandbox and the real
compile/check/render pipeline run for real (SVGRenderer, no Docker needed).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from geometry_diagrams.strategies.python_full import (
    PythonFullStrategy, PydslScriptOutput, MAX_RETRIES, _run_script_node,
)
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl.sandbox import ScriptResult


VALID_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangle(a, b, c)
draw(t)
"""

TYPO_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangel(a, b, c)
draw(t)
"""

NO_DRAW_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangle(a, b, c)
"""


def _make_script_response(script: str) -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 20}}
    return {"raw": raw, "parsed": PydslScriptOutput(script=script), "parsing_error": None}


def _make_script_fail_response() -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 5, "output_tokens": 2}}
    return {"raw": raw, "parsed": None, "parsing_error": "bad JSON from LLM"}


def _make_mock_llm(side_effects: list):
    """Return a mock LLM where with_structured_output().ainvoke() uses side_effects."""
    structured_mock = MagicMock()
    structured_mock.ainvoke = AsyncMock(side_effect=side_effects)
    mock_llm = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=structured_mock)
    return mock_llm


@pytest.mark.asyncio
async def test_first_attempt_success():
    mock_llm = _make_mock_llm([_make_script_response(VALID_SCRIPT)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 0
    assert len(result.diagram_ir.define) > 0
    assert len(result.diagram_ir.render) > 0


@pytest.mark.asyncio
async def test_script_gen_failure_costs_one_attempt():
    """Mirrors test_structured_strategy.py's test_ir_gen_failure_costs_one_attempt:
    after script generation fails once, the sandbox must still run on the next
    attempt — _run_script_node must not double-count a generation failure."""
    mock_llm = _make_mock_llm([
        _make_script_fail_response(),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_sandbox_failure_retries_with_did_you_mean_and_succeeds():
    mock_llm = _make_mock_llm([
        _make_script_response(TYPO_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_nothing_drawn_guard_retries_and_succeeds():
    mock_llm = _make_mock_llm([
        _make_script_response(NO_DRAW_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_exhausts_retries_and_raises():
    mock_llm = _make_mock_llm([_make_script_response(TYPO_SCRIPT)] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        with pytest.raises(RuntimeError, match="PythonFullStrategy failed"):
            await strategy.run(
                "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
            )


@pytest.mark.asyncio
async def test_run_script_node_falls_back_to_error_when_retry_message_is_none():
    """sandbox.py's ExecutionTimeoutError branch always sets retry_message=None —
    _run_script_node must fall back to result.error so last_error is never empty.
    Tested directly against a canned ScriptResult (not a real timing-dependent
    sandbox race) since this is a deterministic fallback-logic check, not an
    integration behavior."""
    fake_result = ScriptResult(
        diagram_ir=None, error="boom, timed out", error_type="timeout", retry_message=None,
    )
    with patch("geometry_diagrams.strategies.python_full.run_script", return_value=fake_result):
        state = {"script": "point(0, 0)", "attempt": 0, "renderer": SVGRenderer()}
        update = await _run_script_node(state)
    assert update["last_error"] == "boom, timed out"
    assert update["attempt"] == 1


def test_build_agent_raises_not_implemented():
    strategy = PythonFullStrategy()
    with pytest.raises(NotImplementedError):
        strategy.build_agent(model="anthropic:claude-sonnet-4-6")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_python_full_strategy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geometry_diagrams.strategies.python_full'`

- [ ] **Step 3: Implement `PythonFullStrategy`**

```python
# geometry_diagrams/strategies/python_full.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .llm import get_chat_model, is_gemini_model, extract_usage, make_system_message
from .instructions_python_full import build_python_full_instructions
from .ir_pipeline import StructuredRunResult, run_ir_pipeline
from ..ir.errors import IRCompileError
from ..ir.renderer import Renderer, TikZRenderer
from ..pydsl.sandbox import run_script

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
SANDBOX_TIMEOUT_SECONDS = 10.0  # vs. run_script's own 5.0 default — real LLM-generated
                                 # constructions may be larger than hand-authored test scripts.


class PydslScriptOutput(BaseModel):
    script: str = Field(description="A Python script using only the provided pydsl API.")


class PythonFullPipelineState(TypedDict):
    prompt: str
    model_id: str
    enable_cache: bool
    attempt: int
    last_error: str
    script: Optional[str]
    result: Optional[StructuredRunResult]
    input_tokens: int
    output_tokens: int
    renderer: Optional[Any]


async def _generate_script_node(state: PythonFullPipelineState) -> dict:
    """Call the LLM to generate a pydsl script from the prompt."""
    model_id = state["model_id"]
    enable_cache = state.get("enable_cache", False)
    attempt = state["attempt"]
    last_error = state.get("last_error", "")

    prompt = state["prompt"]
    if attempt > 0 and last_error:
        prompt = f"{prompt}\n\nPrevious attempt failed: {last_error}\nPlease produce a corrected script."

    from langchain_core.messages import HumanMessage
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache),
        HumanMessage(content=prompt),
    ]

    try:
        llm = get_chat_model(model_id, enable_cache=enable_cache)
        if is_gemini_model(model_id):
            structured = llm.with_structured_output(PydslScriptOutput, method="json_mode", include_raw=True)
        else:
            structured = llm.with_structured_output(PydslScriptOutput, include_raw=True)

        response = await structured.ainvoke(messages)
        raw_msg = response.get("raw")
        parsed = response.get("parsed")
        in_tok, out_tok = extract_usage(raw_msg) if raw_msg else (0, 0)

        if parsed is None:
            parsing_error = response.get("parsing_error") or "Failed to parse script output"
            return {
                "script": None,
                "last_error": str(parsing_error),
                "attempt": attempt + 1,
                "input_tokens": state["input_tokens"] + in_tok,
                "output_tokens": state["output_tokens"] + out_tok,
            }

        return {
            "script": parsed.script,
            "last_error": "",
            "input_tokens": state["input_tokens"] + in_tok,
            "output_tokens": state["output_tokens"] + out_tok,
        }
    except Exception as exc:
        logger.warning(f"_generate_script_node attempt {attempt} failed: {exc}")
        return {
            "script": None,
            "last_error": str(exc),
            "attempt": attempt + 1,
        }


async def _run_script_node(state: PythonFullPipelineState) -> dict:
    """Run the sandboxed script, then the deterministic compile/check/render pipeline."""
    script = state["script"]
    renderer = state.get("renderer")

    if script is None:
        # _generate_script_node already incremented attempt on failure — don't double-count.
        return {"last_error": "No script available to run"}

    result = await asyncio.to_thread(run_script, script, timeout_seconds=SANDBOX_TIMEOUT_SECONDS)

    if result.error is not None:
        # retry_message is None for ExecutionTimeoutError (sandbox.py's timeout branch never
        # sets it) — fall back to result.error so last_error is never empty on that path.
        return {
            "last_error": result.retry_message or result.error,
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    diagram_ir = result.diagram_ir
    if not diagram_ir.render:
        return {
            "last_error": (
                f"Diagram has {len(diagram_ir.define)} definitions but nothing was "
                "drawn — call draw()/draw_points() on what should be visible before finishing."
            ),
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    try:
        pipeline_result = await run_ir_pipeline(diagram_ir, renderer)
        pipeline_result.retries = state["attempt"]
        return {"result": pipeline_result}
    except (IRCompileError, RuntimeError) as e:
        return {
            "last_error": str(e),
            "attempt": state["attempt"] + 1,
            "result": None,
        }


def _pipeline_router(state: PythonFullPipelineState) -> str:
    if state.get("result") is not None:
        return END
    if state["attempt"] < MAX_RETRIES:
        return "generate_script"
    return END


def _build_python_full_graph() -> StateGraph:
    builder = StateGraph(PythonFullPipelineState)
    builder.add_node("generate_script", _generate_script_node)
    builder.add_node("run_script", _run_script_node)
    builder.add_edge(START, "generate_script")
    builder.add_edge("generate_script", "run_script")
    builder.add_conditional_edges("run_script", _pipeline_router)
    return builder.compile()


class PythonFullStrategy(SubstanceStrategy):
    """pydsl-based strategy: LLM writes a sandboxed Python script, compiled + rendered deterministically."""

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
    ) -> StructuredRunResult:
        graph = _build_python_full_graph()
        initial_state: PythonFullPipelineState = {
            "prompt": prompt,
            "model_id": model,
            "enable_cache": self.enable_cache,
            "attempt": 0,
            "last_error": "",
            "script": None,
            "result": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "renderer": renderer,
        }
        final_state = await graph.ainvoke(initial_state, config=self._run_config)
        if final_state.get("result") is None:
            raise RuntimeError(
                f"PythonFullStrategy failed after {MAX_RETRIES} attempts. "
                f"Last error: {final_state.get('last_error', 'unknown')}"
            )
        return final_state["result"]

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        """Not implemented for this PoC — this strategy has no conversational-agent
        requirement yet. Real chat wiring (render_diagram/query_diagram tools, as
        structured.py provides) is deferred until this strategy actually needs it."""
        raise NotImplementedError(
            "PythonFullStrategy doesn't support build_agent() yet — use .run() directly."
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_python_full_strategy.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (previous count + all tests added across this plan's 6 tasks)

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/strategies/python_full.py tests/test_python_full_strategy.py
git commit -m "Add PythonFullStrategy: LLM-driven pydsl script generation via the sandbox

Structurally mirrors StructureStrategy (StateGraph, MAX_RETRIES=3,
with_structured_output) but the LLM writes a pydsl Python script instead
of DiagramIR JSON. Not registered in evals/run.py yet — standalone PoC
proving the generation mechanism (sandbox + retry-message threading +
draw() requirement) actually works end to end with a real model call."
```

---

## Self-Review Notes

- **Spec coverage:** every design-review fix (canvas, Altitude.segment, aliased re-export in both modules, `_run_script_node` None-guard, `retry_message or error` fallback) has its own task/step above; every spec component (draw ops, ir_pipeline extraction, instructions template, strategy class) has a task.
- **Type consistency check:** `PydslScriptOutput.script`, `ScriptResult.{diagram_ir,error,error_type,retry_message}`, `Altitude.segment`, `StructuredRunResult` fields, and `PythonFullPipelineState` keys are used identically everywhere they recur across Tasks 2, 4, and 6 — verified by re-reading each task's code against the ones before it.
- **Out of scope (unchanged from the design spec):** `evals/run.py` registration, an `auto_draw` flag, a conversational `build_agent()`, recipe/catalog translation, labels, and geometric check ops for pydsl scripts.

# Python-DSL-as-Strategy — "python_full" PoC Design

**Status:** Approved for implementation planning
**Scope:** A new `PythonFullStrategy`, structurally equivalent to `StructureStrategy` (`structured.py`), except the LLM generates a pydsl Python script instead of `DiagramIR` JSON. This is a proof of concept: no catalog/selector layer (that's `recipe.py`'s job, out of scope here), and not wired into `evals/run.py`'s `_STRATEGY_MAP` yet — exercised standalone for now.
**Prereq context:** Builds directly on the Phase 1a pydsl surface (`docs/superpowers/specs/2026-08-03-python-dsl-shim-executor-design.md` and its accompanying plan) — the builder shim, handles, stub generator, sandbox, and retry-classification layer are all consumed unchanged here.

## Goal

Produce a second, LLM-driven front end to the exact same deterministic pipeline `structured.py` already uses (`compile_defs` → `resolve_angle_pairs` → `run_checks` → render), but fed by a sandboxed Python script instead of a JSON `DiagramIR`. This is the first time any Phase 1a component is driven by a real LLM call rather than hand-authored test scripts — it's the point where the "does this actually work end to end with a model in the loop" question gets answered.

```
prompt (+ prior retry_message, if any)
  → LLM.with_structured_output(PydslScriptOutput)  →  script: str
  → sandbox.run_script(script)                      →  ScriptResult(diagram_ir | error, retry_message)
  → [if diagram_ir present] run_ir_pipeline(diagram_ir, renderer)  →  StructuredRunResult | raises
```

## Design decisions (from brainstorming discussion)

- **Mirrors `structured.py`, not `recipe.py`.** No selector, no recipe catalog. One LLM call produces the full construction; a `StateGraph` retries the whole thing on failure. `MAX_RETRIES = 3`, matching the project-wide convention (`structured.py`, `recipe.py`).
- **Drawing is mandatory and explicit for this PoC**, via new `draw()`/`draw_points()` pydsl ops — not auto-drawn. Rationale (user's own past experience): models tend to forget trailing steps, and an auto-draw fallback would silently paper over that failure mode instead of surfacing it. The design leaves room for an `auto_draw` flag later (see Out of scope), but does not build that branch now.
- **Retry loop is a `StateGraph`**, not a reuse of `retry_loop.run_with_retries` (the Phase 1a driver). That function's tests assume a synchronous, non-LLM `make_script`; bending it to drive an async LLM call would diverge from how every other strategy in this codebase structures retries. `retry_loop.py` stays as-is, exercised only by its own Phase 1a tests.
- **Not registered in `evals/run.py` yet.** Exercised via direct script/tests for this PoC; bench integration (retry-cap tuning for live vs. batch, judge scoring, A/B plumbing against `structured`/`recipe`) is an explicit later step once the basic mechanism is proven.
- **Shared pipeline code, not duplicated.** `structured.py`'s `_run_ir_pipeline` (compile → resolve angle pairs → checks → render) is identical to what this strategy needs downstream of getting a `DiagramIR`. Extract it into `geometry_diagrams/strategies/ir_pipeline.py` as `run_ir_pipeline()`, imported by both.
  **Correction from design review:** `recipe.py` already does `from .structured import StructuredRunResult, _run_ir_pipeline, dispatch_query` — a third consumer, not two. `StructuredRunResult` must move to `ir_pipeline.py` too (it's the pipeline's return type), re-exported from `structured.py` (evals/run.py and several tests import it from there). Both `structured.py` and `recipe.py` must keep re-exporting the pipeline function under its **old, private name** — `from .ir_pipeline import run_ir_pipeline as _run_ir_pipeline` — because `tests/test_structured_strategy.py` and `tests/test_recipe_strategy.py`/`test_recipe_retry.py` patch `structured._run_ir_pipeline` / `recipe._run_ir_pipeline` directly by that module-qualified name. Updating call sites to the new public name instead (dropping the aliased re-export) would silently break those patches — not a viable option despite being "cleaner."

## Components

### 1. `draw()` / `draw_points()` — new pydsl ops

**File:** `geometry_diagrams/pydsl/api.py` (add), `geometry_diagrams/pydsl/__init__.py` (export)

```python
def draw(obj) -> None:
    """Draw a constructed object (triangle, circle, line, segment, polygon, altitude, median, ...)."""
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

`Median` is fully drawable via its existing `.segment` field (`draw(med.segment)`). **`Altitude` is not — this is a real gap, not just documentation:** `api.py`'s `altitude()` already constructs the vertex→foot `Segment` def (`altitude_seg`), but the `Altitude` handle (`handles.py`) only exposes `foot` and `line` — `line` is the *infinite* perpendicular line, not the drawable segment, so the natural "draw this altitude" object is currently unreachable from the handle. Fix as part of this work: add a `segment: Segment` field to `Altitude` (`handles.py`) and set it in `altitude()`'s return (the segment def already exists — this only exposes it). `stub.py`'s introspection picks up the new field automatically once added.

Uses the existing `Builder._add_render()` (already added in Task 7 for `mark_angle`) — no builder changes needed for `draw()`/`draw_points()` themselves.

**Separate, necessary fix in `builder.py`: `Builder.build()` must stop hardcoding `canvas=Canvas()`.** `Canvas()` defaults to fixed `-5..5` bounds; both `to_svg.py` and `to_tikz.py` only ever *expand* those bounds outward for out-of-range points, never shrink them — so every pydsl diagram currently renders inside an unnecessarily large, zoomed-out `10×10` canvas regardless of how small the actual construction is (a unit triangle would render tiny in the middle of a mostly-empty canvas). Both renderers already have a working fallback for this: `diagram.canvas is None` triggers `compute_bounds()`/auto-sizing from the resolved geometry directly (confirmed in both `to_svg.py:126-140` and `to_tikz.py:76-97` — "canvas may be None" is an existing, exercised code path, not new). Fix: change `Builder.build()`'s `canvas=Canvas()` to `canvas=None`. One-line change, benefits every pydsl consumer (not just this strategy), and requires no new logic since both renderers already handle it.

### 2. Shared `run_ir_pipeline()`

**File:** `geometry_diagrams/strategies/ir_pipeline.py` (new)

Move `structured.py`'s module-level `_run_ir_pipeline` (and the `StructuredRunResult` dataclass it returns) here verbatim, renamed to `run_ir_pipeline`/`StructuredRunResult` (no longer structured.py-private — now a cross-module shared helper). Both `structured.py` and `recipe.py` import and re-export it under the old private name: `from .ir_pipeline import run_ir_pipeline as _run_ir_pipeline`, `from .ir_pipeline import StructuredRunResult` — required so existing test patches (`patch("geometry_diagrams.strategies.structured._run_ir_pipeline", ...)`, same for `recipe`) keep working unchanged. Behavior is unchanged; this is a pure extraction, not a rewrite. Run the full test suite afterward as a regression check on both `structured.py` and `recipe.py`, not just `structured.py`.

### 3. `instructions_python_full.py` — prompt template

**File:** `geometry_diagrams/strategies/instructions_python_full.py` (new)

```python
def build_python_full_instructions() -> str:
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

This is dynamically assembled (calls `generate_stub()` at build time, not baked in statically) — a docstring/signature change to any pydsl op updates the prompt automatically, matching the stub generator's stated purpose in Phase 1a.

### 4. `PythonFullStrategy`

**File:** `geometry_diagrams/strategies/python_full.py` (new)

```python
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


async def _generate_script_node(state) -> dict:
    # Same shape as structured.py's _generate_ir_node: build prompt (+ last_error
    # appended on retries), call llm.with_structured_output(PydslScriptOutput),
    # extract .script and token usage.
    ...


async def _run_script_node(state) -> dict:
    # Mirrors structured.py's _run_pipeline_node, including its None-guard: if
    # _generate_script_node already failed (state["script"] is None), _generate_script_node
    # already incremented attempt — this node must NOT increment it again (this is exactly
    # the double-count bug tests/test_structured_strategy.py's
    # test_ir_gen_failure_costs_one_attempt exists to catch; the equivalent test here is
    # test_script_gen_failure_costs_one_attempt).
    # if state["script"] is None: return {"last_error": "No script available to run"}
    #
    # result = await asyncio.to_thread(run_script, state["script"], timeout_seconds=SANDBOX_TIMEOUT_SECONDS)
    # if result.error:
    #     # retry_message is None for ExecutionTimeoutError (sandbox.py's timeout branch never
    #     # sets it) — fall back to result.error so last_error is never None on this path.
    #     last_error = result.retry_message or result.error; attempt += 1; return
    # if not result.diagram_ir.render:  # the "forgot to draw" guard
    #     last_error = (f"Diagram has {len(result.diagram_ir.define)} definitions but "
    #                    "nothing was drawn — call draw()/draw_points() on what should "
    #                    "be visible before finishing.")
    #     attempt += 1; return
    # try: result = await run_ir_pipeline(result.diagram_ir, renderer); return {"result": result}
    # except (IRCompileError, RuntimeError) as e: last_error = str(e); attempt += 1
    ...


def _pipeline_router(state) -> str:
    # identical to structured.py's _pipeline_router
    ...


class PythonFullStrategy(SubstanceStrategy):
    async def run(self, prompt, model=DEFAULT_AGENT_MODEL, renderer=None) -> StructuredRunResult:
        # build graph, run, raise RuntimeError after MAX_RETRIES — identical shape to
        # StructureStrategy.run()
        ...

    def build_agent(self, model=DEFAULT_AGENT_MODEL, renderer=None):
        # SubstanceStrategy.build_agent is abstract; this PoC has no conversational-agent
        # requirement, so satisfy it minimally: raise NotImplementedError("PythonFullStrategy
        # doesn't support build_agent() yet — use .run() directly."). Real chat wiring
        # (render_diagram/query_diagram tools, as structured.py provides) is deferred until
        # this strategy actually needs to be chat-driven.
        ...
```

`MAX_RETRIES = 3`. `SANDBOX_TIMEOUT_SECONDS` default 10.0 (vs. `run_script`'s own library default of 5.0 — real LLM-generated constructions may be larger than the hand-authored Phase 1a test scripts).

## Error handling / retry semantics

Three independent, each-cost-one-attempt failure points (extending `structured.py`'s already-tested "one failure, one attempt" invariant with a third case specific to this strategy):

1. **Script generation failure** — malformed/unparseable LLM output. `_run_script_node` must not double-count this (see its None-guard above).
2. **Sandbox failure** (`ScriptResult.error is not None`) — import/dangerous-call/hallucinated-API/structural-precondition/timeout, already classified and did-you-mean-enhanced by the Phase 1a retry layer (Tasks 9–10). `last_error = result.retry_message or result.error` (the `or` fallback matters: `ExecutionTimeoutError`'s branch in `sandbox.py` always sets `retry_message=None`, so relying on `retry_message` alone would silently carry no error text into the next prompt on a timeout).
3. **Nothing-drawn guard** — script succeeds, defs exist, `render` list is empty. `last_error` is a purpose-written message (not from the sandbox — this is strategy-level business logic; the sandbox has no opinion on what "should" be visible). Known limitation, acceptable for this PoC: a script that only calls `mark_angle(...)` (which does append to `render`) satisfies this guard without drawing any actual geometry — a narrower, more precise check is future work, not blocking here.
4. **Pipeline failure** — `run_ir_pipeline` raises (geometric check failure, invalid angle triple, etc.), same as `structured.py`.

After `MAX_RETRIES` (3) exhausted attempts: raise `RuntimeError` with the last error, identical convention to `structured.py`/`recipe.py`.

## Testing

- `tests/test_pydsl_draw.py`: `draw(t)` appends `Draw(obj=t.id)`; `draw_points(a, b)` appends `DrawPoints(points=[a.id, b.id])`; `draw(point_handle)` and `draw(angle_ref)` raise `ValueError` naming the correct alternative function.
- `tests/test_python_full_strategy.py`: mirrors `tests/test_structured_strategy.py`'s approach exactly — mock only `get_chat_model().with_structured_output().ainvoke`, feed real hand-authored script strings as the canned "model output." Everything downstream (real sandbox subprocess, real `compile_defs`/checks/render) runs for real, no Docker required if the test passes an `SVGRenderer()`. Cases:
  - First-attempt success.
  - **Script generation failure costs exactly one attempt** (`test_script_gen_failure_costs_one_attempt`, the direct analog of `test_structured_strategy.py`'s `test_ir_gen_failure_costs_one_attempt` — this is the double-count regression the `_run_script_node` None-guard exists to prevent).
  - Sandbox failure (typo'd call) → retry with did-you-mean in the prompt → success.
  - Timeout-classified sandbox failure → `last_error` is non-empty despite `retry_message` being `None` (covers the `or result.error` fallback).
  - Nothing-drawn failure → retry with the guard's message → success.
  - Exhausts `MAX_RETRIES` → `RuntimeError` raised, message includes the last failure.
- `tests/test_structured_strategy.py` **and** `tests/test_recipe_strategy.py`/`test_recipe_retry.py` must still pass unchanged after the `run_ir_pipeline`/`StructuredRunResult` extraction (pure refactor, no behavior change) — run the full suite as a regression check, since `recipe.py` is a consumer too.

## Out of scope for this PoC

- `evals/run.py` / `_STRATEGY_MAP` registration and bench integration (retry-cap tuning for live-chat-vs-batch, LLM-judge scoring, A/B comparison against `structured`/`recipe`).
- An `auto_draw` flag/mode. The design intentionally leaves room for one (a post-process that adds `Draw` for every def, analogous to `recipe/lower.py`'s `auto_draw_all` but adapted for pydsl's all-hidden-id convention) but does not build it now — only add it when a concrete need appears.
- A conversational `build_agent()` (chat-driven render_diagram/query_diagram tools, as `structured.py` provides). The abstract method is satisfied minimally; real chat wiring is deferred.
- Recipe/catalog translation (unchanged from the Phase 1a design doc — still `recipe.py`'s territory, not touched by this strategy).
- **Labels.** pydsl has no label ops and every id is hidden (`__pydsl_pt_1`-style) — diagrams from this strategy will be unlabeled. Visible in any future side-by-side comparison against `structured`/`recipe` output; not addressed here.
- **Geometric check ops.** No pydsl op appends to `DiagramIR.checks`, so `checks` is always `[]` and the "geometric validation fails → retry" channel that makes `structured.py` robust essentially never fires for this strategy yet. Acceptable for a PoC proving the generation mechanism; a real bench comparison later would need to weigh this.
- Retry-prompt wording: the appended "previous attempt failed" text should say "corrected script," not "corrected DiagramIR" (copy difference from `structured.py`'s equivalent text — call this out explicitly when writing `_generate_script_node`, easy to get wrong by copy-pasting).

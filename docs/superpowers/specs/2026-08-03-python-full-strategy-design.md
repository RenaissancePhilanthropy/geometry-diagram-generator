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

`Altitude`/`Median` handles aren't directly drawable as a single object (they bundle a foot/midpoint point plus a line/segment) — `draw(alt.line)`, `draw(alt.foot's containing segment)`, etc. are drawn via their component handles, all of which expose `.id`-bearing sub-parts already. No new handle-side code needed beyond the two functions above; `stub.py`'s introspection picks them up automatically (single source of truth, unchanged from Phase 1a).

Uses the existing `Builder._add_render()` (already added in Task 7 for `mark_angle`) — no builder changes needed.

### 2. Shared `run_ir_pipeline()`

**File:** `geometry_diagrams/strategies/ir_pipeline.py` (new)

Move `structured.py`'s module-level `_run_ir_pipeline` here verbatim, rename to `run_ir_pipeline` (no longer private — now a cross-module shared helper). `structured.py` imports and calls it under its old name via `from .ir_pipeline import run_ir_pipeline as _run_ir_pipeline` (minimal diff) or updates its call sites directly (cleaner — prefer this). Behavior is unchanged; this is a pure extraction, not a rewrite.

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
    # asyncio.to_thread(run_script, state["script"], timeout_seconds=SANDBOX_TIMEOUT_SECONDS)
    #   -> ScriptResult
    # if result.error: last_error = result.retry_message; attempt += 1; return
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

1. **Script generation failure** — malformed/unparseable LLM output.
2. **Sandbox failure** (`ScriptResult.error is not None`) — import/dangerous-call/hallucinated-API/structural-precondition/timeout, already classified and did-you-mean-enhanced by the Phase 1a retry layer (Tasks 9–10). `last_error = result.retry_message`.
3. **Nothing-drawn guard** — script succeeds, defs exist, `render` list is empty. `last_error` is a purpose-written message (not from the sandbox — this is strategy-level business logic; the sandbox has no opinion on what "should" be visible).
4. **Pipeline failure** — `run_ir_pipeline` raises (geometric check failure, invalid angle triple, etc.), same as `structured.py`.

After `MAX_RETRIES` (3) exhausted attempts: raise `RuntimeError` with the last error, identical convention to `structured.py`/`recipe.py`.

## Testing

- `tests/test_pydsl_draw.py`: `draw(t)` appends `Draw(obj=t.id)`; `draw_points(a, b)` appends `DrawPoints(points=[a.id, b.id])`; `draw(point_handle)` and `draw(angle_ref)` raise `ValueError` naming the correct alternative function.
- `tests/test_python_full_strategy.py`: mirrors `tests/test_structured_strategy.py`'s approach exactly — mock only `get_chat_model().with_structured_output().ainvoke`, feed real hand-authored script strings as the canned "model output." Everything downstream (real sandbox subprocess, real `compile_defs`/checks/render) runs for real, no Docker required if the test passes an `SVGRenderer()`. Cases:
  - First-attempt success.
  - Sandbox failure (typo'd call) → retry with did-you-mean in the prompt → success.
  - Nothing-drawn failure → retry with the guard's message → success.
  - Exhausts `MAX_RETRIES` → `RuntimeError` raised, message includes the last failure.
- `tests/test_structured_strategy.py` must still pass unchanged after the `run_ir_pipeline` extraction (pure refactor, no behavior change) — run the full suite as a regression check.

## Out of scope for this PoC

- `evals/run.py` / `_STRATEGY_MAP` registration and bench integration (retry-cap tuning for live-chat-vs-batch, LLM-judge scoring, A/B comparison against `structured`/`recipe`).
- An `auto_draw` flag/mode. The design intentionally leaves room for one (a post-process that adds `Draw` for every def, analogous to `recipe/lower.py`'s `auto_draw_all` but adapted for pydsl's all-hidden-id convention) but does not build it now — only add it when a concrete need appears.
- A conversational `build_agent()` (chat-driven render_diagram/query_diagram tools, as `structured.py` provides). The abstract method is satisfied minimally; real chat wiring is deferred.
- Recipe/catalog translation (unchanged from the Phase 1a design doc — still `recipe.py`'s territory, not touched by this strategy).

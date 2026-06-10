# LangFuse Tracing — Design Spec

**Date:** 2026-06-09  
**Status:** Approved  
**Goal:** Add opt-in LangFuse observability so that every strategy graph run produces a hierarchical trace (graph nodes as spans → LLM calls as child spans) visible in a self-hosted LangFuse instance.

---

## Motivation

The recipe pipeline runs a LangGraph `StateGraph` with three nodes (selector, DSL generation, IR pipeline). When a run fails or is slow, there is currently no way to inspect which node was responsible, what prompts were sent, or how many tokens each step consumed. LangFuse traces provide that visibility without changes to the core pipeline logic.

---

## Scope

- Tracing of all `graph.ainvoke()` calls across all strategies and the eval harness query phase.
- Enabled by env var; zero overhead and zero import cost when disabled.
- No UI changes, no changes to `GeometryConfig`, no new config files.
- LangFuse prompt management and dataset/eval features are out of scope for this change.

---

## Architecture

### New module: `geometry_diagrams/util/tracing.py`

Single responsibility: own the LangFuse `CallbackHandler` lifecycle.

```
get_callback_handler() -> CallbackHandler | None
```

Behaviour:
- If `LANGFUSE_BASE_URL` is **not set** → return `None` (tracing disabled, no imports attempted).
- If `LANGFUSE_BASE_URL` **is set** → tracing is enabled. If either `LANGFUSE_PUBLIC_KEY` or `LANGFUSE_SECRET_KEY` is missing, raise `RuntimeError` immediately (misconfiguration is fatal, not silently swallowed).
- On first successful call, create a `langfuse.callback.CallbackHandler` and cache it as a module-level singleton. Subsequent calls return the cached instance.
- The `langfuse` import lives inside the function body so the package is never imported when tracing is disabled.

### Base class: `SubstanceStrategy._run_config`

A property added to `SubstanceStrategy` in `geometry_diagrams/strategies/base.py`:

```python
@property
def _run_config(self) -> dict:
    from geometry_diagrams.util.tracing import get_callback_handler
    h = get_callback_handler()
    return {"callbacks": [h]} if h else {}
```

All `graph.ainvoke()` calls pass `config=self._run_config`. LangGraph propagates the callback down through every node and every LLM call within the graph, producing a hierarchical trace automatically.

### Call sites updated

Every concrete strategy overrides `run()` with its own `graph.ainvoke()` call. The `_run_config` property is shared infrastructure; each strategy is responsible for passing it.

**Strategy `run()` methods — add `config=self._run_config` to each `graph.ainvoke()` call:**

| File | ainvoke call sites |
|---|---|
| `geometry_diagrams/strategies/base.py` | Add `_run_config` property; update the fallback `run()` |
| `geometry_diagrams/strategies/raw_code.py` | 1 call (line ~54) |
| `geometry_diagrams/strategies/raw_svg.py` | 1 call |
| `geometry_diagrams/strategies/raw_svg_with_revise.py` | 2 calls (draft + revision graphs) |
| `geometry_diagrams/strategies/structured.py` | 1 call |
| `geometry_diagrams/strategies/recipe.py` | 1 call |

**`stages.py` helpers** — `RawCodeWithReviseStrategy.run()` delegates to `run_draft()` and `run_revision()` in `geometry_diagrams/strategies/stages.py` rather than calling `graph.ainvoke()` directly. These functions gain an optional `run_config: dict | None = None` parameter that is passed through to their `graph.ainvoke()` calls. `RawCodeWithReviseStrategy.run()` passes `run_config=self._run_config` when calling them.

**Eval harness** — `evals/run.py` `_run_query_phase()` is not inside a strategy. It calls `get_callback_handler()` directly and passes the result as `config={"callbacks": [h]} if h else {}` to its query agent's `graph.ainvoke()`.

---

## Configuration

All three env vars must be set together. `LANGFUSE_BASE_URL` is the enable flag.

| Env var | Required when | Notes |
|---|---|---|
| `LANGFUSE_BASE_URL` | Always (to enable) | URL of the self-hosted LangFuse instance, e.g. `https://langfuse.example.com` |
| `LANGFUSE_PUBLIC_KEY` | When `LANGFUSE_BASE_URL` is set | Fatal error if absent |
| `LANGFUSE_SECRET_KEY` | When `LANGFUSE_BASE_URL` is set | Fatal error if absent |

Add to `.env.example` (or equivalent documentation) alongside existing `ANTHROPIC_API_KEY`.

---

## Dependencies

Add `langfuse` as an optional dependency group in `pyproject.toml`:

```toml
[dependency-groups]
tracing = ["langfuse>=2.0"]
```

Not included in the default `dependencies` list. Install with `uv sync --group tracing` when tracing is needed.

---

## What traces look like

Each `strategy.run()` call → one LangGraph trace in LangFuse.

For `RecipeStrategy`:
```
trace: RecipeStrategy.run (or graph run ID)
  span: select_recipes       [latency, tokens]
    span: llm call (haiku)   [prompt, response, tokens]
  span: generate_dsl         [latency, tokens]
    span: llm call (sonnet)  [prompt, response, tokens]
  span: run_recipe_pipeline  [latency]        # no LLM calls
  # retries: generate_dsl and run_recipe_pipeline repeat
```

For raw strategies: single `create_react_agent` graph → trace with tool call spans interleaved with LLM call spans.

The eval harness query phase (`_run_query_phase`) produces a separate trace per query agent invocation.

---

## Error handling

- `LANGFUSE_BASE_URL` absent → `None` returned, tracing silently disabled. No log message.
- `LANGFUSE_BASE_URL` present, keys missing → `RuntimeError` raised at first call to `get_callback_handler()`. This surfaces at strategy invocation time, not at import time.
- `langfuse` package not installed but `LANGFUSE_BASE_URL` is set → `ImportError` propagates (the user opted in to tracing and must install the package).
- LangFuse server unreachable at runtime → LangFuse SDK handles this internally (queues and retries); pipeline execution is not blocked.

---

## Testing

- Unit test for `get_callback_handler()`: env absent → `None`; env present with keys → returns handler (mock the LangFuse constructor); env present without keys → `RuntimeError`.
- No integration test against a real LangFuse server (infra dependency, out of scope).
- Existing strategy tests are unaffected: `_run_config` returns `{}` when no env vars are set, so `graph.ainvoke()` calls are unchanged.

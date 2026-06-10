# LangFuse Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in LangFuse observability so every LangGraph strategy run produces a hierarchical trace (graph nodes as spans → LLM calls as child spans) when `LANGFUSE_HOST` is set.

**Architecture:** A new `tracing.py` module owns the LangFuse handler lifecycle — it returns a cached `CallbackHandler` when `LANGFUSE_HOST` is set, raises `RuntimeError` if keys are missing, and returns `None` otherwise. The `SubstanceStrategy` base class exposes a `_run_config` property that wraps that handler into a LangGraph config dict. Every `graph.ainvoke()` call across all strategies passes `config=self._run_config`, which causes LangGraph to propagate the callback down through all nodes and all LLM calls automatically.

**Tech Stack:** `langfuse>=2.0` (optional dep), LangGraph `config={"callbacks": [...]}` propagation, `pytest` with `monkeypatch` for unit tests.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `geometry_diagrams/util/tracing.py` | **Create** | Handler factory, singleton cache, `_reset()` for tests |
| `tests/test_tracing.py` | **Create** | Unit tests for `get_callback_handler()` |
| `pyproject.toml` | **Modify** | Add `[dependency-groups] tracing = ["langfuse>=2.0"]` |
| `geometry_diagrams/strategies/base.py` | **Modify** | Add `_run_config` property; update fallback `run()` |
| `geometry_diagrams/strategies/raw_code.py` | **Modify** | Pass `config=self._run_config` to `graph.ainvoke()` (line ~54) |
| `geometry_diagrams/strategies/raw_svg.py` | **Modify** | Pass `config=self._run_config` to `graph.ainvoke()` (line ~86) |
| `geometry_diagrams/strategies/raw_svg_with_revise.py` | **Modify** | Pass config to both `ainvoke()` calls (lines ~28, ~36) |
| `geometry_diagrams/strategies/structured.py` | **Modify** | Pass `config=self._run_config` to `graph.ainvoke()` (line ~298) |
| `geometry_diagrams/strategies/recipe.py` | **Modify** | Pass `config=self._run_config` to `graph.ainvoke()` (line ~416) |
| `geometry_diagrams/strategies/stages.py` | **Modify** | Add optional `run_config` param to `run_draft()` and `run_revision()` |
| `geometry_diagrams/strategies/raw_code_with_revise.py` | **Modify** | Pass `run_config=self._run_config` to `run_draft()` / `run_revision()` |
| `evals/run.py` | **Modify** | Wire `get_callback_handler()` into `_run_query_phase()` |

---

## Task 1: Create `tracing.py` and its tests

**Files:**
- Create: `geometry_diagrams/util/tracing.py`
- Create: `tests/test_tracing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tracing.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_tracing():
    """Reset tracing module singleton before each test."""
    from geometry_diagrams.util import tracing
    tracing._reset()
    yield
    tracing._reset()


def test_disabled_when_no_host(monkeypatch):
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from geometry_diagrams.util.tracing import get_callback_handler
    assert get_callback_handler() is None


def test_second_call_returns_same_none(monkeypatch):
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    from geometry_diagrams.util.tracing import get_callback_handler
    assert get_callback_handler() is None
    assert get_callback_handler() is None


def test_fatal_when_host_set_public_key_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    from geometry_diagrams.util.tracing import get_callback_handler
    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
        get_callback_handler()


def test_fatal_when_host_set_secret_key_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from geometry_diagrams.util.tracing import get_callback_handler
    with pytest.raises(RuntimeError, match="LANGFUSE_SECRET_KEY"):
        get_callback_handler()


def test_fatal_when_host_set_both_keys_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from geometry_diagrams.util.tracing import get_callback_handler
    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
        get_callback_handler()


def test_returns_handler_when_all_vars_set(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    mock_handler = MagicMock()
    mock_cls = MagicMock(return_value=mock_handler)
    with patch.dict("sys.modules", {"langfuse": MagicMock(), "langfuse.callback": MagicMock(CallbackHandler=mock_cls)}):
        from geometry_diagrams.util.tracing import get_callback_handler
        result = get_callback_handler()
    mock_cls.assert_called_once_with(
        public_key="pk-test",
        secret_key="sk-test",
        host="https://langfuse.example.com",
    )
    assert result is mock_handler


def test_returns_cached_handler_on_second_call(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    mock_handler = MagicMock()
    mock_cls = MagicMock(return_value=mock_handler)
    with patch.dict("sys.modules", {"langfuse": MagicMock(), "langfuse.callback": MagicMock(CallbackHandler=mock_cls)}):
        from geometry_diagrams.util.tracing import get_callback_handler
        r1 = get_callback_handler()
        r2 = get_callback_handler()
    assert r1 is r2
    assert mock_cls.call_count == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_tracing.py -v
```

Expected: all tests fail with `ModuleNotFoundError` (module doesn't exist yet).

- [ ] **Step 3: Create `geometry_diagrams/util/tracing.py`**

```python
from __future__ import annotations

import os

_handler = None
_initialized = False


def get_callback_handler():
    """Return a LangFuse CallbackHandler when LANGFUSE_HOST is set, else None.

    LANGFUSE_HOST being set is the enable flag. If it is set,
    LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must also be present
    or a RuntimeError is raised.

    The handler is created once and cached for the lifetime of the process.
    """
    global _handler, _initialized
    if _initialized:
        return _handler

    host = os.getenv("LANGFUSE_HOST")
    if not host:
        _initialized = True
        return None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    missing = [name for name, val in [
        ("LANGFUSE_PUBLIC_KEY", public_key),
        ("LANGFUSE_SECRET_KEY", secret_key),
    ] if not val]
    if missing:
        raise RuntimeError(
            f"LANGFUSE_HOST is set but required env vars are missing: {', '.join(missing)}"
        )

    from langfuse.callback import CallbackHandler
    _handler = CallbackHandler(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )
    _initialized = True
    return _handler


def _reset() -> None:
    """Reset cached handler state. For use in tests only."""
    global _handler, _initialized
    _handler = None
    _initialized = False
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_tracing.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/util/tracing.py tests/test_tracing.py
git commit -m "feat: add LangFuse tracing module with handler factory"
```

---

## Task 2: Add `_run_config` property to `SubstanceStrategy`

**Files:**
- Modify: `geometry_diagrams/strategies/base.py`

- [ ] **Step 1: Add `_run_config` property and update `run()`**

In `geometry_diagrams/strategies/base.py`, the class currently looks like:

```python
class SubstanceStrategy(ABC):
    def __init__(self, enable_cache: bool = False):
        ...

    @abstractmethod
    def build_agent(...): ...

    async def run(self, prompt, model=DEFAULT_AGENT_MODEL, renderer=None):
        from langchain_core.messages import HumanMessage
        graph = self.build_agent(model=model)
        result = await graph.ainvoke({"messages": [HumanMessage(content=prompt)]})
        return result
```

Replace the class body with (keep `__init__`, `logger`, `build_agent` unchanged — only add `_run_config` and update `run()`):

```python
    @property
    def _run_config(self) -> dict:
        from geometry_diagrams.util.tracing import get_callback_handler
        h = get_callback_handler()
        return {"callbacks": [h]} if h else {}

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: "Renderer | None" = None,
    ) -> Any:
        from langchain_core.messages import HumanMessage
        graph = self.build_agent(model=model)
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            config=self._run_config,
        )
        return result
```

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_agent_e2e.py -x
```

Expected: all existing tests pass (tracing is disabled — no `LANGFUSE_HOST` set).

- [ ] **Step 3: Commit**

```bash
git add geometry_diagrams/strategies/base.py
git commit -m "feat: add _run_config property to SubstanceStrategy base class"
```

---

## Task 3: Wire direct strategy `run()` overrides

Each of the five strategies below calls `graph.ainvoke(...)` directly in its own `run()`. Add `config=self._run_config` to each call.

**Files:**
- Modify: `geometry_diagrams/strategies/raw_code.py`
- Modify: `geometry_diagrams/strategies/raw_svg.py`
- Modify: `geometry_diagrams/strategies/raw_svg_with_revise.py`
- Modify: `geometry_diagrams/strategies/structured.py`
- Modify: `geometry_diagrams/strategies/recipe.py`

- [ ] **Step 1: `raw_code.py` — one ainvoke call**

In `RawCodeStrategy.run()`, find:
```python
        graph = self.build_agent(model=model)
        state = await graph.ainvoke({"messages": [("user", prompt)]})
```

Replace with:
```python
        graph = self.build_agent(model=model)
        state = await graph.ainvoke({"messages": [("user", prompt)]}, config=self._run_config)
```

- [ ] **Step 2: `raw_svg.py` — one ainvoke call**

In `RawSVGStrategy.run()`, find:
```python
        graph = self.build_agent(model=model)
        state = await graph.ainvoke({"messages": [("user", prompt)]})
```

Replace with:
```python
        graph = self.build_agent(model=model)
        state = await graph.ainvoke({"messages": [("user", prompt)]}, config=self._run_config)
```

- [ ] **Step 3: `raw_svg_with_revise.py` — two ainvoke calls**

In `RawSVGWithReviseStrategy.run()`, find:
```python
        draft_state = await draft_graph.ainvoke({"messages": [("user", prompt)]})
```
Replace with:
```python
        draft_state = await draft_graph.ainvoke({"messages": [("user", prompt)]}, config=self._run_config)
```

Then find:
```python
        revision_state = await revision_graph.ainvoke({
            "messages": list(draft_messages) + [("user", REVISION_PROMPT)]
        })
```
Replace with:
```python
        revision_state = await revision_graph.ainvoke(
            {"messages": list(draft_messages) + [("user", REVISION_PROMPT)]},
            config=self._run_config,
        )
```

- [ ] **Step 4: `structured.py` — one ainvoke call**

In `StructureStrategy.run()`, find:
```python
        final_state = await graph.ainvoke(initial_state)
```
Replace with:
```python
        final_state = await graph.ainvoke(initial_state, config=self._run_config)
```

- [ ] **Step 5: `recipe.py` — one ainvoke call**

In `RecipeStrategy.run()`, find:
```python
        final_state = await graph.ainvoke(initial_state)
```
Replace with:
```python
        final_state = await graph.ainvoke(initial_state, config=self._run_config)
```

- [ ] **Step 6: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_agent_e2e.py -x
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add geometry_diagrams/strategies/raw_code.py \
        geometry_diagrams/strategies/raw_svg.py \
        geometry_diagrams/strategies/raw_svg_with_revise.py \
        geometry_diagrams/strategies/structured.py \
        geometry_diagrams/strategies/recipe.py
git commit -m "feat: wire LangFuse _run_config into strategy run() overrides"
```

---

## Task 4: Wire `stages.py` helpers and `RawCodeWithReviseStrategy`

`RawCodeWithReviseStrategy.run()` delegates to `run_draft()` and `run_revision()` in `stages.py` rather than calling `graph.ainvoke()` directly. These helpers need an optional `run_config` parameter.

**Files:**
- Modify: `geometry_diagrams/strategies/stages.py`
- Modify: `geometry_diagrams/strategies/raw_code_with_revise.py`

- [ ] **Step 1: Update `run_draft()` in `stages.py`**

Current signature (line ~209):
```python
async def run_draft(
    prompt: str,
    model: str = DEFAULT_AGENT_MODEL,
    model_settings: dict | None = None,
):
    ...
    return await graph.ainvoke({"messages": [("user", prompt)]})
```

New signature and call:
```python
async def run_draft(
    prompt: str,
    model: str = DEFAULT_AGENT_MODEL,
    model_settings: dict | None = None,
    run_config: dict | None = None,
):
    ...
    return await graph.ainvoke({"messages": [("user", prompt)]}, config=run_config or {})
```

- [ ] **Step 2: Update `run_revision()` in `stages.py`**

Current signature (line ~269):
```python
async def run_revision(
    model: str,
    message_history: list[BaseMessage],
    force_rerender: bool = True,
    model_settings: dict | None = None,
):
    ...
    return await graph.ainvoke({"messages": messages})
```

New signature and call:
```python
async def run_revision(
    model: str,
    message_history: list[BaseMessage],
    force_rerender: bool = True,
    model_settings: dict | None = None,
    run_config: dict | None = None,
):
    ...
    return await graph.ainvoke({"messages": messages}, config=run_config or {})
```

- [ ] **Step 3: Update `RawCodeWithReviseStrategy.run()` to pass `run_config`**

Current `raw_code_with_revise.py` `run()`:
```python
    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL, renderer=None) -> RawRunResult:
        draft_state = await run_draft(prompt, model=model)
        draft_messages = draft_state["messages"]
        revision_state = await run_revision(model, message_history=draft_messages, force_rerender=True)
```

Replace with:
```python
    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL, renderer=None) -> RawRunResult:
        run_config = self._run_config
        draft_state = await run_draft(prompt, model=model, run_config=run_config)
        draft_messages = draft_state["messages"]
        revision_state = await run_revision(model, message_history=draft_messages, force_rerender=True, run_config=run_config)
```

- [ ] **Step 4: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_agent_e2e.py -x
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add geometry_diagrams/strategies/stages.py \
        geometry_diagrams/strategies/raw_code_with_revise.py
git commit -m "feat: wire LangFuse run_config through stages.py helpers"
```

---

## Task 5: Wire eval harness `_run_query_phase`

`_run_query_phase` in `evals/run.py` is a standalone function (not a strategy method), so it calls `get_callback_handler()` directly.

**Files:**
- Modify: `evals/run.py`

- [ ] **Step 1: Import and wire `get_callback_handler` in `_run_query_phase`**

At the top of `_run_query_phase` (around line 112), the function starts:
```python
async def _run_query_phase(
    queries: list[dict],
    sym: dict,
    model: str,
) -> list[dict[str, Any]]:
    ...
    results: list[dict[str, Any]] = []

    for query_def in queries:
```

Add two lines immediately before the `for` loop (after `results: list[dict[str, Any]] = []`):
```python
    from geometry_diagrams.util.tracing import get_callback_handler
    _h = get_callback_handler()
    _qconfig: dict = {"callbacks": [_h]} if _h else {}
```

Then find the `graph.ainvoke` call inside the loop (around line 170):
```python
            state = await graph.ainvoke({"messages": [("user", context_msg)]})
```

Replace it with:
```python
            state = await graph.ainvoke({"messages": [("user", context_msg)]}, config=_qconfig)
```

- [ ] **Step 2: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_agent_e2e.py -x
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add evals/run.py
git commit -m "feat: wire LangFuse tracing into eval harness query phase"
```

---

## Task 6: Add optional `langfuse` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the `tracing` dependency group**

In `pyproject.toml`, find the `[dependency-groups]` section:
```toml
[dependency-groups]
dev = [
    "mlcroissant>=1.1.0",
    ...
]
```

Add the `tracing` group after `dev`:
```toml
[dependency-groups]
dev = [
    "mlcroissant>=1.1.0",
    "pymupdf>=1.27.2.3",
    "pytest>=9.0.3",
    "pytest-asyncio>=0.24",
]
tracing = ["langfuse>=2.0"]
```

- [ ] **Step 2: Verify the toml parses correctly**

```bash
uv sync --dry-run
```

Expected: no errors (langfuse not installed yet since we're not adding `--group tracing`).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add optional langfuse tracing dependency group"
```

---

## Task 7: Smoke test with a real LangFuse instance

This task requires a running LangFuse instance and valid credentials in `.env`.

- [ ] **Step 1: Set env vars in `.env`**

Add to `.env` (do not commit):
```
LANGFUSE_HOST=https://your-langfuse-host
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

- [ ] **Step 2: Install the langfuse package**

```bash
uv sync --group tracing
```

- [ ] **Step 3: Run one eval scenario**

```bash
source .venv/bin/activate
python -m evals.run \
  --scenarios evals/scenarios.yaml \
  --strategies recipe \
  --model anthropic:claude-sonnet-4-6 \
  --repeats 1 \
  --renderer svg \
  --scenario-limit 1
```

Expected: the scenario runs and a trace appears in the LangFuse UI showing a graph run with `select_recipes`, `generate_dsl`, and `run_recipe_pipeline` spans.

- [ ] **Step 4: Verify trace structure in LangFuse UI**

Open LangFuse and confirm:
- One trace per scenario run
- Three top-level spans matching the graph node names
- LLM call spans nested under `select_recipes` and `generate_dsl` with token counts visible
- No errors in the `run_recipe_pipeline` span (it has no LLM calls)

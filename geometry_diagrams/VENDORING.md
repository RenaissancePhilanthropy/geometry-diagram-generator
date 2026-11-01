# Vendoring `geometry_diagrams`

A quick guide for developers who want to copy this package into their own project.

## Installation

**Recommended: install as a git dependency**

```bash
# uv
uv add git+https://github.com/RenaissancePhilanthropy/geometry-diagram-generator

# pip
pip install git+https://github.com/RenaissancePhilanthropy/geometry-diagram-generator
```

**Alternative: manual copy (vendor)**

If you prefer to copy the source directly rather than using pip/uv, copy the entire `geometry_diagrams/` directory into your project. All internal imports are relative so it works under any name or nesting depth. You are responsible for adding the runtime dependencies listed below to your own project.

## Runtime dependencies

**Core (always needed):**

| Package | Notes |
|---|---|
| `httpx` | HTTP client for the TikZ renderer service |
| `sympy` | Source of truth for all geometric computation |
| `pyyaml` | Recipe catalog and config parsing |
| `pydantic` | IR schema and config dataclass |
| `langchain` + `langchain-core` | LLM orchestration base |
| `langgraph` | Strategy state graphs and retry loops |

**Provider package** (import one, chosen lazily by model prefix in `strategies/llm.py`):

| Package | When needed |
|---|---|
| `langchain-anthropic` | `anthropic:*` models |
| `langchain-openai` | `openai:*` models (extra: `openai`) |
| `langchain-google-genai` | `google:*` models (extra: `google`) |

**Optional:**

| Package | When needed |
|---|---|
| `langfuse` | LangFuse tracing (only when `LANGFUSE_BASE_URL` is set) |
| `cairosvg` | `util/llm_judge.py` only — eval/judge utility, not the main render path |
| `smolagents`, `numpy`, `mpmath`, `matplotlib` | Declared core dependencies: the pydsl sandbox, the conic kernel, curve measures and SVG label metrics import them |

**Not needed** (repo scaffolding only, not imported by the module):
- `uvicorn`, `starlette`, `python-dotenv` — web server for the demo app only (extra: `server`)
- `fastapi` — used only inside the renderer container

## Renderer choice

This is the key decision for new consumers.

**`renderer="svg"` — recommended for new consumers**

In-process rendering, zero infrastructure. No Docker, no external service.

```python
GeometryConfig(renderer="svg")
# or set env var: GEOMETRY_RENDERER=svg
```

**`renderer="tikz"` — current default**

Requires the TikZ renderer Docker container running at `renderer_url` (60 s client timeout). Produces higher-fidelity output but requires Docker and the renderer service. Build the image from the repository root (`docker build -f renderer/Dockerfile -t tikz-renderer .`); the container runs `lualatex` with `--no-shell-escape` as a non-root user and caps request sizes, so after rebuilding it, verify that a render still works.

```
# Default URL: http://localhost:8001
# Override with: TIKZ_RENDERER_URL=http://your-host:8001
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GEOMETRY_RENDERER` or `RENDERER` | `tikz` | Renderer backend: `tikz` or `svg` |
| `GEOMETRY_STRATEGY` | `recipe` | Strategy: `recipe`, `python_full` or `structured` (`main.py` also accepts the raw strategies and falls back to `STRATEGY`, default `raw_code`) |
| `GEOMETRY_MODEL` or `MODEL` | `anthropic:claude-sonnet-4-6` | LLM model ID |
| `GEOMETRY_SELECTOR_MODEL` | `anthropic:claude-haiku-4-5-20251001` | Model for recipe selection |
| `TIKZ_RENDERER_URL` | `http://localhost:8001` | TikZ renderer service URL |
| `DIAGRAM_FONT_FAMILY` | `NunitoSans` | Font family name |
| `DIAGRAM_EMBED_FONTS` | off | `1`/`true`/`yes`/`on` (any case) embeds fonts in SVG output |
| `DIAGRAM_DEBUG_SHOW_IMPLICIT` | off | Same boolean forms; SVG renderer also emits hidden `data-implicit` elements (inspector tooling) |
| `GEOMETRY_FEATURES` | empty | Comma-separated opt-in feature groups (`solids`, `tilted_ellipses`) |
| `GEOMETRY_EDIT_MODE` | `search_replace` | python_full edit format: `full_rewrite`, `patch`, `search_replace`, `hashline` or `line_number`; any other value raises `ValueError` |
| `GEOMETRY_HASH_ALGORITHM` | `blake2s` | Line hash for `hashline` edits: `blake2s` or `xxhash` |
| `GEOMETRY_SANDBOX_TIMEOUT_SECONDS` | `2.5` | python_full script time limit; must be finite and > 0 |
| `MATHTEXT_FONTSET` | `cm` | matplotlib mathtext font set for LaTeX-style labels in SVG output (read at import) |
| `ANTHROPIC_API_KEY` | — | Provider API key (read by LangChain SDK) |
| `OPENAI_API_KEY` | — | Provider API key (read by LangChain SDK) |
| `GOOGLE_API_KEY` | — | Provider API key (read by LangChain SDK) |
| `LANGFUSE_BASE_URL` | — | LangFuse tracing (optional) |
| `LANGFUSE_PUBLIC_KEY` | — | LangFuse tracing (optional) |
| `LANGFUSE_SECRET_KEY` | — | LangFuse tracing (optional) |

## Public API

Full docstrings are in `__init__.py`. Summary:

| Symbol | Description |
|---|---|
| `render_geometry_diagram(prompt, *, config=None, renderer=None, strategy=None, model=None, selector_model=None, renderer_url=None, font_family=None, previous_dsl=None, previous_script=None, previous_ir=None, run_config=None, callbacks=None, extra_instructions=None)` | Main async entry point; at most one `previous_*`, matching the strategy |
| `render_geometry_diagram_sync(prompt, ...)` | Sync wrapper — same keyword args as above (raises if called inside a running event loop) |
| `edit_geometry_diagram(prompt, previous_dsl=None, *, previous_script=None, previous_ir=None, ...)` | Async convenience wrapper for iterative edits; exactly one of `previous_dsl` (recipe), `previous_script` (python_full) or `previous_ir` (structured) is required. It takes no `strategy` argument: the strategy comes from `config` / `GEOMETRY_STRATEGY` |
| `edit_geometry_diagram_sync(prompt, previous_dsl=None, **kwargs)` | Sync version of the above |
| `render_diagram` | LangChain `@tool`, reads config from environment; returns JSON with `svg`, `tikz`, `dsl`, `input_tokens`, `output_tokens`, `script`, `warnings`, `cost_usd` (or `{"error": ...}`) |
| `query_diagram`, `query_geometry_diagram` | Query a diagram's geometry from its `dsl` (no LLM call) |
| `select_recipes`, `select_recipes_sync`, `RecipeSelectionResult` | Run only the cheap recipe-selection step |
| `GeometryConfig` / `GeometryConfig.from_env()` | Config dataclass |
| `DiagramResult` | Return type: `svg`, `tikz`, `input_tokens`, `output_tokens`, `dsl`, `diagram_ir`, `recipes`, `retry_count`, `script`, `cost_usd`, `warnings` |

`extra_instructions` (also `GeometryConfig.extra_instructions`) is application text appended to the generation system prompt as an "Additional instructions from the application" section, for every strategy; it is not applied to the recipe selector.

`DiagramResult` fields:

| Field | Type | Description |
|---|---|---|
| `svg` | `str` | Rendered SVG markup |
| `tikz` | `str` | Generated TikZ/LaTeX source; empty string when `renderer="svg"` |
| `input_tokens` | `int` | LLM input tokens consumed |
| `output_tokens` | `int` | LLM output tokens consumed |
| `dsl` | `dict \| None` | Recipe strategy only: DSL representation (JSON-serializable); pass as `previous_dsl` to edit |
| `diagram_ir` | `dict \| None` | Compiled intermediate representation; pass as `previous_ir` to edit under `structured` |
| `recipes` | `list[str] \| None` | Recipe strategy only: recipe names selected during construction |
| `retry_count` | `int` | Generation attempts made, successful one included (a first-try success is 1), for every strategy |
| `script` | `str \| None` | python_full only: the pydsl script; pass as `previous_script` to edit |
| `cost_usd` | `float \| None` | Provider-reported USD cost summed over attempts; `None` = not reported (the recipe strategy never reports) |
| `warnings` | `list[str]` | Non-fatal pipeline notes from the final run (renderer warnings, failed `prefer` checks, ...) |

## Integration with parent-app tracing and cost tracking

Pass a LangChain callback handler via `callbacks` for lightweight token tracking, or use `run_config` for richer tracing integrations such as LangFuse.

```python
from langchain_community.callbacks import get_openai_callback
from geometry_diagrams import render_geometry_diagram_sync

# Token tracking via a LangChain callback
with get_openai_callback() as cb:
    result = render_geometry_diagram_sync(
        "Draw a right triangle with legs 3 and 4",
        callbacks=[cb],
    )
print(f"Tokens used: {cb.total_tokens}")

# Richer tracing via run_config (e.g. LangFuse)
result = render_geometry_diagram_sync(
    "Draw a right triangle",
    run_config={"callbacks": [langfuse_handler], "metadata": {"session_id": "abc"}},
)
```

Both `callbacks` and `run_config` are forwarded directly to the underlying LangGraph execution. They are independent — you can use either or both.

## Iterative editing

Use `edit_geometry_diagram` / `edit_geometry_diagram_sync` to refine an existing diagram while preserving all properties you did not mention. Pass the `dsl` field from a previous result as `previous_dsl`.

```python
from geometry_diagrams import render_geometry_diagram_sync, edit_geometry_diagram_sync

# First render
result = render_geometry_diagram_sync("Draw an equilateral triangle")
print(result.svg)

# Edit preserving all unrequested properties
result2 = edit_geometry_diagram_sync(
    "Make it isosceles with the apex angle 30 degrees",
    previous_dsl=result.dsl,
)
print(result2.svg)

# result2.dsl can be saved and reused for further edits
```

`result.dsl` is a plain dict (JSON-serializable) — it can be stored in a database or checkpoint and passed back to `edit_geometry_diagram` in a later session. It is `None` if the diagram failed to compile.

## Quick start (SVG, no Docker needed)

```python
import asyncio
from geometry_diagrams import render_geometry_diagram, GeometryConfig

result = asyncio.run(
    render_geometry_diagram(
        "Draw a right triangle with legs 3 and 4",
        config=GeometryConfig(renderer="svg"),
    )
)
print(result.svg[:200])
```

# Vendoring `geometry_diagrams`

A quick guide for developers who want to copy this package into their own project.

## How to vendor

1. Copy the entire `geometry_diagrams/` directory into your host project.
2. All internal imports are relative, so the package works under any name or nesting depth:
   - `myapp/geometry_diagrams/`
   - `myapp/vendor/geom/`
   - etc.
3. If you rename the directory, update your import statements to match the new name (`import myapp.geometry_diagrams` → `import myapp.vendor.geom`). The internal imports inside the package will still work unchanged.

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
| `langchain-openai` | `openai:*` models |
| `langchain-google-genai` | `google:*` models |

**Optional:**

| Package | When needed |
|---|---|
| `langfuse` | LangFuse tracing (only when `LANGFUSE_BASE_URL` is set) |
| `cairosvg` | `util/llm_judge.py` only — eval/judge utility, not the main render path |

**Not needed** (repo scaffolding only, not imported by the module):
- `uvicorn`, `starlette`, `fastapi` — web server for the demo app only
- `matplotlib` — not imported anywhere in the module

## Renderer choice

This is the key decision for new consumers.

**`renderer="svg"` — recommended for new consumers**

In-process rendering, zero infrastructure. No Docker, no external service.

```python
GeometryConfig(renderer="svg")
# or set env var: GEOMETRY_RENDERER=svg
```

**`renderer="tikz"` — current default**

Requires the TikZ renderer Docker container running at `renderer_url`. Produces higher-fidelity output but requires Docker and the renderer service.

```
# Default URL: http://localhost:8001
# Override with: TIKZ_RENDERER_URL=http://your-host:8001
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GEOMETRY_RENDERER` or `RENDERER` | `tikz` | Renderer backend: `tikz` or `svg` |
| `GEOMETRY_MODEL` or `MODEL` | `anthropic:claude-sonnet-4-6` | LLM model ID |
| `GEOMETRY_SELECTOR_MODEL` | `anthropic:claude-haiku-4-5-20251001` | Model for recipe selection |
| `TIKZ_RENDERER_URL` | `http://localhost:8001` | TikZ renderer service URL |
| `DIAGRAM_FONT_FAMILY` | `NunitoSans` | Font family name |
| `DIAGRAM_EMBED_FONTS` | — | Set to `1` or `true` to embed fonts in SVG output |
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
| `render_geometry_diagram(prompt, *, config=None, ...)` | Main async entry point |
| `render_geometry_diagram_sync(prompt, ...)` | Sync wrapper (raises if called inside a running event loop) |
| `render_diagram` | LangChain `@tool`, reads config from environment |
| `GeometryConfig` / `GeometryConfig.from_env()` | Config dataclass |
| `DiagramResult` | Return type: `svg`, `tikz`, `input_tokens`, `output_tokens` |

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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install Python dependencies
uv sync

# Activate the virtual environment (required before running Python commands)
source .venv/bin/activate

# Run tests
.venv/bin/python -m pytest tests/

# Run a single test file
.venv/bin/python -m pytest tests/test_compile_defs.py -v

# Run evals
uv run python -m evals.run --scenarios evals/scenarios.yaml --strategies structured --model anthropic:claude-sonnet-4-6 --repeats 3 --output evals/results
```

**Note:** The TikZ renderer container (`docker run -p 8001:8001 tikz-renderer`), the main server (`uv run python -m uvicorn main:app`), the UI dev server (`cd demo-ui && pnpm dev`), and the eval viewer (see below) are typically managed by the user, not started by Claude Code.

```bash
# Start the eval viewer backend (port 8002; requires renderer container on port 8001 for re-rendering)
uv run python evals/eval_viewer.py

# Start the eval viewer frontend dev server (proxies /api to localhost:8002)
cd eval-viewer-ui && pnpm dev
```

## Architecture

This project generates geometric diagrams as SVGs by having an LLM produce geometry descriptions that compile down to TikZ/LaTeX.

### Pipeline

```
User Request (for "structured" / "recipe" strategy)
    → Strategy (LangGraph StateGraph)
    → DiagramIR (Pydantic schema)
    → SymPy geometry objects (ir/to_sympy.py)
    → Geometric validation (ir/checks.py)
    → TikZ code (ir/to_tikz.py)
    → LaTeX → SVG (renderer Docker container via HTTP)
```

Other strategies may skip the IR and go straight to TikZ.

### IR Layer (`ir/`)

The Intermediate Representation is the central abstraction:

- **`ir.py`**: Pydantic models for `DiagramIR` — contains `Canvas`, `DefStmt` (20+ geometric definition types: points, segments, circles, triangles, polygons, intersections, etc.), `Check` (geometric invariants), and `RenderOp` (drawing commands).
- **`to_sympy.py`**: Compiles `DiagramIR` definitions into SymPy geometry objects by resolving the definition DAG. Handles forward references and intersection disambiguation via `pick` rules.
- **`to_tikz.py`**: Converts compiled SymPy objects to TikZ code (`\tkzDefPoint`, `\tkzDrawSegment`, etc.). Computes canvas bounds and helper points automatically.
- **`to_svg.py`**: Direct SVG rendering path — converts compiled SymPy objects to SVG without going through TikZ/LaTeX.
- **`checks.py`**: Validates geometric properties (distance, collinearity, parallelism, perpendicularity, angle equality, tangency, etc.) against compiled SymPy objects with tolerance-based floating-point comparison.
- **`queries.py`**: Query interface for extracting geometric facts from compiled SymPy objects.
- **`render_util.py`**: Shared rendering utilities used by both `to_tikz.py` and `to_svg.py`.
- **`renderer.py`**: Dispatch layer that selects the appropriate rendering backend.

### Strategies (`strategies/`)

Multiple LLM-based approaches implementing `SubstanceStrategy` base class (`base.py`). All strategies use LangGraph and LangChain for LLM orchestration.

- **`raw_code.py`**: LLM generates TikZ directly via a ReAct agent (`create_react_agent`).
- **`raw_code_with_revise.py`**: Raw TikZ with a revision loop on validation failure.
- **`raw_svg.py`**: LLM generates SVG directly.
- **`raw_svg_with_revise.py`**: Raw SVG with a revision loop.
- **`structured.py`**: Full IR pipeline — LLM produces `DiagramIR` JSON → compile → check → render. Uses a `StateGraph` retry loop (up to `MAX_RETRIES=3`). This is more robust and easier to debug than raw code generation.
- **`recipe.py`**: Strategy that uses the recipe DSL to specify constructions. Uses a two-node `StateGraph`: selector (cheap model picks relevant recipes) → DSL generator → lowering → IR pipeline. Currently the main strategy to use.

**`llm.py`**: Model factory — maps `"anthropic:MODEL"` / `"openai:MODEL"` / `"google:MODEL"` IDs to LangChain chat models (`ChatAnthropic`, `ChatOpenAI`, `ChatGoogleGenerativeAI`). Provides `get_chat_model()`, `extract_usage()`, `make_system_message()`, and `is_gemini_model()`.

**`stages.py`**: Shared rendering tool helpers used by raw strategies.

Prompt templates are split across `instructions_structured.py`, `instructions_recipe.py`, `instructions_tikz.py`, and related files.

### Renderer (`renderer/`)

A Docker container running a FastAPI server (port 8001) that compiles LaTeX to SVG:
- `POST /render` accepts LaTeX, runs `lualatex` → `dvisvgm`, returns SVG.
- Uses `tkz-euclide` and `tkz-elements` TeX packages for geometric drawing primitives.
- The HTTP client is `util/tikz_renderer.py`.

### Utilities (`util/`)

- **`tikz_analysis.py`**: Extracts coordinates from TikZ code and validates geometric properties.
- **`svg_checks.py`**: Validates rendered SVG output properties.
- **`llm_judge.py`**: LLM-based quality evaluation of rendered diagrams.
- **`message_helpers.py`**: Helpers for extracting SVG/TikZ/tool content from LangChain message lists.

### Evals (`evals/`)

Benchmark harness comparing strategies across tiered geometry scenarios (Basic/Intermediate/Advanced defined in `evals/scenarios.yaml`). `evals/run.py` runs scenarios with multiple repeats, collecting success rates, token usage, latency, and LLM judge scores. Results are written as JSONL to `evals/results/` (gitignored). `scenarios.py` provides programmatic scenario loading; `scenarios_query.yaml` defines query-style eval scenarios.

### Recipe (`recipe/`)

A DSL for declaratively specifying geometry constructions:

- **`dsl.py`**: Defines the recipe DSL syntax and parsing.
- **`catalog.py`**: Library of named geometry construction recipes.
- **`lower.py`**: Lowers recipe DSL constructions down to `DiagramIR` for compilation and rendering.
- **`expressions.py`**: Expression evaluation for recipe DSL parameters.
- **`solve.py`**: Constraint solver used during recipe lowering.

### Docs (`docs/`)

- **`geometry-dsl-spec.md`**: Formal specification of the geometry DSL/IR schema.
- **`gen_examples.py`**: Script to regenerate example SVGs in `docs/examples/`.
- **`examples/`**: Pre-rendered SVG examples used for documentation.

## Key Design Notes

- **Focus on test-driven development**: The project is structured around unit tests for each component and end-to-end tests for the full pipeline. This ensures reliability and makes it easier to iterate on strategies. Writing tests first for new features or bug fixes is highly encouraged.
- **SymPy is the source of truth** for geometric computation. TikZ code is generated from SymPy objects, not from the LLM's coordinate guesses.
- **Checks are assertions** about the compiled geometry — if an LLM-generated `DiagramIR` fails checks, the strategy retries via the LangGraph `StateGraph` retry loop.
- **The renderer container must be running** for any code path that produces SVG output.
- The project uses **LangGraph** and **LangChain** (`langchain-anthropic`, `langchain-openai`, `langchain-google-genai`) for LLM orchestration. Inner retry loops use `StateGraph`; conversational agents use `create_react_agent`.
- API keys go in `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).

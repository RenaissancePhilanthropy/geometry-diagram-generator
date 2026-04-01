# geometry-diagram-generator

Generate geometric diagrams as SVGs from natural language using an LLM pipeline. The LLM describes geometry in a structured intermediate representation (IR); SymPy does the math; TikZ/LaTeX renders the result.

## Examples

<table>
<tr>
<td align="center"><img src="docs/examples/right_triangle.svg" width="220"/><br/>Right triangle</td>
<td align="center"><img src="docs/examples/circumscribed_circle.svg" width="220"/><br/>Circumscribed circle</td>
<td align="center"><img src="docs/examples/euler_line.svg" width="220"/><br/>Euler line</td>
</tr>
</table>

## How it works

```
User request
  → LLM (strategy)
  → DiagramIR (Pydantic schema)
  → SymPy geometry objects       ← source of truth for coordinates
  → Geometric validation
  → TikZ code
  → lualatex (with tkz-euclide and tkz-elements) + dvisvgm (Docker)
  → SVG
```

The LLM avoids picking coordinates directly. It describes *what* to construct (midpoints, intersections, circumcenters, etc.); the compiler resolves positions from SymPy.

## Strategies

| Strategy | Description |
|---|---|
| `structured` | Full IR pipeline — most robust; LLM outputs DiagramIR JSON |
| `raw_code` | LLM generates TikZ directly |
| `raw_code_with_revise` | Raw TikZ with a revision loop on failure |
| `plan_and_code` | Two-stage: planning agent sets coordinates, then generates TikZ |
| `recipe` | Uses predefined YAML templates for common constructions |

Set the active strategy via `STRATEGY` env var (default: `structured`).

## Quick start

**Prerequisites:** Python 3.11+, [uv](https://github.com/astral-sh/uv), Docker, Node.js + pnpm

```bash
# 1. Install dependencies
uv sync

# 2. Set API keys
cp .env.example .env   # then fill in ANTHROPIC_API_KEY

# 3. Build and start the renderer (LaTeX → SVG)
docker build -t tikz-renderer renderer/
docker run -p 8001:8001 tikz-renderer

# 4. Start the server
uv run python -m uvicorn main:app

# 5. Start the UI
cd demo-ui && pnpm install && pnpm dev
# Open http://localhost:5173
```

## Development

```bash
# Run tests
uv run python -m pytest tests/

# Run evals
uv run python -m evals.run \
  --scenarios evals/scenarios.yaml \
  --strategies structured \
  --model anthropic:claude-sonnet-4-6 \
  --repeats 3 \
  --output evals/results

# Start eval viewer
uv run python evals/eval_viewer.py   # backend on :8002
cd eval-viewer-ui && pnpm dev        # frontend proxies /api to :8002
```

## Project layout

```
ir/               Intermediate representation: schema, SymPy compiler, TikZ emitter, checks
strategies/       LLM strategy implementations
renderer/         Docker container: FastAPI server wrapping lualatex + dvisvgm
evals/            Benchmark harness, scenarios, result viewer
demo-ui/          Vite frontend (served from / by main.py)
eval-viewer-ui/   Vite frontend for browsing eval results
util/             Shared utilities (renderer client, SVG checks, LLM judge)
recipe/           YAML recipe templates for common constructions
docs/             DSL specification (geometry-dsl-spec.md)
tests/            Unit and integration tests
```

## Architecture notes

- See [CLAUDE.md](CLAUDE.md) for the full pipeline description and design rationale.
- See [docs/geometry-dsl-spec.md](docs/geometry-dsl-spec.md) for the IR schema specification.
- The renderer container exposes `POST /render` (TikZ → SVG) and `GET /health` on port 8001.
- `pydantic-ai` is used for LLM agent orchestration with Anthropic and OpenAI backends.

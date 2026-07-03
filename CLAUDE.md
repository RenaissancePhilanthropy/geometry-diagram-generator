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

# GenExam dry run — end-to-end test against real LLM, no database writes
# macOS: prefix with DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib (for cairosvg/libcairo)

# Single prompt — verbose section output by default
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m benchmark.genexam.dry_run --prompt-id Mathematics_72

# Random sample with judge
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m benchmark.genexam.dry_run --sample 10 --seed 42

# Verbose section output for a batch run
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m benchmark.genexam.dry_run --sample 5 --verbose

# Generation only (no AI judge), with outer retry on failure
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m benchmark.genexam.dry_run --prompt-id Mathematics_15 --no-judge --gen-retries 2

# Filter by difficulty tier (1=easy, 2=medium, 3=hard) before sampling
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m benchmark.genexam.dry_run --sample 5 --tier 1 --seed 0

# Run all HIGH + MEDIUM-cartesian prompts (91 total), no judge, high concurrency
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m benchmark.genexam.dry_run --all --no-judge --concurrency 8

# Regenerate benchmark/definitions/bench_genexam.yaml from the source JSONL
.venv/bin/python -m benchmark.genexam.filter_genexam
```

Key dry-run flags: `--model` (generation model, default `anthropic:claude-sonnet-4-6`), `--judge-model`, `--renderer svg|tikz` (svg=no Docker required), `--concurrency N`, `--out-dir` (SVGs + `dry_run.jsonl`, default `/tmp/bench_dry_run`), `--gen-retries N` (outer retry loop on generation failure). Output for single-prompt runs uses verbose section headers (Prompt / Generation / AI Judge / Score); use `--verbose` to enable that format for batch runs too.

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
User Request (for "structured" strategy)
    → Strategy (LLM agent)
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

Multiple LLM-based approaches implementing `SubstanceStrategy` base class (`base.py`):

- **`raw_code.py`**: LLM generates TikZ directly.
- **`raw_code_with_revise.py`**: Raw TikZ with a revision loop on validation failure.
- **`plan_and_code.py`**: Two-stage: planning sub-agent determines coordinates, then generates TikZ.
- **`structured.py`**: Full IR pipeline — LLM produces `DiagramIR` JSON → compile → check → render. This is more robust and easier to debug than raw code generation. `structured_plus_refine.py` and `structured_two_phase.py` are variants with additional refinement steps.
- **`recipe.py`**: Strategy that uses the recipe DSL to specify constructions. Currently the main strategy to use.

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

### Evals (`evals/`)

Benchmark harness comparing strategies across tiered geometry scenarios (Basic/Intermediate/Advanced defined in `evals/scenarios.yaml`). `evals/run.py` runs scenarios with multiple repeats, collecting success rates, token usage, latency, and LLM judge scores. Results are written as JSONL to `evals/results/` (gitignored). `scenarios.py` provides programmatic scenario loading; `scenarios_query.yaml` defines query-style eval scenarios.

### Benchmark (`benchmark/`)

A standalone benchmarking system with persistent storage and an HTTP API:

- **`db.py`**: Database layer for storing and querying benchmark run results.
- **`server.py`**: FastAPI HTTP server exposing benchmark data and triggers.
- **`models.py`**: Pydantic models (`BenchmarkDefinition`, `BenchmarkPrompt`, `RubricItem`) shared across the benchmark system. `RubricItem` has an optional `weight` field; `BenchmarkPrompt` has a `metadata` dict.
- **`ai_judge.py`**: LLM-based judge for scoring benchmark outputs.
- **`irr.py`**: Inter-rater reliability computation for human annotation agreement.
- **`import_run.py`**: Imports eval run results into the benchmark database.
- **`definitions/bench_genexam.yaml`**: Pre-built benchmark definition from the GenExam-Math dataset (91 prompts: 77 HIGH-relevance + 14 MEDIUM-cartesian). Regenerate with `python -m benchmark.genexam.filter_genexam`.

#### `benchmark/genexam/`

GenExam-Math integration:

- **`Mathematics.jsonl`**: Source dataset (geometry problems with scoring points).
- **`filter_genexam.py`**: Filters problems by geometric relevance and emits `bench_genexam.yaml`. Relevance tiers: HIGH (77 problems), MEDIUM-cartesian (14), MEDIUM-3d (11), LOW (excluded). Weights come from `scoring_points[].score`; tags from difficulty/img_type/taxonomy.
- **`dry_run.py`**: End-to-end test harness — runs RecipeStrategy against benchmark prompts with real LLM calls, no database writes. Outputs per-prompt SVGs and `dry_run.jsonl`. See Commands section for usage.

Note: `benchmark/` and `evals/` serve related but distinct purposes — `evals/` is project-specific LLM eval harness (scenarios, repeats, judge scoring), while `benchmark/` is a persistent database-backed system for tracking results over time, potentially across multiple projects or pipelines.

### Recipe (`recipe/`)

A DSL for declaratively specifying geometry constructions:

- **`dsl.py`**: Defines the recipe DSL syntax and parsing.
- **`catalog.py`**: Library of named geometry construction recipes.
- **`lower.py`**: Lowers recipe DSL constructions down to `DiagramIR` for compilation and rendering.
- **`expressions.py`**: Expression evaluation for recipe DSL parameters.
- **`solve.py`**: Constraint solver used during recipe lowering.

### Benchmark UI (`benchmark-ui/`)

A Vite-based frontend for the benchmark system. Connects to `benchmark/server.py` and provides views for annotation queues, IRR reports, and run lists. Run with `cd benchmark-ui && pnpm dev`.

### Docs (`docs/`)

- **`geometry-dsl-spec.md`**: Formal specification of the geometry DSL/IR schema.
- **`gen_examples.py`**: Script to regenerate example SVGs in `docs/examples/`.
- **`examples/`**: Pre-rendered SVG examples used for documentation.
- **`human_study_protocol.md`**: Pre-registered protocol for the human-correlation rating study.

### Interpretability (`interp/`)

Mechanistic-interpretability probe of how an LLM (Qwen2.5) represents geometric relationships while writing a GeoGen construction. Standalone from the main pipeline; has its own `requirements.txt` and offline smoke tests. See `interp/README.md`, `PLAN.md`, `METHODOLOGY.md`, `RESULTS.md`, and `CONFIDENCE.md`.

- **`grade.py`** (Phase 0): render-free grader — completion → parse → validate → lower → compile → check.
- **`capability_check.py`** (Phase 0): prompts the model on benchmark prompts and reports valid-construction rate; supports few-shot exemplars (`--few-shot none|3|all|relevant:K`).
- **`capture.py`** (Phase 1): generate + forward-pass, saving the residual stream per completion token plus ground-truth geometry. `--keep-positions entities` stores only entity-name tokens to keep datasets small.
- **`geometry_labels.py`** (Phase 1–2): extracts spatial ground truth (entity→relation, point coords, check facts) from a construction — the bridge for non-trivial probes.
- **`probe.py`** (Phase 2): per-layer linear probes → decodability-vs-layer.
- **`patch.py`** (Phase 3): activation-patching harness for causal tests.
- **`confidence.py`**: fixed-slot confidence-token experiment (see `CONFIDENCE.md`).
- **`setup_vast.sh`**: bootstraps a rented CUDA box. Heavy runs need a GPU — Apple Silicon/MPS lacks FlashAttention, so long few-shot prompts OOM.

### Paper (`paper/`)

LaTeX source for the **GeoGenBench** NeurIPS Datasets & Benchmarks paper. Naming: **GeoGen** = the methodology/pipeline (text → TikZ → SymPy → automatic verification); **GeoGenBench** = the released benchmark (801 prompts with machine-checkable property lists). `geogenbench.tex` is the main file; sections in `sections/`, appendices in `appendices/`, figures symlink to `docs/figures/`. Build with the `Makefile`. `scripts/` holds figure-refresh and supplementary-bundle helpers.

### Curriculum (`curriculum/`)

Pipeline that extracts geometry curriculum structure from Carnegie textbook PDFs and generates student-style prompts for the eval suite: `convert_pdfs.py` (PDF → Markdown via marker-pdf in its own `.marker-venv`) → `extract_curriculum.py` (Markdown → JSON, Claude Sonnet) → `generate_prompts.py` (JSON → scenario YAML). `to_benchmark.py` emits benchmark definitions. See `curriculum/README.md`.

### Human study (`evals/human_study/`)

Human-correlation rating study for the paper: raters judge whether they agree with the auto-verifier's `pass`/`soft_pass`/`fail` on (prompt, diagram) pairs. `serve.py` + `viewer.html` present items; responses saved as `responses_*.csv`; `compute_kappa.py` computes inter-rater agreement (Cohen's kappa). `sample_human_study.py` builds the sample. See its `README.md` and `docs/human_study_protocol.md`.

### Slides (`slides/`)

Self-contained onboarding presentation (`onboarding.html`) with `SPEAKER_NOTES.md` for new contributors.

### Interpretability (`interp/`)

A research sub-project probing **where — and whether — the model represents spatial reasoning and its own correctness (metacognition)** in the residual stream, using the geometry-construction task as the probe domain. It has its **own venv** (`interp/.venv`, separate from the repo's `.venv`) and `requirements.txt`. Linear probes and analyses run **offline on CPU**; activation **capture is a GPU job** (typically a rented cloud box — see `setup_vast.sh`). Captured activations live in `interp/activations/` (gitignored, multi-GB).

Phased pipeline:
- **`grade.py`**: render-free auto-grader — runs a model completion through `parse → validate → lower → compile → check` and returns pass/fail + furthest stage. The ground-truth correctness signal.
- **`capability_check.py`** (Phase 0 gate): can the model produce valid constructions? Prompts a local HF model, grades each, reports the valid-construction rate. `load_model` handles bf16 / AWQ / 4-bit; `build_messages` mirrors RecipeStrategy's prompt.
- **`capture.py`** (Phase 1): generate + grade + one forward pass with `output_hidden_states`, saving the residual stream (float16 `.npz` + `meta.jsonl`) at chosen token positions. Key flags: `--keep-positions entities`, `--elicit-confidence` (single-turn "Confidence: N"), `--confidence-followup` (**two-turn**: generate the construction cleanly, then elicit confidence separately — avoids the single-turn instruction truncating the JSON), `--no-think` (disable hybrid-reasoner `<think>`, e.g. GLM-4.x).
- **`geometry_labels.py`**: extracts ground-truth spatial facts (entity relations, point coords, vertex angles) from the compiled construction, for non-trivial probe targets.
- **`probe.py`** (Phase 2): per-layer linear probes (StandardScaler → PCA → LogReg/Ridge) with a **base-prompt-grouped** train/test split and a token-identity baseline. Labelers: `relation`, `entity_relation`, `point_coord`, `angle`, plus the metacognition set `correctness` (last entity token), `correctness_conf` (the fixed confidence **decision** token), `correctness_conf_digit`.
- **`patch.py`** (Phase 3): activation patching / logit-difference recovery for causal claims.
- **`confidence.py`**: confidence elicitation (single- and two-turn) + read-site location — `confidence_read_positions` returns the **decision token** (the `:`/space that generates the number, content-neutral) and the digit tokens.
- **`analysis/`**: `confidence_vs_difficulty.py` (difficulty + within-prompt + surface controls; `--read last|first|conf|conf_digit`), `verbalized_vs_internal.py` (stated vs internal confidence), plus `ordering.py` / `consistency.py` / `coherent_map.py`.

Docs: `METHODOLOGY.md` (protocol), `RESULTS.md` (spatial-decodability curves), `CONFIDENCE.md` (the metacognition sub-study + GPU runbook + decision rules), `PLAN.md`, `PROPOSAL.md`. Offline tests run as scripts, e.g. `interp/.venv/bin/python interp/test_confidence.py`.

## Key Design Notes

- **Focus on test-driven development**: The project is structured around unit tests for each component and end-to-end tests for the full pipeline. This ensures reliability and makes it easier to iterate on strategies. Writing tests first for new features or bug fixes is highly encouraged.
- **SymPy is the source of truth** for geometric computation. TikZ code is generated from SymPy objects, not from the LLM's coordinate guesses.
- **Checks are assertions** about the compiled geometry — if an LLM-generated `DiagramIR` fails checks, the strategy can retry or revise.
- **The renderer container must be running** for any code path that produces SVG output.
- The project uses `pydantic-ai` for LLM agent orchestration with Anthropic and OpenAI backends.
- API keys go in `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).


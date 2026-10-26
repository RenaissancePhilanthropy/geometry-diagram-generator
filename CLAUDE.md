# CLAUDE.md / AGENTS.md

(`AGENTS.md` is a symlink to this file — there is only one copy to keep in sync.)

This file provides guidance to AI coding agents (Claude Code, Codex, etc.) when working with code in this repository.

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

# Run feature-gated evals (e.g. the rectangular-prism "solids" scenarios; they are skipped unless the group is enabled)
uv run python -m evals.run --scenarios evals/scenarios_solids.yaml --strategies recipe --features solids --model anthropic:claude-sonnet-4-6 --repeats 3 --output evals/results
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
    → SymPy geometry objects (geometry_diagrams/ir/to_sympy.py)
    → Geometric validation (geometry_diagrams/ir/checks.py)
    → TikZ code (geometry_diagrams/ir/to_tikz.py)
    → LaTeX → SVG (renderer Docker container via HTTP)
```

Other strategies may skip the IR and go straight to TikZ.

Compile and both renderers read an **effective definition view** (`ir/derived.py`): the authored definitions plus the extra definitions that registered "derived" constructions synthesize (a regular polygon's vertices, a tangent circle's center, a rectangular prism's 12 edges and 6 faces, a block stack's column top faces). The authored `DiagramIR` is never rewritten; consumers that must see only what was authored (edit diagnostics, eval IR diagnostics, auto-checks) keep reading `diagram.define`.

### Package (`geometry_diagrams/`)

All core code lives under `geometry_diagrams/`, which is also the unit that gets copied into other projects. The public facade is:

- **`__init__.py`**: Re-exports `render_diagram` (LangChain `@tool`), `render_geometry_diagram` (async), `render_geometry_diagram_sync`, `DiagramResult`, `GeometryConfig`.
- **`facade.py`**: Single entry point — wraps `RecipeStrategy`, `PythonFullStrategy` or `StructureStrategy` (`GeometryConfig.strategy`) + renderer selection behind one callable. Stateless edits take the prior result's matching field: `previous_dsl` (recipe), `previous_script` (python_full, via `PythonFullStrategy.edit`, which reruns the script to rebuild its manifest, then edits in `edit_generation_mode`), `previous_ir` (structured, whole-IR regeneration anchored on the prior `diagram_ir`); the wrong one for the strategy raises `ValueError`. A `python_full` edit's rerun needs the script's feature groups enabled (a `prism()` script cannot be edited with `solids` off: `ValueError` naming the group) and costs one sandbox start plus an in-process render, no LLM call. `run_config`/`callbacks` reach every strategy, including the edit-generation LLM call; `DiagramResult` carries `cost_usd` (None = not reported; recipe never reports) and the run's pipeline `warnings`. Use `render_diagram` as a drop-in LangGraph tool; use `render_geometry_diagram` for async node wiring.
- **`features.py`**: Feature-group gating (`solids` and `tilted_ellipses`, off by default; `GeometryConfig.features` / `GEOMETRY_FEATURES`). `require_features` rejects generated IR using a disabled group's kind, or a field a group owns (`FIELD_RULES`: an ellipse `rotation_deg` that is not a literal 0 belongs to `tilted_ellipses`), at generation surfaces only; compile and render always accept every kind.
- **`config.py`**: `GeometryConfig` dataclass consolidating renderer, model, selector_model, renderer_url, font_family. `GeometryConfig.from_env()` reads env vars; individual fields can be overridden per-call.

### IR Layer (`geometry_diagrams/ir/`)

The Intermediate Representation is the central abstraction:

- **`ir.py`**: Pydantic models for `DiagramIR` — contains `Canvas`, `DefStmt` (20+ geometric definition types: points, segments, circles, triangles, polygons, intersections, etc.), `Check` (geometric invariants), and `RenderOp` (drawing commands). Also `OrderedPolygon`, an opaque filled polygon with its own stroke painted in strict list order (for painter's-algorithm figures such as block stacks): it is emitted only by registered `lower_draw` hooks, never authored, and is deliberately not in the validated `RenderOp` union, so the LLM-facing schemas and prompts do not mention it. `RectangularPrism` has optional verbatim label fields `length_label`/`width_label`/`height_label`/`base_area_label` and `BlockStack` has `count_label` (all `min_length=1`).
- **`conic_kernel.py`**: Numpy-only numeric kernel for circle/ellipse work, importing nothing from the package (tolerances come in from `to_sympy`). `EllipseFrame` (center, semi-axes, rotation; `to_local`/`to_world`/`point_at`/`param_of`/`boundary_gap`, a length-based `f/|grad f|`) is the one home of the rotation math. `intersect_conics` (half-angle quartic, `np.convolve` not `np.polymul`, roots classified by the measured gap not by `np.roots`' imaginary part, theta = pi always probed, `CoincidentConicsError` for one curve twice), `line_ellipse_crossings`, `tangent_touch_points` and `touch_point_for_line` are its closed forms. `tests/test_conic_kernel.py` checks it against a brute-force oracle.
- **`to_sympy.py`**: Compiles `DiagramIR` definitions into SymPy geometry objects by resolving the definition DAG. Handles forward references and intersection disambiguation via `pick` rules. `arc_param_frame` is the public `(cx, cy, hr, vr, start, end)` frame of an arc/sector in parametric angle. An ellipse with a nonzero `rotation_deg` compiles to the `RotatedEllipse` marker (deliberately not an `spg.Ellipse`; float rotation in radians; it holds a `conic_kernel.EllipseFrame`, the one place the tilt math lives, and the arc sites read their parametric angle through the same frame); rotation 0 keeps the exact `spg.Ellipse`. A tilted or float-valued circle/ellipse pair, and a line/segment/ray against a tilted ellipse, intersect through `conic_kernel` (exact axis-aligned pairs keep SymPy, results lifted with `_lift`); `line_tangent` and the `tangent` check on a tilted ellipse use its frame.
- **`curve_measures.py`**: `curve_length`, the one answer to how long a circle, ellipse, arc, sector or elliptical arc/sector is (a sector counts its curved edge only; circular is closed form, elliptical uses `mpmath.ellipe`), shared by the length checks and queries; raises `CurveMeasureError` for a wrong type or zero radius.
- **`to_tikz.py`**: Converts compiled SymPy objects to TikZ code (`\tkzDefPoint`, `\tkzDrawSegment`, etc.). Computes canvas bounds and helper points automatically.
- **`to_svg.py`**: Direct SVG rendering path — converts compiled SymPy objects to SVG without going through TikZ/LaTeX. When a label would overflow the SVG it grows the `viewBox` (scale preserved, capped at 200 px per side) instead of clipping it. Label text width (collision boxes, `data-bbox`) is estimated from the bundled font's real glyph advances via matplotlib's `ft2font` (flat 0.65 em per character if the font is unavailable). A tilted ellipse is drawn at any canvas aspect and is a label-nudging obstacle at its screen angle (`drawn_ellipses` entries carry an optional fifth element, that angle in radians; absent means axis-aligned).
- **`checks.py`**: Validates geometric properties (distance, collinearity, parallelism, perpendicularity, angle equality, tangency, etc.) against compiled SymPy objects with tolerance-based floating-point comparison (default relative tolerance 5e-3). The prism checks `VolumeEquals`/`TrueLengthEquals` default to a near-exact 1e-9; `CubeCountEquals(stack, expected)` is an exact integer comparison. `run_checks` takes an optional `warnings` list (e.g. a 2D length check on a prism edge warns that a projection was measured). Length checks (`equal_length`/`distance_equals`/`ratio_equal`) also measure circular and elliptical arcs and sectors by their curved edge (via `curve_measures.py`); a full circle or ellipse is rejected with a clean message pointing at the radius checks.
- **`label_bounds.py`**: Black-box post-render check that parses an already-rendered SVG's `data-bbox` label attributes (stamped by `to_svg.py`) and reports any label extending past the SVG's declared `viewBox`.
- **`pre_assert_filter.py`**: Pure 4-stage pre-filter (API-name validation, generic-instance grounding, structural lints, request-relevance) for the pre-assert pre-step's proposed checks, with no model/network dependency of its own.
- **`queries.py`**: Query interface for extracting geometric facts from compiled SymPy objects (including `query_registered`, the registry-backed solid queries, with `query_prism` and `query_stack` (cube count, volume, length, width, height and `is_height_map`) as wrappers, and a true 3D `true_length` next to the projected 2D `length` for a segment joining two corners of one prism). The `length`/`radius`/`area`/`perimeter` queries also accept the circle family (circles, ellipses, circular and elliptical arcs and sectors; a full curve's length is its `perimeter`, an open arc has no area).
- **`render_util.py`**: Shared rendering utilities used by both `to_tikz.py` and `to_svg.py`, including the backend-neutral **color layer**: `parse_color` accepts named colors, `#rrggbb`/`#rgb`, `rgb(r,g,b)`, `hsv(h,s,v)` and xcolor mixes (`blue!30`); `svg_color`/`tikz_color` emit each backend's native form (TikZ gets a `\definecolor` for hex/rgb/hsv). Unrecognized strings pass through unchanged with a renderer warning. Also the elliptical curve-walking both renderers share: `elliptical_arc_params` (the arc's parametric frame), `tick_mark_elliptical_arcs` (arc ticks) and the text-along-curve placement along an ellipse. `screen_ellipse(hr, vr, rotation, sx, sy)` is the closed-form screen image (axes and angle) of a tilted ellipse under unequal axis scales.
- **`derived.py`**: Derived-entity registry. A registered definition kind (regular-polygon/polygon-on-edge vertices, tangent-circle center, `rectangular_prism`, `block_stack`) declares the entities it owns, how they are registered into the symbol table, the extra definitions it synthesizes (`effective_defs` / `effective_diagram`), how drawing it lowers to draw ops (`lower_render`, called by both renderers; the ops may include `ir.OrderedPolygon`, which both renderers keep at its list position because it shares the draw z-layer, while ordinary `Fill`s are hoisted behind it, so an ordinary fill under an opaque ordered polygon is hidden; the lowered and effective diagrams are internal render-time views, `RenderTimeDiagram` instances that raise `TypeError` on `model_dump`/`model_dump_json`, so never dump or re-validate one), a position hook (label centroids, entity manifest; also what makes pydsl's `label_text(centroid_of=...)` accept a handle) and an optional feature group. Solid kinds (non-SymPy compiled objects) also declare, through optional hooks: how they compile (`compile`), the labels of their own fields (`lower_labels`: called once per drawn authored solid, drawn through its id or any id it owns, by `lower_render`, which therefore takes the compiled `sym`; a prism's dimension and base-area fields, a stack's `count_label`), their object type (`entry_for_object`), an agent query (`query_type`/`query`, dispatched by `dispatch_query`), a segment's `true_length`, the check kinds they own (`evaluate_checks`) and check-time warnings (`check_warnings`), a point segment labels are placed away from (`label_away_from`, both renderers), `run_ir_pipeline` warnings (`pipeline_warnings`), the recipe auto-canvas extent (`canvas_extent`), a screen box (`screen_bounds`, compared across kinds by `overlap_warnings` to warn when two drawn solids overlap, since solids are not depth-sorted) and `trusted_faces` (faces compiled without SymPy validation and skipped by the angle-mark pass). For that compiled-geometry behavior (compile, queries, checks, label placement, warnings, canvas extents, centroids) the consumers (`to_sympy`, `queries`, `checks`, both renderers, `ir_pipeline`, the recipe lowerer's canvas fit, pydsl `label_text`, evals) consult the registry instead of importing `prism`/`stack`, while the prism/stack op lowering in the recipe lowerer and the pydsl builder/handles stay on the kinds' authoring surface and still use those modules; the module docstring lists every hook and what deliberately stays outside the registry (IR schema classes, DSL ops/pydsl functions and handles, prompt text including the query-tool description lines, eval vocabulary). Adding a new construction means registering one entry here instead of special-casing the compiler. Raises `IRCompileError` when an authored id collides with a derived id.
- **`prism.py`**: Rectangular prism (`rectangular_prism` definition): a projection is a linear map of the three axes plus a viewer direction (isometric or oblique, `side` right/left), from which the visible faces and the hidden corner are derived. Compiles to a non-SymPy `Prism` object (true dimensions, volume, 8 projected corner points, corner-pair index of segments for true 3D length), synthesizes derived edges `{id}_e_{abc}_{abc}` and faces `{id}_front/_back/_left/_right/_top/_bottom`, draws wireframe/solid/unit-cube gridlines, places edge labels outside the silhouette (its `label_away_from` hook; the shared `render_util.away_normal` rule, and in SVG `render_util.away_label_center` slides a slanted edge's label along the edge so its nearest corner touches the line at the edge midpoint), implements the registry's prism query, true length, `volume_equals`/`true_length_equals` evaluation, projection and dimension-label warnings and canvas extent, and raises typed errors for render ops that would silently do nothing on a prism id. Its label fields lower (`lower_labels`) to `label_segment` ops on the silhouette edge of each dimension, derived from the hidden corner (not the hidden `e_000_001` edge for `side: right`), plus a free-text label at the bottom face centroid for `base_area_label`; the dimension-label warning also checks the fields. Opt-in via the `solids` feature group, but compile and render always accept it.
- **`stack.py`**: Block stack (`block_stack` definition): an irregular stack of unit cubes, given as `heights[z][x]` (rows front to back, columns left to right) or `cubes` (`[x, y, z]` triples: x along the front, y = HEIGHT, z = depth), drawn through the prism's projection (`prism.projection_for`, so the same `view`/`depth_angle`/`depth_scale`/`side`) with `front_color`/`side_color`/`top_color`. Compiles to a non-SymPy `Stack` object (cube set, extents, `is_height_map`, projected lattice), owns hidden lattice ids `__{id}_l{x}_{y}_{z}`, synthesizes public column top faces `{id}_top_{x}_{z}` (registry `trusted_faces`: built without SymPy polygon validation, so a 20x20 stack compiles in well under a second), lowers a draw of the id to a culled, painter-ordered list of `OrderedPolygon` faces, and uses the bounding-box center of the silhouette as its position; `count_label` lowers (`lower_labels`) to one free-text label 0.5 construction units above the lattice's screen box, once when the stack is drawn. Caps: 400 cubes, 20 cells per axis. A cube set with a cube above an empty cell warns (via the registry `render_warnings` hook) that it is not a height map. Opt-in via the `solids` feature group, but compile and render always accept it.
- **`renderer.py`**: Dispatch layer — `TikZRenderer` (HTTP to Docker container) and `SVGRenderer` (in-process, no Docker needed).
- **`errors.py`**: `IRCompileError`, raised with the failing `def_id` during IR compilation.
- **`refs.py`**: Extracts ID references from IR definition statements; used by `compile_defs` (`to_sympy.py`) for topological sorting.
- **`auto_checks.py`**: Auto-generates implicit checks from definition types (e.g., verifying an intersection point lies on both parent objects), complementing LLM-specified checks.
- **`angle_pairs.py`**: Post-compile resolver for `mark_angle_pair` annotations — replaces each `PendingAnglePair` with a concrete `MarkAngles` render op once coordinates are known (can't be done at lowering time, before SymPy has resolved the geometry).
- **`plan.py`**: `ConstructionPlan` schema for the two-phase strategy — the planner LLM describes construction steps in natural language, the constructor LLM translates each into IR.
- **`edit_diagnostics.py`**: Diagnostic-only edit-locality checker for pydsl multi-turn editing — compares two compiled turns to report which named entities moved unexpectedly; never gates whether an edit succeeds.
- **`font.py`**: `FontConfig` for diagram renderers (family, base64-embedded font data).
- **`mathtext_svg.py`**: Renders LaTeX math strings to self-contained SVG path data via matplotlib's mathtext engine — no LaTeX binary required.
- **`test_scenarios.py`**: Instantiates `DiagramIR` for the eval scenarios to confirm schema expressiveness.

### Strategies (`geometry_diagrams/strategies/`)

Multiple LLM-based approaches implementing `SubstanceStrategy` base class (`base.py`). All strategies use LangGraph and LangChain for LLM orchestration.

- **`raw_code.py`**: LLM generates TikZ directly via a ReAct agent (`create_react_agent`).
- **`raw_code_with_revise.py`**: Raw TikZ with a revision loop on validation failure.
- **`raw_svg.py`**: LLM generates SVG directly.
- **`raw_svg_with_revise.py`**: Raw SVG with a revision loop.
- **`structured.py`**: Full IR pipeline — LLM produces `DiagramIR` JSON → compile → check → render. Uses a `StateGraph` retry loop (up to `MAX_RETRIES=3`). This is more robust and easier to debug than raw code generation.
- **`recipe.py`**: Strategy that uses the recipe DSL to specify constructions. Uses a two-node `StateGraph`: selector (configurable cheap model picks relevant recipes) → DSL generator → lowering → IR pipeline. Currently the main strategy to use.
- **`pre_assert_step.py`**: Optional pre-step LLM call (before construction) that proposes geometric invariants, parses them, and runs each through `pre_assert_filter.py`'s 4-stage pre-filter to build advisory context for the script-writer.
- **`python_full.py`**: LLM writes a plain Python construction script against the `geometry_diagrams/pydsl/` builder-shim API (rather than emitting DSL/IR JSON), executed via `pydsl/sandbox.py`, with a retry loop over `pydsl/retry.py`/`retry_loop.py` on failure.

**`ir_pipeline.py`**: Shared deterministic pipeline — compile a `DiagramIR`, resolve pending angle pairs, run geometric checks, then render. Used by every strategy that produces a `DiagramIR` (`structured.py`, `recipe.py`, `python_full.py`), regardless of how that IR was produced. The result carries a `warnings` list (renderer warnings, failed `prefer`-level checks, prism and stack projection/canvas-skew warnings, a block stack's not-a-height-map warning, a prism dimension label contradicting its true length, two drawn solids overlapping on screen, unrecognized colors) that strategies append to their next retry prompt; warnings never fail a run or trigger a retry by themselves. A failed run raises `PipelineError`, which carries the warnings gathered so far.

**`llm.py`**: Model factory — maps `"anthropic:MODEL"` / `"openai:MODEL"` / `"google:MODEL"` IDs to LangChain chat models (`ChatAnthropic`, `ChatOpenAI`, `ChatGoogleGenerativeAI`). Provides `get_chat_model()`, `extract_usage()`, `make_system_message()`, and `is_gemini_model()`.

**`stages.py`**: Shared rendering tool helpers used by raw strategies.

Prompt templates are split across `instructions_structured.py`, `instructions_recipe.py`, `instructions_tikz.py`, `instructions_python_full.py` (the `python_full.py` prompt, embedding the live pydsl API stub text), `instructions.py` (shared fragments reused across templates), and related files.

**Feature-gated prompt text:** guidance for an opt-in feature group (today only `solids`) is appended through `features.tagged_fragment`/`tagged_insertions` (structured, python_full, recipe docs, query-tool descriptions), so with the group disabled every prompt is byte-identical to the ungated one. That identity is pinned by fixture-equality tests against `tests/*_pre_solids.json`; if you intentionally change default prompt text, regenerate the fixture in the same commit and say why. Each strategy that produces IR must call `features.require_features` before the shared pipeline (the structured and recipe schemas are static and cannot hide a kind, so rejection plus prompt text is the gate).

### Renderer (`renderer/`)

A Docker container running a FastAPI server (port 8001) that compiles LaTeX to SVG:
- `POST /render` accepts LaTeX, runs `lualatex` → `dvisvgm`, returns SVG.
- Uses `tkz-euclide` TeX package for geometric drawing primitives.
- The HTTP client is `geometry_diagrams/util/tikz_renderer.py`.

### Utilities (`geometry_diagrams/util/`)

- **`tikz_analysis.py`**: Extracts coordinates from TikZ code and validates geometric properties.
- **`svg_checks.py`**: Validates rendered SVG output properties.
- **`llm_judge.py`**: LLM-based quality evaluation of rendered diagrams.
- **`message_helpers.py`**: Helpers for extracting SVG/TikZ/tool content from LangChain message lists.
- **`tikz_extraction.py`**: Regex-based extraction of geometric objects (points, draw commands, marks, labels, canvas features) from TikZ/tkz-euclide source — no coordinate computation.
- **`tikz_geometry.py`**: Resolves derived point coordinates from `tikz_extraction.py`'s output and validates geometric properties (right angles, midpoints, parallelism, etc.) against them.
- **`tikz_validation.py`**: Higher-level scenario validators composing `tikz_extraction.py`/`tikz_geometry.py` to check labels, canvas features, expected point positions, and required draw entities.
- **`tracing.py`**: LangFuse callback handler factory, enabled via the `LANGFUSE_BASE_URL` env var; returns `None` (no-op) when unset.

### Evals (`evals/`)

Benchmark harness comparing strategies across tiered geometry scenarios (Basic/Intermediate/Advanced defined in `evals/scenarios.yaml`). `evals/run.py` runs scenarios with multiple repeats, collecting success rates, token usage, latency, and LLM judge scores; every record also stores the run's pipeline `warnings`, and a scenario's `fail_on_warnings: [substring, ...]` adds a `warning:<substring>` gate failure for each substring found in a recorded warning (the five prism scenarios use `does not match its true length`). Results are written as JSONL to `evals/results/` (gitignored). `scenarios.py` provides programmatic scenario loading; `scenarios_query.yaml` defines query-style eval scenarios. Scenarios may declare `requires_features: [group]` (skipped visibly unless `--features group` enables it; naming a gated scenario in `--scenario-ids` without the flag is an error); `scenarios_solids.yaml` holds the rectangular-prism and block-stack scenarios. Structural checks include `polygon_count` (authored 2D plane polygons only; a prism never counts) and `solid_count` (kind, minimum, literal dimensions; kind `block_stack` takes a literal `cube_count` read from the authored `heights`/`cubes`); prism property types `prism_volume`/`prism_dimensions` and stack property types `stack_cube_count`/`stack_extents`/`stack_is_height_map` (a stack id or `"*"` for any stack) are evaluated through queries on the full compiled symbol table, not on 2D projections, and a stack property failure is prefixed `stack:` in the gate. Note: `required_labels` is evaluated against TikZ output when there is TikZ code, and against the SVG's label text (`data-label-text`) under `--renderer svg`.

### Recipe (`geometry_diagrams/recipe/`)

A DSL for declaratively specifying geometry constructions:

- **`dsl.py`**: Defines the recipe DSL syntax and parsing, including the `prism` and `stack` ops (with the label fields `length_label`/`width_label`/`height_label`/`base_area_label` and `count_label`) and the `volume`/`true_length`/`cube_count` checks (feature-gated: `reject_disabled_ops` rejects them before lowering when `solids` is off).
- **`catalog.py`**: Library of named geometry construction recipes, and the DSL docs shown to the model (`dsl_docs_for(features)` appends the gated prism guidance; its examples live in `PRISM_EXAMPLES` and `STACK_EXAMPLES` and are executed by tests so the docs cannot drift).
- **`lower.py`**: Lowers recipe DSL constructions down to `DiagramIR` for compilation and rendering. A prism/stack origin point that no other construction op mentions is only an anchor, so auto-draw and auto-label skip it (an explicit `label_point` still labels it).
- **`expressions.py`**: Expression evaluation for recipe DSL parameters.
- **`solve.py`**: Constraint solver used during recipe lowering.

### Pydsl (`geometry_diagrams/pydsl/`)

A Python-native DSL surface: a public builder-shim API plus the sandboxed execution machinery that lets an LLM write plain Python construction scripts against it instead of emitting DSL/IR JSON directly.

- **`api.py`**: Public builder-shim API -- every function records an op against the ambient `Builder` and returns a handle (points, segments, circles, polygons, `label_text`/`label_in_polygon`, `assert_*` wiring, etc.).
- **`stub.py`**: Generates LLM-readable signature+docstring text from the public pydsl API for prompt assembly, from `api.py`'s own signatures/docstrings as the single source of truth.
- **`sandbox.py`**: Executes untrusted pydsl scripts inside a resource-limited subprocess (`smolagents.LocalPythonExecutor` plus RLIMIT_CPU and an RSS-polling watchdog).
- **`cookbook.py`**: Experimental, opt-in helper functions layered on top of the core `api.py` surface, only exposed to the sandbox when explicitly enabled.
- **`handles.py`**: Thin typed handles (`Point`, `Line`, `Circle`, `Triangle`, `Polygon`, ...) returned by pydsl API functions, wrapping internal ids so the model never re-derives geometric parts from raw point references.
- **`builder.py`**: Ambient builder context -- a contextvar-scoped `Builder` that every `api.py` function records its op against, set fresh per script execution.
- **`asserts.py`**: `assert_*` geometric-invariant predicates for the Python DSL surface, wrapping `ir.Check` kinds (plus canvas-membership checks with no backing `Check` kind). `assert_volume`/`assert_true_length` belong to the gated `solids` group.
- **Feature-gated names:** `pydsl.GROUPED_NAMES` maps a feature group to the API names (e.g. `prism`, the `Prism` handle in `handles.py`, `assert_volume`, `assert_true_length`, and `stack`, the `Stack` handle with `.cube_count`/`.volume`/`.top(x, z)`/`.label`, `assert_cube_count`; `prism()`/`stack()` take the same label kwargs) that join the sandbox namespace and the prompt stub only when the group is enabled; the enabled set is passed explicitly into the sandbox subprocess request.
- **`_sandbox_child.py`**: Entrypoint for the sandboxed script's own child process, invoked via `subprocess.Popen` from `sandbox.py` — deliberately not `multiprocessing`, which would re-execute host init code in the child.
- **`hashline.py`**: Content-hash line-anchored script editing ("hashline") — each line is tagged `{line_number}:{hash}`; a stale tag means the line changed since the model last saw it.
- **`line_number.py`**: Plain line-number-anchored script editing ("line_number") — same op model as `hashline.py`, but references a line by its plain 1-indexed position instead of a content hash.
- **`patch.py`**: Applies a unified-diff-shaped patch to a pydsl script — exact context-line matching only, no fuzzy offset search.
- **`search_replace.py`**: Applies a sequential list of exact-match search/replace blocks to a pydsl script (Aider-style semantics: blocks apply in order against a single mutating buffer).
- **`retry.py`**: Classifies executor failures and builds a retry prompt message, including did-you-mean suggestions for hallucinated API names.
- **`retry_loop.py`**: Runs successive script attempts through `run_script`, stopping on the first success or once a caller-supplied attempt cap is reached.

### Docs (`docs/`)

- **`geometry-dsl-spec.md`**: Formal specification of the geometry DSL/IR schema, including the rectangular prism, the block stack, `OrderedPolygon`, the color-forms contract, SVG label `viewBox` growth, and the pipeline warnings list.
- **`gen_examples.py`**: Script to regenerate example SVGs in `docs/examples/`.
- **`examples/`**: Pre-rendered SVG examples used for documentation, including `diagram_kinds/attempts/` and `diagram_kinds/attempt_scripts/`, which hold per-attempt generation artifacts (SVGs/scripts) for `assemble_diagram_kinds_manifest.py`'s fresh-generation kinds.
- **`retrospective-template.md`**: Optional post-ticket step for `subagent-execution`-style work in this repo — after an implementer subagent closes a ticket (especially one that struggled or hit a known gap), resume it and ask what tooling/information would have made the task easier. See `docs/specs/2026-09-04-diagram-kinds-retrospective-findings.md` for a worked example where this surfaced a convergent, actionable finding across unrelated tickets.

## Key Design Notes

- **Focus on test-driven development**: The project is structured around unit tests for each component and end-to-end tests for the full pipeline. This ensures reliability and makes it easier to iterate on strategies. Writing tests first for new features or bug fixes is highly encouraged.
- **SymPy is the source of truth** for geometric computation. TikZ code is generated from SymPy objects, not from the LLM's coordinate guesses.
- **Checks are assertions** about the compiled geometry — if an LLM-generated `DiagramIR` fails checks, the strategy retries via the LangGraph `StateGraph` retry loop.
- **The renderer container must be running** for any code path that uses `TikZRenderer`. The `SVGRenderer` path needs no container — it renders in-process from SymPy.
- The project uses **LangGraph** and **LangChain** (`langchain-anthropic`, `langchain-openai`, `langchain-google-genai`) for LLM orchestration. Inner retry loops use `StateGraph`; conversational agents use `create_react_agent`.
- API keys go in `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).
- **Opt-in feature groups gate generation, never compilation.** A feature group (`features.FEATURE_GROUPS`, enabled with `GeometryConfig.features`, the `GEOMETRY_FEATURES` env var, or `--features` in evals) controls what the model is told and what strategies accept; stored IR using a gated kind still compiles and renders when the group is off.
- **Byte-identity checks need a fixed hash seed.** Recipe renders can differ between processes because the dependency sort (`TopologicalSorter` in `to_sympy.py`) iterates string-keyed sets. Fix `PYTHONHASHSEED=0` when comparing rendered output before and after a change.

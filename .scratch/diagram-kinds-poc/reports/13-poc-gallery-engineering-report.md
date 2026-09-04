# Ticket 13: PoC generation script + final SVG set — Engineering Report

## Scope note (corrections applied)

Per the controller's corrections to the ticket text:
- `balance_scale` actually **passed** baseline (level beam, correct pans,
  correct equation) — reused as-is, NOT treated as an orphan.
- `coordinate_plane` was baseline "partial" (caption clipped off the left
  edge) — treated as an orphan needing a fresh fix.
- The 5 kinds needing a genuine fresh `PythonFullStrategy.run()` are:
  `area_model`, `attribute_chart` (both with
  `experimental_diagram_cookbook=True`), `coordinate_plane`,
  `scatter_plot`, `shape_comparison` (all three without the cookbook
  flag). Tickets 10/11's `area_model`/`attribute_chart` proof SVGs were
  **hand-built through the sandbox** (`run_script(enable_cookbook=True)`),
  not genuine `PythonFullStrategy.run()` calls — confirmed by reading
  both reports directly — so this ticket does NOT reuse them; it re-runs
  both kinds as real LLM-driven strategy calls (see below).

## What was implemented

New directory `.scratch/diagram-kinds-poc/final/`, mirroring ticket 07's
`baseline/` structure:

- `final_prompts.py` — the 5 kinds' prompts, one list per kind
  (`FINAL_KIND_CONFIGS: kind -> (use_cookbook, [attempt prompts in
  order])`), each entry the prompt actually iterated to.
- `run_final.py` — driver: for a given `(kind, attempt_index)`, makes a
  fresh `PythonFullStrategy()` instance and calls
  `strategy.run(prompt, model=..., renderer=SVGRenderer(),
  experimental_diagram_cookbook=use_cookbook)`, exactly mirroring
  `../baseline/run_baseline.py`'s call pattern. Saves each attempt's SVG
  to `attempts/<kind>_attempt<N>.svg` and appends mechanical generation
  facts (ok/error/retries/duration) to `generation_log.json`. CLI flags
  (`--kind`, `--attempt`) let a single attempt be re-run without
  re-running the whole set.
- `final_manifest_lib.py` — final manifest schema
  (`FinalManifestEntry(kind, svg_path, source, status, notes)`) +
  read/write helpers, mirroring `../baseline/manifest_lib.py`.
- `assemble_manifest.py` — pure `build_final_entries(baseline_manifest,
  fresh_choices)` combines ticket 07's baseline manifest (25 "pass" kinds
  reused as `source="baseline-reuse"`) with `FRESH_CHOICES` (the 5 kinds'
  hand-reviewed outcome, after visually reviewing every attempt's
  rendered SVG) into 30 `FinalManifestEntry` objects; `main()` copies
  every referenced SVG into `./svgs/<kind>.svg` so the final manifest is
  self-contained, then writes `manifest.json`.
- `manifest.json` — the final 30-kind manifest (inline table below).
- `svgs/` — 28 SVGs (all "ok" kinds except `none`, which needs none).
- `attempts/` — every raw attempt SVG (9 files: 1 each for area_model,
  attribute_chart, coordinate_plane; 3 each for scatter_plot,
  shape_comparison) kept for evidence of real iteration.
- `tests/test_diagram_kinds_final.py` — 15 unit tests for
  `final_manifest_lib.py`'s schema validation and
  `assemble_manifest.py`'s `build_final_entries` logic (including 2 tests
  run against the *real* baseline manifest + real `FRESH_CHOICES` to
  catch drift). No LLM calls exercised in tests, same discipline as
  ticket 07's `test_diagram_kinds_baseline.py`.

Rendering verification method: rendered every SVG to PNG with a real
headless Chrome for Testing binary (found cached at
`~/Library/Caches/ms-playwright/chromium-1234/...`, no `playwright` pip
package needed — invoked directly via `--headless
--screenshot=... file://...`) and visually inspected each PNG — same
"actually look at the rendered output" discipline as ticket 07's baseline
review (headless Chrome, not cairosvg, per ticket 07's own note about
cairosvg's tspan mis-rendering).

## The 5 fresh-generation attempts

### area_model (cookbook=True, 1 attempt)

Prompt: box-method rectangle for 23×15, explicit ask that "all 4 cell
labels are present and none of the text overlaps."

Result: attempt 0 — clean. All 4 partial products (200, 100, 30, 15)
render at distinct, non-overlapping positions; both factor braces (20+3,
10+5) correct. Baseline's defect (2 empty right-column cells, overlapping
left-column text) is gone. **Verdict: ok.**

### attribute_chart (cookbook=True, 1 attempt)

Prompt: comparison table (square/rectangle/triangle ×
sides/right-angles/equal-sides), explicit ask for "a single bordered grid
... no duplicate or extra decorative rows/bands."

Result: attempt 0 — clean. Single header row, single header column, each
check/X mark rendered exactly once, no stray decorative bands. Baseline's
defect (duplicated headers, 2 extra bands) is gone. **Verdict: ok.**

### coordinate_plane (no cookbook, 1 attempt)

Prompt: same base content as baseline, plus explicit instruction that the
"Translation: (x-2, y-3)" caption be placed "safely inside the canvas
with enough left margin that it is not clipped by the left edge."

Result: attempt 0 — clean. Caption renders fully inside the canvas,
bottom-left, fully legible; triangle/translation/vertex labels all
correct. Baseline's clipped-caption defect is gone. **Verdict: ok.**

### scatter_plot (no cookbook, 3 attempts — known gap)

- **Attempt 0**: prompt asked for "canvas wide enough... enough right-hand
  margin." Result: viewBox `0 0 91.5 500` — canvas rendered as a tall,
  narrow strip; axis title, rise/run labels, and point-coordinate text cut
  off at the right edge (same defect as baseline).
- **Attempt 1**: prompt shortened axis labels to "Hours"/"Score" and gave
  an explicit "leave at least 2 extra units of margin" instruction.
  Result: viewBox `0 0 83.7 500` — no better; additionally the
  denser per-unit y-tick marks (from a stray grid choice in the LLM's
  script) crowded the axis further, and "Slope"/most text was still
  clipped.
  x-axis tick labels also began overlapping ("12345678" jammed together).
- **Attempt 2**: prompt was rewritten to be maximally explicit — "the plot
  must be noticeably WIDER than it is tall (a landscape-shaped canvas,
  roughly 1.5 times as wide as tall)," coarse tick spacing only, no grid,
  no slope triangle. Result: viewBox `0 0 79.2 500` — **worse**, not
  better: point-coordinate labels ran together illegibly at the bottom of
  the canvas, "Hours" clipped at the left edge.

**Root cause** (read directly from
`geometry_diagrams/ir/to_svg.py`'s `ir_to_svg()`): the SVG renderer
computes a single uniform `scale = usable / max(geo_w, geo_h)` shared by
both axes — correct, and necessary, for the tool's core geometry diagrams
(so circles stay circular, right angles stay square, etc.), but it means
the SVG's aspect ratio is locked to the canvas's x-range:y-range ratio.
This scatter plot's y-range (score, 0–100) is roughly 15-25× its x-range
(hours, 0–6/8), so the rendered canvas is inherently a tall, narrow strip
regardless of prompt wording about "wide canvas" or margins — the
renderer will not stretch one axis independently of the other. Fixing
this for real would require either compressing the y-axis (misrepresenting
the data) or an engineering change to `to_svg.py` to allow independent
x/y scaling for axis-imbalanced content — both out of this ticket's scope
(prompt refinement + re-running the existing pipeline only, no renderer
changes).

**Verdict: known-gap**, recorded honestly in the manifest with the full
attempt history and root cause above (see `manifest.json`'s
`scatter_plot` entry / the table below).

### shape_comparison (no cookbook, 3 attempts)

- **Attempt 0**: baseline-style prompt plus "enough bottom margin... never
  clipped." Result: Area/Perimeter labels under each shape were clean,
  but the closing two-line summary sentence rendered with its two lines
  overlapping each other (same defect as baseline).
- **Attempt 1**: prompt forced explicit vertical stacking with "at least 1
  full unit of blank margin" language. Result: **same defect persisted**
  — the two summary lines still overlapped, just with a mildly different
  wrap point.
- **Attempt 2**: prompt instead forced the summary onto a **single short
  line** ("exactly ONE short summary label as a SINGLE line of text...
  short enough to fit on one line, not wrapped"). Result: clean — "Rectangle
  has more area; both have equal perimeter" renders on one line with no
  overlap or clipping, all other labels intact.

**Verdict: ok** (attempt 2 kept as the final SVG). The real lesson: the
two-line-summary defect wasn't fixable by asking for "more margin" between
two wrapped lines — the LLM's generated pydsl script placed both lines at
too-similar a y-coordinate regardless; forcing a single line sidestepped
the wrapping/spacing computation entirely.

## Final 30-kind manifest (summary table)

| kind | source | status |
|---|---|---|
| grid_area | baseline-reuse | ok |
| tape_diagram | baseline-reuse | ok |
| number_line | baseline-reuse | ok |
| coordinate_plane | fresh-generation | ok |
| scatter_plot | fresh-generation | **known-gap** |
| shape_comparison | fresh-generation | ok |
| attribute_chart | fresh-generation | ok |
| work_table | baseline-reuse | ok |
| area_model | fresh-generation | ok |
| equation_steps | baseline-reuse | ok |
| angle_figure | baseline-reuse | ok |
| cube_volume | baseline-reuse | ok |
| prism_3d | baseline-reuse | ok |
| l_prism | baseline-reuse | ok |
| prism_net | baseline-reuse | ok |
| composite_polygon | baseline-reuse | ok |
| dot_plot | baseline-reuse | ok |
| circle | baseline-reuse | ok |
| column_arithmetic | baseline-reuse | ok |
| long_division | baseline-reuse | ok |
| composite | baseline-reuse | ok |
| object_array | baseline-reuse | ok |
| bar_graph | baseline-reuse | ok |
| place_value_blocks | baseline-reuse | ok |
| place_value_chart | baseline-reuse | ok |
| number_bond | baseline-reuse | ok |
| ruler_measure | baseline-reuse | ok |
| fill_level | baseline-reuse | ok |
| balance_scale | baseline-reuse | ok |
| none | baseline-reuse | ok (no SVG — not a rendering kind) |

**29 ok / 1 known-gap** (out of 30). Full manifest with per-kind notes:
`.scratch/diagram-kinds-poc/final/manifest.json`.

## Test results

- New tests: `tests/test_diagram_kinds_final.py` — **15 passed** (schema
  validation + assembly logic, including 2 tests exercised against the
  real baseline manifest and real `FRESH_CHOICES` dict).
- Full suite: `.venv/bin/python -m pytest tests/ -q` →
  **2172 passed, 48 skipped, 0 failed** (up from the stated baseline of
  2157 passed / 48 skipped — 15 new tests added, no regressions).

## Files changed / created

- `.scratch/diagram-kinds-poc/final/final_prompts.py` (new)
- `.scratch/diagram-kinds-poc/final/run_final.py` (new)
- `.scratch/diagram-kinds-poc/final/final_manifest_lib.py` (new)
- `.scratch/diagram-kinds-poc/final/assemble_manifest.py` (new)
- `.scratch/diagram-kinds-poc/final/manifest.json` (new, final manifest)
- `.scratch/diagram-kinds-poc/final/generation_log.json` (new, mechanical
  facts for all 9 attempts)
- `.scratch/diagram-kinds-poc/final/svgs/*.svg` (new, 28 files — the
  final gallery SVG set)
- `.scratch/diagram-kinds-poc/final/attempts/*.svg` (new, 9 files — every
  raw attempt, kept as evidence of iteration)
- `tests/test_diagram_kinds_final.py` (new, 15 tests)

Committed as `13468df` — "feat: assemble final 30-kind gallery SVG set +
manifest (ticket 13)" (44 files changed, 1373 insertions).

## Self-review

- **Completeness**: all 30 kinds present in the final manifest (verified
  by a real test against `kinds_prompts.KIND_NAMES`). All 5 flagged kinds
  got genuine fresh `PythonFullStrategy.run()` calls — confirmed by
  reading tickets 10/11's reports first (their `area_model`/
  `attribute_chart` proofs were hand-built through the sandbox, not
  strategy runs) and deliberately not reusing those SVGs. Every "ok"
  status points at a real SVG copied from an actual attempt (either
  ticket 07's baseline reuse or one of this ticket's fresh attempts) —
  none fabricated or hand-edited.
- **Honesty**: `scatter_plot` is the one known-gap, with a note recording
  all 3 attempts' prompts, their specific rendered defects, and a
  root-caused explanation (read directly from `to_svg.py`) of why prompt
  wording alone can't fix it. Not silently omitted, not force-passed —
  its `svg_path` is `null` in the manifest so the gallery cannot
  accidentally display a broken render as if it were clean.
- **Discipline**: no hand-authored pydsl script stands in for any kind's
  pipeline output anywhere in this ticket's work — every "ok" SVG in
  `svgs/` is either ticket 07's real baseline strategy-run output or one
  of this ticket's real fresh strategy-run attempts. No HTML/gallery code
  was written (out of scope per the boundary in the ticket).

## Concerns

None blocking. One judgment call worth flagging: `scatter_plot`'s known-gap
is an architectural limitation (equal-unit x/y scaling), not a
prompt-solvable defect — a 4th or 5th prompt attempt would very likely
not help either, so iteration was stopped at 3 per the ticket's own
"2-3 tries" guidance rather than continuing indefinitely.

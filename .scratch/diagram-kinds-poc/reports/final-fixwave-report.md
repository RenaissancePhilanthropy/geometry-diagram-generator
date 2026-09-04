# diagram-kinds-poc final fix wave report

Branch: `diagram-kinds-poc`. Scope: 4 findings from the closing whole-branch
review (2 Important + 1 Important + 1 Minor). No new review round follows
this one beyond a scoped re-review.

## 1. Stale "currently empty / no-op" comments

All 5 locations found and corrected to reflect that `COOKBOOK_NAMES` now
lists 7 real helpers (`unit_grid`, `array_of`, `tick_marks`, `bar`, `bars`,
`table_grid`, `oblique_point`).

### `geometry_diagrams/pydsl/_sandbox_child.py` (`_build_tool_names`)

Old:
> `COOKBOOK_NAMES` is empty until later tickets (09-12) populate
> `cookbook.py`, so `enable_cookbook=True` is currently a no-op in
> practice — this function is what makes that wiring provable ahead of
> any real cookbook content, independent of a real subprocess.

New:
> `COOKBOOK_NAMES` now lists `cookbook.py`'s 7 real helper functions
> (`unit_grid`, `array_of`, `tick_marks`, `bar`, `bars`, `table_grid`,
> `oblique_point`), so `enable_cookbook=True` makes all of them callable
> from the sandboxed script.

### `geometry_diagrams/strategies/python_full.py` (`PythonFullStrategy.run` docstring)

Old:
> ... (`sandbox.run_script`'s `enable_cookbook`) -- currently a no-op in
> practice since COOKBOOK_NAMES is still empty; later tickets (09-12)
> populate it with real cookbook helpers. Deliberately NOT threaded
> through ...

New:
> ... (`sandbox.run_script`'s `enable_cookbook`) -- COOKBOOK_NAMES now
> lists cookbook.py's 7 real helper functions (unit_grid, array_of,
> tick_marks, bar, bars, table_grid, oblique_point). Deliberately NOT
> threaded through ...

### `geometry_diagrams/strategies/instructions_python_full.py` (`build_python_full_instructions` docstring)

Old:
> ... documenting the opt-in helper functions from
> geometry_diagrams/pydsl/cookbook.py (only reachable in the sandbox when
> PythonFullStrategy.run() is called with
> experimental_diagram_cookbook=True). Ticket 09 adds the first three
> (grid/discrete-object) helpers; later tickets (10-12) append more.

New:
> ... documenting the opt-in helper functions from
> geometry_diagrams/pydsl/cookbook.py (only reachable in the sandbox when
> PythonFullStrategy.run() is called with
> experimental_diagram_cookbook=True): unit_grid, array_of, tick_marks,
> bar, bars, table_grid, and oblique_point.

(This edit is bundled with finding 2's docstring rewrite of the same
docstring — see below.)

### `evals/run.py` (`--experimental-diagram-cookbook` help text)

Old:
> "adds a (currently empty) advisory cookbook section to the
> script-writer prompt and, defense in depth, allows the sandboxed script
> to call any cookbook helper. ..."

New:
> "adds an advisory cookbook section (7 helpers: unit_grid, array_of,
> tick_marks, bar, bars, table_grid, oblique_point) to the script-writer
> prompt and, defense in depth, allows the sandboxed script to call any
> cookbook helper. ..."

### `geometry_diagrams/pydsl/__init__.py` (`COOKBOOK_NAMES` comment)

Condensed the ~29-line ticket-by-ticket changelog (separate paragraphs for
"Ticket 09 populates...", "Ticket 10 appends...", "Ticket 11 appends...",
"Ticket 12 (the last one on this branch) appends...") down to a plain,
current-state comment describing what the list is and why it's kept out
of `__all__`, with no per-ticket narration. Kept the still-load-bearing
paragraph explaining the getattr/AttributeError contract with
`_sandbox_child.py`.

## 2. Docstring overstates dynamic generation for the cookbook section

`build_python_full_instructions`'s docstring previously implied the whole
prompt (base API + cookbook section) is "dynamic by design ... not a
static, hand-copied string." Rewrote the docstring to scope that claim to
the base `## Available API` section only (still true — it calls
`generate_stub()` at build time), and to explicitly state that the
appended `## Cookbook (experimental)` section is a manually-maintained
addendum, hand-copied from `cookbook.py`'s docstrings, that must be kept
in sync by hand.

Verified the hand-copied cookbook section's text against each of the 7
helpers' current docstrings in `cookbook.py`. Found one drifted detail:
`unit_grid`'s hand-copied line invented a parenthetical function name that
doesn't exist in `cookbook.py`'s docstring — "a backdrop grid behind a
composite shape (`composite_polygon`)" — where the real docstring just
says "a grid behind a composite polygon" (no such identifier). Other
helpers legitimately reference real example names this way (e.g.
`array_of`'s docstring really does say `object_array`/`dot_plot`), so this
one stood out as fabricated. Fixed to drop the invented identifier:
"a backdrop grid behind a composite polygon." The other 6 helpers'
hand-copied text was checked line by line against their real docstrings
and found faithful in substance (some paraphrasing, no invented claims).

## 3. Final gallery deliverable relocated out of `.scratch/`

Per `spec.md`'s "PoC deliverable" section (which named
`docs/gen_cookbook_examples.py` following the `docs/gen_examples.py`
pattern), moved the disposable-working-area deliverable to a permanent
location under `docs/`:

**Scripts** (repo root `docs/`, flat, following `docs/gen_examples.py`'s
single-script-in-docs/ convention):
- `docs/gen_diagram_kinds_examples.py` (was `.scratch/.../final/run_final.py`)
- `docs/assemble_diagram_kinds_manifest.py` (was `.../final/assemble_manifest.py`)
- `docs/diagram_kinds_manifest_lib.py` (was `.../final/final_manifest_lib.py`)
- `docs/diagram_kinds_prompts.py` (was `.../final/final_prompts.py`)

**Data** (mirrors `docs/gen_examples.py`'s own `docs/examples/` output
convention, in its own subdirectory since this is a 28-file gallery + a
manifest rather than 3 loose SVGs):
- `docs/examples/diagram_kinds/manifest.json`
- `docs/examples/diagram_kinds/svgs/*.svg` (28 files)

Internal path fixes:
- `gen_diagram_kinds_examples.py`: `ATTEMPTS_DIR` and `GENERATION_LOG_PATH`
  now resolve under `docs/examples/diagram_kinds/` (via `OUT_DIR`) instead
  of the old `.scratch/.../final/`, so a future re-run needs no `.scratch`
  dependency at all.
- `assemble_diagram_kinds_manifest.py`: `FINAL_MANIFEST_PATH`/`FINAL_SVG_DIR`
  now resolve under the same `docs/examples/diagram_kinds/` `OUT_DIR`;
  fresh-generation SVG sources now resolve relative to `OUT_DIR` (matching
  where `gen_diagram_kinds_examples.py` now writes attempts) instead of the
  old `FINAL_DIR`. `BASELINE_DIR` still points at
  `.scratch/diagram-kinds-poc/baseline/` (explicitly, via `REPO_ROOT`),
  since that directory was left untouched per instructions — documented
  this dependency directly in the script's module docstring (see Judgment
  calls below).
- `diagram_kinds_manifest_lib.py` / `diagram_kinds_prompts.py`: only
  docstring/comment path mentions updated (no functional path constants in
  either file); renamed sibling-module import in
  `assemble_diagram_kinds_manifest.py` from `final_manifest_lib` to
  `diagram_kinds_manifest_lib`.

Removed the relocated files from `.scratch/diagram-kinds-poc/final/`:
`run_final.py`, `assemble_manifest.py`, `final_manifest_lib.py`,
`final_prompts.py`, `manifest.json`, `svgs/` (28 files) — via `git rm`, no
duplicates left. Left `.scratch/diagram-kinds-poc/final/attempts/` (10 raw
per-attempt SVGs from the actual generation run) and
`generation_log.json` in place — these are intermediate working
notes/evidence, not "the deliverable" per spec §4 (SVGs saved + gallery),
and the instructions said to leave the rest of
`.scratch/diagram-kinds-poc/` untouched aside from the relocated files.
Also left the rest of `.scratch/diagram-kinds-poc/` (`baseline/`,
`cookbook/`, `reports/`, `issues/`, `spec.md`, `map.md`, `ledger.md`)
completely untouched.

Updated `tests/test_diagram_kinds_final.py`: `FINAL_DIR` (pointing at the
old `.scratch/.../final/`) replaced with `DOCS_DIR` (`docs/`); its module
fixtures now load `diagram_kinds_manifest_lib` and
`assemble_diagram_kinds_manifest` (the renamed files) from `DOCS_DIR`
instead of `final_manifest_lib`/`assemble_manifest` from the old
`FINAL_DIR`. `BASELINE_DIR` is unchanged (still points at
`.scratch/diagram-kinds-poc/baseline/`, which was left in place). All 15
tests in this file pass unchanged otherwise — no test *behavior* changed,
only where the modules under test are loaded from.

Verified none of the new `docs/` files are caught by any `.gitignore` rule
(`git status --short docs/` shows them as ordinary untracked/added files,
no `git add -f` needed).

## 4. Cookbook prompt framing text (minor, bundled)

`instructions_python_full.py`'s `## Cookbook (experimental)` intro
previously said "use them as shortcuts for grid/discrete-object diagrams
instead of hand-writing the equivalent loops yourself." Updated to:
"use them as shortcuts for grid/discrete-object, bar/container, table,
and oblique-3D-projection diagrams instead of hand-writing the equivalent
loops/arithmetic yourself" — reflecting all 7 helpers' actual scope
(`bar`/`bars` for containers, `table_grid` for tables, `oblique_point` for
3D projection), not just the original 3.

## Test results

- Before: `.venv/bin/python -m pytest tests/ -q` → 2172 passed, 48
  skipped, 0 failed.
- After: same command → 2172 passed, 48 skipped, 0 failed (identical
  count). `tests/test_diagram_kinds_final.py` specifically: 15/15 passed.

## Judgment calls

1. **Naming of the 4 relocated scripts**: the spec named a single script
   (`docs/gen_cookbook_examples.py`), but reality had 4 files with
   distinct responsibilities (live LLM generation, assembly logic, schema,
   prompt data). Rather than force-merging them into one file (an
   architecture change beyond this fix wave's scope), kept them as 4
   sibling files directly under `docs/`, named
   `gen_diagram_kinds_examples.py` (the actual generator, closest to the
   spec's suggested name) plus 3 supporting modules with parallel
   `diagram_kinds_*`/`*_diagram_kinds_*` naming.
2. **`assemble_diagram_kinds_manifest.py` still depends on
   `.scratch/diagram-kinds-poc/baseline/`**: that directory holds 25 of
   the 30 kinds' baseline verdicts/SVGs and was explicitly out of scope to
   touch (per instructions, left for the human to handle at Close). The
   already-produced `manifest.json` + `svgs/` are moved and self-contained
   as static artifacts, but *re-running* the assembly script from scratch
   after `.scratch/` is deleted will fail on the missing baseline
   directory. This is now called out explicitly in the script's module
   docstring rather than silently broken. Fully decoupling assembly from
   baseline (e.g. by also archiving baseline's 25 SVGs into `docs/`) was
   judged out of scope — the finding asked to relocate "the final gallery
   deliverable," not to also promote the disposable baseline snapshot to
   permanent status.
3. **`attempts/` and `generation_log.json` left in `.scratch/`**: these
   are raw per-attempt evidence used to reach the hand-reviewed
   `FRESH_CHOICES` decisions, not the polished deliverable itself. Left
   them behind rather than relocating, consistent with "leave the rest of
   `.scratch/diagram-kinds-poc/` untouched" and "don't leave duplicates."
   `gen_diagram_kinds_examples.py`'s *own* future output location was
   redirected to `docs/examples/diagram_kinds/attempts/` so a future
   re-run is self-sufficient going forward (doesn't recreate a
   `.scratch/` dependency), even though the existing historical
   attempts/log were left where they already were.
4. **`composite_polygon` fix**: treated the invented parenthetical
   identifier in `unit_grid`'s hand-copied prompt text as drift per
   finding 2(b)'s instruction to fix wording that has "already drifted,"
   even though it's a small, arguably harmless embellishment rather than a
   factual error about behavior.

## Files touched

- `geometry_diagrams/pydsl/_sandbox_child.py`
- `geometry_diagrams/strategies/python_full.py`
- `geometry_diagrams/strategies/instructions_python_full.py`
- `evals/run.py`
- `geometry_diagrams/pydsl/__init__.py`
- `tests/test_diagram_kinds_final.py`
- New: `docs/gen_diagram_kinds_examples.py`,
  `docs/assemble_diagram_kinds_manifest.py`,
  `docs/diagram_kinds_manifest_lib.py`, `docs/diagram_kinds_prompts.py`,
  `docs/examples/diagram_kinds/manifest.json`,
  `docs/examples/diagram_kinds/svgs/*.svg` (28 files)
- Removed (via `git rm`):
  `.scratch/diagram-kinds-poc/final/run_final.py`,
  `.scratch/diagram-kinds-poc/final/assemble_manifest.py`,
  `.scratch/diagram-kinds-poc/final/final_manifest_lib.py`,
  `.scratch/diagram-kinds-poc/final/final_prompts.py`,
  `.scratch/diagram-kinds-poc/final/manifest.json`,
  `.scratch/diagram-kinds-poc/final/svgs/*.svg` (28 files)

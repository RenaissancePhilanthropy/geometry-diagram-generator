# Solids: Evidence, Known Limitations and Follow-ups

Companion to `docs/specs/2026-10-15-solids-prisms-and-block-stacks-decisions.md`
(the decision record). This file records what was measured with real models,
which silent-corruption classes the harness does and does not catch, the
known weaknesses of the code on branch `feat/solids-prisms` (HEAD 22ff253),
the proposed path to enabling `solids` by default, how to add a third solid,
and the deferred minor items. Schema and behavior: `docs/geometry-dsl-spec.md`
([`rectangular_prism`](../geometry-dsl-spec.md#rectangular_prism),
[`block_stack`](../geometry-dsl-spec.md#block_stack),
[Pipeline warnings](../geometry-dsl-spec.md#pipeline-warnings)).

Status: `solids` is OFF by default and the branch is unmerged. Nothing in the
evidence below supports enabling it yet.

## Eval history

All runs used `--features solids`, the in-process SVG renderer, and the
scenarios in `evals/scenarios_solids.yaml` as they stood at the time. "Gate"
is the harness gate (generation, render, structural and property checks).
Sample sizes are small throughout: no cell has more than 3 repeats, and most
later cells have 1. Treat every pass rate here as anecdotal.

**1. Prism v1 run (solids ticket 18, at f8f71f1), `anthropic:claude-sonnet-4-6`.**
3 prism scenarios x 3 strategies x 3 repeats = 27 runs with solids on, plus 27
with solids off as a baseline.

| Strategy | On: gate | Off: gate | On: mean s | Off: mean s |
|---|---|---|---|---|
| recipe | 9/9 | 0/9 | 9.5 | 23.0 |
| structured | 9/9 | 0/9 | 10.4 | 28.6 |
| python_full | 9/9 | 0/9 | 5.4 | 21.2 |

- Zero retries with solids on. The off baseline fails the prism-specific
  checks by construction, so 0/9 vs 9/9 shows the gate and the feature
  working end to end; it is not a quality comparison. Latency, tokens and the
  look of the hand-rolled off diagrams are the only real comparisons (recipe
  used roughly half the input tokens with solids on).
- With solids off, structured still emitted `rectangular_prism` in 3 of 9
  runs (the static schema exposes the kind) and failed after 3 attempts at
  the `require_features` gate.
- Hand inspection of the IR records found a defect in 10 of the 27 passing
  runs: labels on the wrong edge (recipe unit-cubes r1 swapped "4" and "5";
  structured wireframe put the height "5" on a length edge in all 3 repeats),
  unit-cube grids lost because the faces were drawn instead of the prism id
  (python_full 3/3, structured 1/3), and recipe drawing the unit-cube
  scenario oblique (3/3) although the reference figure is isometric.
  `required_labels` was not evaluated at all under the SVG renderer.
- The structured strategy recorded 0 tokens and no run reported `cost_usd`.

These findings produced the follow-up commits 292ec9a (unit-cube guidance and
warning), 8a32734 (warning when a numeric edge label differs from the edge's
true length), db1a299 (`required_labels` evaluated on SVG label text),
3f0eae9 (CSS color names defined for TikZ) and 95cd5ad (recipe guidance:
`view=isometric` when the request says isometric).

**2. Re-runs after those fixes (2026-10-14), 1 repeat per cell, the same 3
prism scenarios.** Read from run records kept in a temporary session
directory, not retained.

| Model | recipe | structured | python_full | Gate failures |
|---|---|---|---|---|
| anthropic:claude-sonnet-4-6 | 1/3 | 1/3 | 2/3 | all `required_labels` |
| anthropic:claude-haiku-5-5 | 1/3 | 3/3 | 3/3 | all `required_labels` |
| openai:gpt-6-luna | 3/3 | 0/3, then 3/3 | 1/3 | python_full: `required_labels` |

- Every gate failure was a label-wording mismatch: the scenarios then
  required "6 units"-style labels, and the models wrote bare numbers on edges
  ("11", "6", "3") or their own area wording. Commit 1d923db then made the
  required labels bare numbers and added two `-feet` scenario variants.
- luna's structured 0/3 was infrastructure, not solids: OpenAI's strict
  `json_schema` mode rejects the `oneOf` in `DiagramIR`'s schema (HTTP 400 on
  every attempt). Fixed by forcing function calling (933a319); a structured
  re-run on luna then passed 3/3.
- The unit-cube scenario's prompt does not say "isometric". It was drawn
  oblique by sonnet recipe, sonnet python_full and haiku python_full (n=1
  each), isometric elsewhere. Every unit-cube prism in these re-runs drew the
  prism id, so the grid was present.

**3. Units test, `openai:gpt-6-luna`, python_full only.** The two oblique
scenarios and their `-feet` variants, 3 repeats each: 12/12 gate pass. With
"feet" in the prompt every run carried the unit ("11 ft", "Base area = 60
ft²"); with "units" in the prompt every run wrote bare edge numbers. So the
unit word is dropped specifically for "units". Required labels are now bare
numbers by design, so no check enforces units either way.

**4. Block-stack scenarios (block-stacks ticket 09), `openai:gpt-6-luna`,
1 repeat, 3 stack scenarios x 3 strategies.** Gate 9/9, 0 retries. Height-map
drawings were correct in all strategies. Defects the checks missed:

- the arch (an overhang cube set) via recipe and python_full swapped y and z:
  five cubes lying flat, still a height map, so no warning and the cube count
  still matched;
- the structured arch put the bridge one level too high (the prompt was
  ambiguous; reworded in 594c500, not re-run on that wording alone);
- "16 cubes" placed at the stack's bounding-box center, straddling cube
  edges; recipe drew a stray origin dot labeled "O"; structured recorded 0
  tokens.

After block-stacks ticket 11 (axis guidance on all three surfaces plus
`stack_extents` and `stack_is_height_map` properties on the arch scenario),
the arch was re-run once per strategy: 3/3 pass, all three a standing arch.
This is n=1 per strategy, and it is contaminated: the new guidance contains
the arch's exact cube triples annotated cube by cube, so the re-run shows the
models can copy the example, not that they generalize the axis convention.
The two height-map scenarios were not re-run after ticket 11.

**TikZ.** Prism v1 was built with the renderer container down; TikZ criteria
were covered by assertions on generated TikZ text and by local `lualatex`
compiles (20/20 configurations). When the container returned, the full suite
ran with it up (3490 passed, 24 skipped at 997a002); the only failures were
four color-layer smoke tests whose regex did not accept dvisvgm's abbreviated
`#rgb` colors (a test bug). The stack lowering's container tests ran with the
container up. No exhaustive comparison of TikZ output across every view,
mode and style was done.

## Silent-corruption classes

"Silent" means the run passes the gate while the figure is wrong. Pipeline
warnings reach the retry prompt but never fail a run, and eval records do not
store them (`evals/run.py` has no warnings field), so a warning is invisible
in eval results. (Superseded 2026-10-16: records now carry `warnings` and
scenarios can gate on them, see the 2026-10-16 section.)

| Class | Seen in | What exists now |
|---|---|---|
| Numeric label on the wrong prism edge | run 1 | Pipeline warning (`prism.label_dimension_warnings`); never fails; not in eval records. Addressed 2026-10-16: warnings are recorded and a scenario can gate on them (see the 2026-10-16 section) |
| Unit-cube grid lost (faces drawn, not the prism id) | run 1 | Guidance plus a pipeline warning; not in eval records (superseded 2026-10-16: records now carry `warnings` and scenarios can gate on them, see the 2026-10-16 section) |
| `required_labels` skipped under SVG | run 1 | Fixed (db1a299) |
| Isometric expected, oblique drawn | runs 1, 2 | Recipe guidance only; no scenario check of `view` |
| Stray origin dot and label (recipe) | runs 1, 4 | Nothing |
| Unit word dropped ("6" for "6 units") | runs 2, 3 | Nothing; required labels are bare numbers by design |
| Label placement (free text over edges, bbox-center label on a stack) | runs 1, 4 | Nothing. Addressed 2026-10-16: label fields on the solids (see the 2026-10-16 section) |
| Stack y/z swap | run 4 | Arch scenario only: `stack_extents` + `stack_is_height_map` |
| Stack per-column heights wrong, same count and extents | not observed | Nothing (no per-column property) |
| CSS color names breaking TikZ | prompt examples | Fixed (3f0eae9) |
| Overlapping solids painted in the wrong order | design review | Advisory warning only |
| Model emits a solid on a non-solids prompt | not measured | Unknown |

## Known limitations

- **Overlap between solids is warn-only and bounding-box based**
  (`DerivedRegistry.overlap_warnings`, `screen_bounds` hooks). L-shaped or
  interlocking stacks can warn with no pixel overlap; solids are never
  depth-sorted against each other.
- **"Drawn" counts owned ids.** A `draw` or `fill` of any face, edge or column
  top face counts the whole solid as drawn for the overlap check, so a single
  shaded face brings in the full box; a draw of a hidden lattice id would also
  count (exotic).
- **pydsl warnings name hidden ids** such as `__pydsl_stack_3` or
  `__pydsl_prism_2`, which the model never wrote; the retry path has no
  translation back to script variable names.
- **The serialization guard covers only `model_dump` and `model_dump_json`**
  (`RenderTimeDiagram` in `ir/derived.py`). `TypeAdapter(DiagramIR)` dumps,
  `dict(view)`, pickling and `model_validate` of a view's contents remain
  open. No production path does any of these today.
- **`ir/derived.py` is about 830 lines** (836 at 22ff253) and `ir/prism.py`
  889. `prism.py` and `stack.py` use function-local imports of
  `checks.UnsupportedOperand` / `_near_exact` and of `derived.Lowering` to
  break the cycle checks -> derived -> prism. Suggested split (not done):
  move the hook dataclasses (`DerivedConstruction`, `Lowering`) and the shared
  check helpers into leaf modules that import nothing from the kind modules,
  which would let `prism.py` and `stack.py` import at top level.
- **Query-tool description texts are hand-maintained in four sites**:
  `strategies/structured.py` `QUERY_TOOL_SOLIDS_INSERTIONS` (shared with
  recipe), python_full's inline insertions, `facade.py`
  `_QUERY_DIAGRAM_SOLIDS_INSERTIONS`, and the table rows in `evals/run.py`.
  Each words the solids lines in its own layout; generating them from the
  registry would have required four phrasings per kind. Pinned by
  `tests/query_tool_descriptions_pre_solids.json` and the solids-on tests.
- **Two registry exceptions remain**: the recipe lowerer aliases a `segment`
  op that joins two corners of one prism edge (`_prism_edge_owner` in
  `recipe/lower.py`), and the pydsl builder reuses a prism edge for
  `segment()` (`pydsl/builder.py`, via `prism.edge_between`). Both use
  authoring-time state the registry cannot see. A `segment_alias` hook is the
  next step if a second solid needs edge reuse.
- **Angle checks on prism corners do not warn.** Only `distance_equals`,
  `equal_length` and `ratio_equal` emit the projection warning; perpendicular,
  right-angle and angle checks on prism geometry are as misleading but silent.
- **The pre-assert step cannot ground solid asserts.** With solids on it
  advertises `assert_volume` / `assert_true_length`, but its grammar cannot
  define a prism, so those proposals are always filtered.
- **(Fixed 2026-10-16.) The spec's pipeline-warnings list omits the label-dimension warning**
  (`docs/geometry-dsl-spec.md#pipeline-warnings`), although CLAUDE.md lists
  it.
- **Structured token usage is recorded as 0** in eval records, so cost
  comparisons across strategies are incomplete.

## Proposed path to enabling `solids` by default

An independent readiness-to-enable assessment concluded that the evidence
does not support default-on yet: no cell above n=3; the silent-corruption
classes above (wrong-edge labels warn but never fail and are not recorded;
isometric expected but oblique drawn; stray origin dot; units; label
placement; per-column heights); TikZ output not exhaustively verified in the
container on this branch; and no evidence on whether models emit solids on
non-solids prompts once the group is on.

Proposed plan (not executed):

1. Run the 8 solids scenarios plus held-out prompts (not the ones the
   guidance examples were written from) across 3 strategies x 3 models x 3
   repeats.
2. Run a solids ON vs OFF regression over the core and generalization
   scenarios, to see whether enabling the group changes non-solids results or
   makes models produce solids unprompted.
3. Run a TikZ container smoke test over the solids configurations.
4. Rollout: default-on only with an environment-variable kill switch, enabling
   python_full first.

The assessment estimated about $45 plus the luna runs for items 1-3. That
figure rests on pricing assumptions that were not verified; re-estimate
before running. Recording pipeline warnings in eval records, so that the
warn-only classes become measurable, would make the run far more informative.

## Adding a third solid

Reference: the module docstring of `geometry_diagrams/ir/derived.py` (every
hook, its consumer, and what is outside the registry) and
`tests/test_registry_toy_solid.py` (a toy solid registered without editing
any consumer, one test per hook). The second whole-branch review wrote its
own toy cylinder through the public API and it worked first time; these are
the points it found undocumented.

1. Add the IR classes in `ir/ir.py`: a `DefBase` subclass with a `Literal`
   `kind`, plus any `CheckBase` subclasses, and add them to the `DefStmt` /
   `Check` unions. This changes the structured JSON schema even with the
   group off; the prompt fixtures pin text, not schemas.
2. Write the kind module (compile to a non-SymPy object, query, checks,
   lowering) and register a `DerivedConstruction` with `feature="solids"`.
   Give it `object_type` whenever it has a `query`.
3. `id_forms` placeholders are free-form templates; nothing checks them
   against what `owned_ids` actually returns, so keep the two in sync by hand.
4. `check_warnings` and `label_away_from` are called for every check and
   every segment label in every diagram, so they must answer cheaply and
   return quickly for objects that are not theirs. `position` is asked of
   every kind, first non-None wins, so position hooks must be type-exact.
5. In tests, the registry is global: pair every `REGISTRY.register` with
   `REGISTRY.unregister` in a `finally`, and assert nothing is left behind.
   A test-only definition outside the unions must be appended after
   `DiagramIR` validation, and `builder.build()` re-validates, so the toy
   test reads recorded ops instead.
6. Outside the registry, still by hand: the recipe op and its lowering
   (`recipe/dsl.py`, `OP_FEATURES` / `CHECK_FEATURES`, `recipe/lower.py`),
   `refs._NON_REF_FIELDS`, the pydsl function, handle and asserts plus
   `pydsl.GROUPED_NAMES["solids"]`, the three gated prompt fragments with
   executable examples, the four query-tool description sites, the eval
   vocabulary (`_SOLID_KINDS` in `evals/run.py`, property types in
   `evals/scenarios.py` and `evals/sympy_checks.py`), and the spec section.
7. Keep solids-off prompts byte-identical (`tests/*_pre_solids.json`) and
   check byte-identity of all catalog recipes and existing solid fixtures with
   `PYTHONHASHSEED=0`.

## Deferred minor items

| Item | Where | Why deferred |
|---|---|---|
| `Builder._advance_sym` copies the symbol table per statement (O(n^2)) | `pydsl/builder.py` | Cheap at current script sizes |
| Effective view recomputed about six times per pipeline run | `ir/derived.py` consumers | O(n) and cheap; must stay a pure function |
| Corner-pair index lookups scan the symbol table | `ir/prism.py` | Fine at current sizes |
| `Prism.corner_segments` written but read only through a private map | `ir/prism.py` | The spec-named record; left as is |
| Unused `\definecolor` lines for some bare styles | `ir/to_tikz.py` | Output noise only |
| Tests reach `REGISTRY._by_kind` | several test files | Test hygiene |
| Skipped scenarios printed to stdout only, not in JSONL | `evals/run.py` | Visible at run time |
| `solid_count` with `min: 0` always passes | `evals/run.py` | Author error, documented |
| Prism-edge labels ignore `pos` in SVG but honor it in TikZ | `ir/to_svg.py` | Pre-existing generic SVG behavior |
| "very thick" / "ultra thick" not carried into ordered-polygon strokes | `ir/stack.py` | SVG ordinary draws ignore them too |
| Lax `expected` coercion in `cube_count_equals` (`True`, `"7"`) | `ir/ir.py` | Pydantic lax mode; rare |
| Eval help text does not list `stack_extents` / `stack_is_height_map` | `evals/run.py` | Help text only |
| `scenarios_solids.yaml` stack header says the arch checks cube count only | `evals/scenarios_solids.yaml` | Comment predates the extents properties |
| Remedy text in the degenerate-view error is conservative, not the exact threshold | `ir/prism.py` | Advice, not a contract |
| Fill of a column top id is hidden under the opaque drawn stack | `ir/stack.py` lowering | Fills hoist behind ordered polygons by design |

## 2026-10-16: label placement follow-up (branch feat/solid-label-placement)

**Diagnosis.** In the latest luna rerun every strategy drew correct prisms
but the dimension labels were wrong or messy, and nothing caught it. Cause
found by running the code: our own guidance named a HIDDEN edge. It told
models the width (depth) edge is `P_e_000_001`, but for the default `side:
"right"` views the hidden corner is `001` (back-bottom-left) and every edge
touching it is hidden, so structured and recipe put the depth label on an edge
that is not on the silhouette (left of the figure or inside the face).
Silhouette edges, per `side` (the hidden corner `h` comes from the projection;
the same in oblique and isometric views):

| Dimension | `side: "right"` (hidden corner `001`) | `side: "left"` (hidden corner `101`) |
|---|---|---|
| length (front bottom) | `e_000_100` | `e_000_100` |
| height | `e_000_010` | `e_100_110` |
| width (depth) | `e_100_101` (`e_000_001` is hidden) | `e_000_001` (`e_100_101` is hidden) |

python_full named the visible width edge but duplicated every label (a bare
number on the edge plus a detached free text); recipe free-text labels were
placed by guessed coordinates and drifted; the stack total sat at the bounding
box center, straddling cube edges.

**What changed.**

- Guidance fix: all three surfaces now name the silhouette edge per side
  (pinned by `tests/test_solid_guidance_edges.py`).
- Label fields: `length_label`, `width_label`, `height_label`,
  `base_area_label` on the prism and `count_label` on the stack, on the IR
  definition, the recipe ops and pydsl `prism()` / `stack()`; text verbatim.
  The solid places them itself on the silhouette edge (or the base centroid, or
  above the stack), once, when drawn.
- Registry hook `lower_labels` in `ir/derived.py`: called once per drawn
  authored solid by `lower_render`, which now takes the compiled symbol table
  (`lower_render(diagram, sym, warnings=None)`); "drawn" uses the overlap
  advisory's rule (`DerivedRegistry.drawn_ids`).
- The label-dimension warning also checks the three dimension fields; the
  spec's pipeline-warnings list now lists it (this closes the omission noted
  under Known limitations).
- Evals: every record stores `warnings`; a scenario's `fail_on_warnings`
  adds a `warning:<substring>` gate failure per matching substring; the five
  prism scenarios gate on `does not match its true length`. This is the
  "record pipeline warnings in eval records" step proposed above for the
  warn-only classes, for this one class.

**Open limits (accepted).**

- TikZ renders a dimension label (a `label_segment`) in math mode (italic,
  spaces collapse); `^` in the plain-text `base_area_label` / `count_label`
  (e.g. "cm^2") is a LaTeX error in TikZ. SVG is unaffected.
- The warning reads the first number in the text, so "7/2" or "3 1/2 in"
  falsely warns (fraction text must be avoided in gated scenarios); a
  wrong-number field warns even if the solid is never drawn.
- A top-face-only `fill` (or a draw/fill of any owned id) counts as drawing
  the solid and so emits all of its labels.
- The stack label sits above the lattice's bounding box, not the silhouette
  (it floats higher over short columns of an uneven stack), and its 0.5-unit
  margin is a construction-unit gap whose pixel size shrinks on wide canvases.
- `base_area_label` on a solid prism reads over the front face (the base is
  hidden) and can cross edges or another label on extreme shapes (20x1x1 at `depth_angle`
  80, 1x1x20 at `depth_scale` 1.5) or sit partly outside a narrow base.
- Setting a field and also labelling the same edge by hand gives two labels
  (no de-duplication).
- Whitespace-only `fail_on_warnings` entries are accepted and match almost any
  warning.

**Limits of the verification evidence.** The post-change luna run is n=1 per
cell, one model (gpt-6-luna), judge off, and every prism cell is oblique `side:
right`: side-left and isometric label placement was exercised by tests and a
216-case placement sweep, not by model runs. The gate has no
outside-the-silhouette placement check; placement was verified by eyeballing
and tests. The 23/24 gate pass of this run against the earlier 14/15 is not a
before/after comparison: the one failing cell (structured drawing a block stack
for the unit-cubes prompt) predates this change.

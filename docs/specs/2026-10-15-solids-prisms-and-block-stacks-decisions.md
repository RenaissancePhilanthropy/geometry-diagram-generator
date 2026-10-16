# Solids (Rectangular Prisms and Block Stacks): Decision Record

Durable copy of the design decisions, rulings and measurements behind the
`solids` feature group on branch `feat/solids-prisms` (unmerged as of
2026-10-15, HEAD 22ff253). The working records (specs, tickets, ledgers,
review reports under `.scratch/solids/` and `.scratch/block-stacks/`) are
being deleted; this file keeps what a maintainer needs to understand why the
code is shaped the way it is. Evidence, open items and the extension
checklist are in the companion file
`docs/specs/2026-10-15-solids-evidence-and-follow-ups.md`.

The schema and behavior reference is `docs/geometry-dsl-spec.md`; this file
does not repeat it. Relevant sections there:
[`rectangular_prism`](../geometry-dsl-spec.md#rectangular_prism),
[`block_stack`](../geometry-dsl-spec.md#block_stack),
[Color forms](../geometry-dsl-spec.md#color-forms),
[SVG viewBox growth for labels](../geometry-dsl-spec.md#svg-viewbox-growth-for-labels),
[Ordered polygons](../geometry-dsl-spec.md#ordered-polygons),
[Pipeline warnings](../geometry-dsl-spec.md#pipeline-warnings).

## Problem and scope

Curriculum items (counting with blocks, volume) show three looks of a
rectangular prism: unit-cube prisms in an isometric view, solid shaded prisms
with labeled dimensions in an oblique view, and oblique wireframes with dashed
hidden edges and a shaded, labeled base. The reference folder had 10 items
(identifiers omitted). Before this work an
author could only fake a prism with hand-placed projected points: nothing
recorded "this is a 2x4x5 prism", a length check on a receding edge silently
measured the 2D projection, evals could not tell a prism from a pile of
polygons, and most strategies could not draw one at all.

A second, older problem: constructions that create extra named entities
(regular polygon on an edge, polygon on an edge, tangent circle center) were
special-cased in several places that had drifted apart, and dependents
tracking attributed none of their derived ids to an owner.

Scope delivered, in two phases on the same branch:

1. Prism v1 (solids tickets 01-18): derived-entity registry, effective
   definitions view, pipeline warnings list, color layer, label grow-to-fit,
   the `rectangular_prism` kind with queries/checks, the three strategy
   surfaces, eval support, and feature gating.
2. Block stacks (solids ticket 19, the `OrderedPolygon` primitive, then
   block-stacks tickets 01-14): the `block_stack` kind (height map or cube
   set), painter-ordered rendering, `cube_count_equals`, the three surfaces,
   eval properties, and three post-review design calls (registry hooks, overlap
   warning, serialization guard).

## Core design

**Derived-entity registry** (`geometry_diagrams/ir/derived.py`). One entry per
definition kind (`DerivedConstruction`) declares the ids it owns, how they are
registered into the symbol table, what it synthesizes, how a draw of it
lowers, its position, and its feature group. The module docstring lists every
hook and its consumer, and what is deliberately left outside the registry. The
three existing constructions were migrated first with no behavior change (the
existing suite was the safety net), then the prism became the fourth user and
the stack the fifth. Why: a fourth hand-rolled copy of the "construction owns
extra entities" pattern would have repeated the drift, and dependents tracking
needed an owner map anyway.

**Effective definitions view** (`effective_defs` / `effective_diagram` in
`derived.py`). Authored definitions plus synthesized ones (a prism's 12 edges
and 6 faces, unit-cube gridlines, a stack's column top faces), computed as a
pure function of the authored IR and never written back. Compile, both
renderers, bounds/helpers and linear-pair resolution read it; edit
diagnostics, eval IR diagnostics, auto-checks and dependents tracking read
`diagram.define`. Why: no provenance field in the schema (nothing for a model
to spoof), metrics such as `polygon_count` automatically exclude derived
definitions, and no entry point can bypass expansion. Synthesized definitions
carry a private, never-serialized marker (`DefBase._synthesized_by` in
`ir/ir.py`) so the view is idempotent. An authored id equal to a derived id is
a typed `IRCompileError`, never a silent shadow (an early version silently
dropped the synthesized definition, so mid-script and final compiles in pydsl
disagreed).

**Projection as a linear map plus viewer direction** (`ir/prism.py`,
`projection_for`). A view maps the three axes (length, height, width) to 2D
vectors; the viewer direction is the kernel of that map, signed so the top is
visible. Visible faces, the hidden corner, and the stack painter order are all
derived from it, never tabulated per view. The constants are exact SymPy
values (`OBLIQUE_DEFAULT_SCALE = sp.Rational(1, 2)`, 45 degrees with
`cos = sin = sqrt(2)/2`) because floats leak 16-digit rationals into SymPy.
The same vocabulary holds in both views (origin = front-bottom-left; length
along the front bottom edge, width along the right bottom edge, height up),
so prompts do not change per view. Why: the reference art turned out to mix
isometric and oblique figures (an early assumption of "one oblique view" was
wrong), so the view had to be a parameter, and a derived rule is testable for
every configuration while a table is not.

**Prism and stack as non-SymPy symbol-table objects.** `Prism`
(`ir/prism.py`) and `Stack` (`ir/stack.py`) hold true dimensions, volume or
cube count, and projected points. "SymPy is the source of truth" is relaxed
only for these registered types, and consumers reach them through registry
hooks (`compile`, `object_type`, `query`, `evaluate_checks`, ...), not
`isinstance`. True 3D length is keyed by the endpoint ids of any segment
joining two corners of one prism, recorded at compile (registry `index`
hook), never by coordinates: two corners can project to the same 2D point for
crafted dimensions.

**Lattice ownership for stacks.** A stack's lattice points are owned ids
registered directly into the symbol table as SymPy points with hidden
`__{id}_l{x}_{y}_{z}` ids, not synthesized `PointBetween` definitions. Why:
the origin can be any point (so coordinates are not fixed at synthesis time),
and a chain of roughly 1500 synthesized definitions would be recompiled
several times per run (the effective view is recomputed about six times per
pipeline run). Only the column top faces are synthesized polygons.

**Painter-ordered `OrderedPolygon` lowering** (`ir.OrderedPolygon`,
`stack.painter_faces`, `stack.lower_draw`). Cubes are sorted by the dot
product of the cube center with the viewer direction (farthest first, ties by
coordinates), and each cube emits its faces on the three visible planes,
culled when the neighbouring cell is occupied. A new op was needed because
both renderers hoist every fill before every stroke (`_Z_ORDER` in `to_svg.py`
and the same kind sort in `to_tikz.py`), so with ordinary `fill` + `draw` the
outlines of far faces show through near fills. Plain prisms do not need it:
with hidden faces culled, a box's exterior faces never overlap. The ordering
argument (if cube A can hide cube B, every nonzero component of A - B has the
sign of the matching viewer component) needs every viewer component nonzero,
which `projection_for` guarantees. An early fixture's sort key `(x + y - z)`
was valid only for `side: right`; the real key comes from the viewer.

**Color layer** (`ir/render_util.py`: `parse_color`, `svg_color`,
`tikz_color`). Parsed once, emitted natively per backend; unrecognized strings
pass through with a renderer warning. Why: an xcolor mix such as `cyan!55`
painted solid black in SVG while TikZ rejected hex, and the stack needs
opaque tints (opacity would let hidden faces show through).

**Label grow-to-fit** (`to_svg.py`, `_MAX_LABEL_GROWTH_PX = 200.0`). The SVG
viewBox grows, preserving scale, only when a label overflows, so diagrams
without overflow stay byte-identical.

**Pipeline warnings** (`strategies/ir_pipeline.py`). A `warnings` list on the
result and on `PipelineError`, shown in the next retry prompt, never a failure
or a retry trigger by itself. Why: compile and checks had no non-fatal channel,
and several solid-specific problems (projection measured, skewed canvas,
unit-cube grid not drawn, label contradicting a dimension, overlapping
solids) are worth telling the model about but not worth failing a run.

**Feature gating, generation only, off by default** (`geometry_diagrams/features.py`).
The `solids` group gates prompt fragments, pydsl names (including inside the
sandbox subprocess, which receives the enabled set explicitly), recipe
parsing, query-tool description lines, and a post-parse `require_features`
rejection. Compile and render always accept every kind, so stored diagrams
stay portable. The structured and recipe schemas are static and cannot hide a
kind, so rejection plus prompt text is the gate. With the group off, every
prompt is pinned byte-identical by `tests/*_pre_solids.json`. Off by default
because the eval evidence does not yet support enabling it (see the companion
file).

## Rulings and design calls

Condensed from the two ledgers. "Cost if wrong" is what the ruling accepted.

1. **Gate placement.** `require_features` is called by each IR-producing
   strategy before `run_ir_pipeline`, not inside it, because moving it would
   have changed existing tests' mocks. Mitigation: a documented contract in
   `features.py` and the strategy base class plus a parametrized regression
   test in `tests/test_feature_gating.py`. Cost: a future strategy can forget
   the call.
2. **No speculative warnings parameter.** The warnings channel was added only
   where a producer existed (`run_checks(warnings=...)` arrived with the
   projection warning). Cost: later tickets touched signatures.
3. **200 px growth cap kept.** A label more than 200 px off-canvas almost
   always signals a generation mistake; leaving it flagged keeps the
   label-bounds retry useful. Cost: a legitimately far label retries until
   moved.
4. **Solid look = fill and draw the visible face ids, not the prism id**
   (drawing the prism id strokes dashed hidden edges over fills). The first
   eval run showed this guidance dropped unit-cube gridlines, so it was
   narrowed to non-unit-cube prisms, and a unit-cube prism whose id is never
   drawn now warns. Cost: models may still draw faces of a unit-cube prism;
   the warning is advisory.
5. **Projection warning fires unconditionally** when `distance_equals` /
   `equal_length` / `ratio_equal` measures a prism-corner segment, even where
   the drawn length equals the true length (front edges, isometric edges).
   Cost: noisy warnings on correct checks. Angle checks on prism corners do
   not warn (backlog).
6. **Query-tool description lines gated on `solids`** (the spec's "prompt text
   unchanged until opt-in" overrode the ticket). Cost: the facade's
   `query_diagram` tool is built at import and reads `GEOMETRY_FEATURES` then,
   so a per-call feature override cannot change its description (documented).
7. **Unit-cube dimensions capped at 100 each** (`UNIT_CUBE_MAX_DIM`). The
   reference maximum is 11; without a cap a hallucinated huge literal would
   hang generation. Cost: a legitimate larger counting figure is rejected,
   with a message pointing to wireframe mode.
8. **Bare color style keys honored in both backends.** `Fill(style="red")`
   used to paint blue in SVG and `blue!20` in TikZ; it now paints red in both
   (a deliberate output change for hand-written IR); bare `none` is excluded.
   Cost: a stored diagram relying on the old color changes.
9. **Solids-off prompts are not byte-identical to master.** The color-form
   guidance lines (not gated; independent of solids) changed default prompts
   for everyone, and the `*_pre_solids.json` fixtures pin the post-color
   text. Accepted and flagged to the user.
10. **No per-look prism default.** Solid vs wireframe is a draw-time
    distinction, so the 1/2 depth scale stays the default and guidance tells
    authors to pass `depth_scale` 2/3 for wireframe-like figures.
11. **Stack position = center of the silhouette's bounding box.** For a
    concave stack it can fall in an empty notch; column top-face ids are the
    way to place a label on a column. Cost: a whole-stack label may sit off
    the mass; switching to an area centroid is a one-function change.
12. **TikZ ordered-polygon stroke = tkz-euclide's `line style`**, not the
    spec's assumed 0.4 pt, because ordinary tkz draws measure 0.2 pt and faces
    must match ordinary draws.
13. **Cube-set guidance must show a real overhang** (the arch), not a set a
    height map can express; and after a model swapped y and z, the `[x, y, z]`
    axis convention is stated on all three surfaces with an explicit "never
    swap y and z" line, backed by `stack_extents` / `stack_is_height_map` eval
    properties.
14. **Degenerate oblique views fail at compile**: `projection_for` evaluates
    the viewer eagerly, so `depth_scale * sin(depth_angle)` below 1e-12 is a
    typed `IRCompileError` instead of an uncaught `ValueError` at render.
15. **Errors in synthesized definitions name the owner.**
    `compile_one_attributed` (`ir/to_sympy.py`) is shared by `compile_defs`
    and the pydsl builder, so the model sees the id it wrote (e.g. `P` or
    `__pydsl_prism_2`) rather than `P_front`.
16. **Parked residuals of the recipe edge alias**: a `segment` op written
    before its prism op is not aliased (extra stroke over a hidden edge); a
    `draws` list naming both the prism and the aliased segment strokes the
    edge twice. Cosmetic, never a failure.

Design calls made by the user after the three post-final independent reviews
(block-stacks ledger, "DESIGN CALLS"):

- **D1. Overlapping solids: warn only.** Solids are not depth-sorted against
  each other; a render warning ("draw order is not depth order") fires when
  two drawn solids' screen bounding boxes overlap with positive area. A later
  review found the motivating case (a face-shaded prism next to a stack)
  slipped through, so "drawn" now means a `draw` or `fill` names the solid's
  id or any id it owns. Cost: bounding boxes are conservative and can warn
  without pixel overlap.
- **D2. No per-diagram resource budget.** Per-definition caps and existing
  timeouts only; slowness of extreme diagrams (on the order of 50 stacks or
  10 unit-cube prisms in one diagram, per the review) is accepted.
- **D3. `OrderedPolygon` stays outside the `RenderOp` union**, so it can never
  be authored, plus a guard: lowered and effective diagrams are
  `RenderTimeDiagram` instances whose `model_dump` / `model_dump_json` raise
  `TypeError`, and `render_view` rejects a non-`DiagramIR`.
- **D4. Registry hooks added now**, not when a third solid arrives: compile,
  object type, query, true length, check evaluators, check warnings, label
  placement, pipeline warnings, canvas extent, trusted faces, and later
  screen bounds. A test-only toy solid (`tests/test_registry_toy_solid.py`)
  proves each consumer reaches a new kind with no consumer edit.
- **D5. The `cubes` input is kept** alongside `heights`.

## Measured facts that drove decisions

- **Oblique default 45 degrees at depth scale 1/2.** Sub-pixel line fits on
  outline edges of the four oblique reference figures gave a receding angle of
  44.2-45.1 degrees (mean 44.7; fit error under 0.09 px per edge). Depth
  scale 0.499 on the only oblique figure that states its depth (11
  units drawn as 5.49). The three wireframe figures state no depth and imply
  about 0.65-0.69 (inferred, assuming the front face is to scale; not
  measured). Proportional depth is "consistent with the references, moderate
  confidence" (one direct data point). The provisional 9/20 was eyeballed;
  the earlier 30 degrees looked too shallow. No reference figure recedes to
  the left, so `side: left` is unexercised by the data.
- **TikZ stroke 0.2 pt.** Measured in the container (dvisvgm
  `stroke-width='0.2'`) and in a local TeX Live 2024 config.
- **Caps: 400 cubes, 20 cells per axis** (`MAX_CUBES`, `MAX_CELLS_PER_AXIS`
  in `ir/stack.py`), confirmed by measurement: after the top-face change a
  20x20 height-1 stack runs pipeline+SVG in 0.11-0.44 s (77 KiB SVG, 440
  faces) and the worst face count, a 20x20 height-2 checkerboard (400 cubes,
  1000 faces), in 0.58 s oblique. Unit-cube prisms: 100x100x100 gives 1505
  effective definitions and compiles in 0.54 s (definition count grows
  linearly, about 2(L+W+H) segments plus as many points).
- **20x20 flat stack time and why top faces skip SymPy validation.** Before
  the change, a 20x20 height-1 stack took 8.6 s in `compile_defs` and 26 s
  through the pipeline. The cause was `spg.Polygon`'s constructor simplifying
  every collinearity triple on exact radical coordinates. A lattice unit
  square under a non-degenerate projection always has four distinct,
  non-collinear vertices, so the stack's synthesized top faces are built
  without validation (`_trusted_polygon` in `ir/to_sympy.py`, enabled by the
  registry's `trusted_faces` flag; authored polygons can never take this
  path). A second cost, `check_render_angles` building linear pairs with no
  angle ops present, was removed by an early return (58 s to 0.74 s for the
  case with an angle mark). The independent final review measured the 20x20
  flat stack at 0.15 s.
- **Culling.** The painter prototype grid (22 cubes) draws 35 faces with
  culling and 66 without; output is identical.

## Process, as far as it explains the code

Each ticket was implemented by a fresh subagent, then reviewed (spec and
quality), with fix rounds; each phase ended with a two-axis whole-branch
review and one fix wave. Consequences visible in the code:

- Byte-identity checks before and after every risky refactor (all catalog
  recipes plus prism and stack fixtures, run with `PYTHONHASHSEED=0` because
  the dependency sort iterates string-keyed sets).
- Executable guidance: prompt examples live in constants
  (`PRISM_EXAMPLES`, `STACK_EXAMPLES` in `recipe/catalog.py`, the python_full
  and structured example scripts/IR) and tests run them through the pipeline.
  This found a real bug: the recipe guidance's space-diagonal `true_length`
  example (5.39) would have failed the near-exact check.
- The TikZ container was down for most of prism v1; TikZ criteria were
  covered by text assertions and local `lualatex` compiles, then run in the
  container later (see the companion file).
- Fixture-pinned solids-off prompts, verified against the base commit in a
  scratch worktree.

## Out of scope (deliberately)

- Other viewpoints, a free-form viewer direction, composite or
  non-rectangular solids (L-shapes, triangular prisms), nets.
- True occlusion between separate solids (warn-only overlap instead, D1).
- 3D-aware generic checks (parallel, perpendicular, right angle, equal
  length, distance) on prism or stack geometry.
- Per-column and per-layer stack queries; non-unit cubes; expressions in
  `heights`/`cubes`; transparency.
- TikZ label fixes (math-mode words in `label_segment`, fonts, collisions on
  dense stacks) and TikZ label nudging.
- Hiding solid kinds from the structured/recipe static schemas.
- Folding the experimental cookbook flag into a feature group.
- Enabling `solids` by default.

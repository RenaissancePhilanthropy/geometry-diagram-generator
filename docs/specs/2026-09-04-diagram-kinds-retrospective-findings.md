# Diagram-Kinds PoC: Retrospective Findings

Five implementer subagents from the `diagram-kinds-poc` feature (branch:
`diagram-kinds-poc`) were interviewed after their tickets closed, using the
protocol in `docs/retrospective-template.md`. Their answers converged
independently on one dominant gap and surfaced two smaller, well-scoped
findings. Not yet acted on — this is a findings record, not a spec.

## Dominant finding: no way to verify a label's rendered position before finishing

Raised independently by four agents, in four different tasks:

- **The `prism_net`/`work_table`/`l_prism` round-2 refinement agent**, after
  two failed attempts to fix `prism_net`'s crowded labels: *"I compute label
  positions by hand-rolled coordinate arithmetic and have no feedback loop
  telling me whether a placement actually landed inside the rendered
  canvas... 'looks safely inside my mental margin' and 'actually inside the
  rendered SVG' silently diverge."* Proposed either an `assert_all_labels_within_canvas()`
  check (raising with the offending label's text + position) or a plain
  `canvas_bounds() -> (xmin, xmax, ymin, ymax)` query. Explicitly generalized
  this beyond nets: *"the same 'hand-rolled layout math with no way to verify
  it before rendering' pattern is exactly what caused `area_model`/
  `attribute_chart`'s original defects... and is related to `scatter_plot`'s
  known-gap clipping issue too."*

- **The ticket 07 baseline agent**, re-examining its 5 partial-verdict kinds
  with the raw SVGs in front of it: 4 of 5 (`area_model`, `coordinate_plane`,
  `scatter_plot`, `shape_comparison`) shared one root cause — *"the script
  gets the geometry/math right but computes a label's screen position
  without accounting for the label's own rendered footprint relative to
  canvas bounds or a neighboring region."* Concrete examples: `area_model`
  reused one row-midpoint x-coordinate for two column-specific labels;
  `coordinate_plane`'s caption sat at x=45 with `text-anchor="middle"`,
  running off the left edge. Proposed `assert_labels_in_canvas()` (extending
  the existing `assert_in_canvas`, which today only checks points/geometric
  objects, not rendered text bboxes) and/or a `label_text_width(s,
  font_size) -> float` query callable before anchoring a label near a cell
  boundary. Framing: pydsl's primitives are geometry-first, but kinds like
  `attribute_chart`/`area_model`/`scatter_plot` are table/chart-layout
  problems "wearing geometry clothing" — a couple of worked examples in the
  prompt might fix this cheaper than new primitives, for some kinds.
  (The 5th kind, `attribute_chart`'s original defect, was pure
  duplication/copy-paste, unrelated to this pattern.)

- **The `table_grid` (ticket 11) helper-author agent**, reflecting on
  building `table_grid`/reading the other 6 cookbook helpers as precedent:
  *"there's no way for a helper (or a script) to query rendered text extent
  ... `to_svg.py`'s label-nudging system computes bbox estimates internally
  but that's never exposed to pydsl"* — and separately, no canvas-bounds
  query either, so *"every grid-shaped helper pushes extent bookkeeping back
  onto the calling script."*

- **The ticket 13 final-gallery agent**, on the `scatter_plot` known gap
  (see below) — implicitly the same family of gap (the renderer computing a
  fixed layout with no way for the script to check it fits).

**Convergent proposal**: some combination of (a) a rendered-text-extent
query, (b) a canvas-bounds query, (c) a pre-finish assertion that raises on
any label whose rendered bbox falls outside the canvas. Not yet decided
which shape is right, or whether it's a `pydsl` addition, a `checks.py`
addition, or both.

## Finding 2: independent x/y canvas scaling (`scatter_plot` known gap)

From the ticket 13 agent, having traced `to_svg.py`'s `ir_to_svg()`: it
computes one uniform `scale = usable / max(geo_w, geo_h)` shared by both
axes — correct for classical geometry (angles/right-angles need equal
scaling to look right), but wrong for a chart whose x-range and y-range are
wildly different magnitudes (e.g. `scatter_plot`'s 0-8 hours vs. 0-100
score), which always renders as a tall, narrow strip no matter how the
prompt is worded.

**Proposed fix**: an optional `canvas(..., preserve_aspect: bool = True)` (or
`aspect="auto"`) parameter. When `False`, `to_svg.py` would compute
`scale_x = usable_w/geo_w` and `scale_y = usable_h/geo_h` independently —
point data stays exact, only the pixel mapping changes. Opt-in per kind:
`scatter_plot`/`bar_graph`-style kinds would use it; `coordinate_plane`/
`circle`-style kinds would keep the default. One concrete in-script
workaround was identified but not verified: padding the x-range via
`canvas(x_range=...)` to force `geo_w > geo_h` and flip the shared scale
toward landscape — wastes canvas as blank margin, untested.

## Finding 3: generalize `equation_steps()` into a general line-stacking helper

From the ticket 13 agent, on why `shape_comparison` took 3 attempts instead
of 1: both failed attempts wrapped a 2-line summary with y-offsets too close
together, overlapping — a hand-placed `label_text()` bug, not a prompt
problem (asking for "more margin" didn't change how the script computed the
offset). `equation_steps()` (from tickets 05/06) already solves exactly this
— stacking N lines with a correct, collision-free `y_step` — but is framed
as algebra-specific. Generalizing it (or exposing its stacking logic as a
standalone helper) would likely have fixed this class of bug on the first
attempt, since it removes the hand-rolled vertical-offset arithmetic
entirely rather than asking the model to get it right by hand.

## Finding 4 (implementation-side): duplicated span-partitioning math

From the `table_grid` (ticket 11) agent, comparing its work to the other 6
cookbook helpers: `table_grid`'s cumulative-sum cell-boundary logic,
`unit_grid`'s uniform-cell logic, and `bars`'s 1D offset logic are three
independent reimplementations of "partition a span into N segments with
given sizes, return edges/centers." A shared, undrawn coordinate-math
primitive underneath the grid/bar/table cluster would remove the
duplication — this also matches what the whole-branch Standards review
(during `subagent-execution`) flagged independently as a baseline smell.

## Status

Findings only — nothing here has been spec'd or ticketed yet. See the
`diagram-kinds-poc` feature's own `.scratch/` (if it still exists) for the
full session history these were extracted from; this file is the durable
copy meant to survive that directory's deletion.

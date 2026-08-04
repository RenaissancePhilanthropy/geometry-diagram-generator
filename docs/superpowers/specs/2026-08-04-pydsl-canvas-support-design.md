# pydsl Canvas/Grid Support — Design

## Problem

pydsl scripts have no way to request a grid or axes, or to set explicit
canvas bounds. `Builder.build()` (`geometry_diagrams/pydsl/builder.py`)
hardcodes `canvas=None` on every `DiagramIR` it produces.

This isn't a missing feature at the IR/renderer level. `ir.Canvas`
(`geometry_diagrams/ir/ir.py`) already has `xmin`/`xmax`/`ymin`/`ymax`,
`grid`, `grid_step`, `axes`, `tick_step`, `show_ticks`, `show_tick_labels`,
`show_axis_labels`, and `clip`. Both `to_tikz.py` and `to_svg.py` already
render all of it — critically, grid lines render with styling visibly
distinct from ordinary drawn geometry (`to_svg.py`'s `_append_grid`:
`stroke="#ccc"`, `stroke-width="0.5"`, vs. the default black stroke used
for triangles/segments/etc.). The recipe DSL already exposes a subset of
this via `CanvasOp` (`geometry_diagrams/recipe/dsl.py`), lowered directly to
`ir.Canvas` in `geometry_diagrams/recipe/lower.py`.

This gap is not hypothetical. Running the new `python_full` strategy (pydsl)
against two real models (`anthropic:claude-sonnet-4-6`,
`openai:gpt-5.6-luna`) on a scenario needing a coordinate grid, both models
hand-built a "grid" out of dozens of individual `segment()`/`line_through()`
calls, drawn in the exact same stroke as the actual triangle — there is no
visual way to tell the grid apart from the geometry it's supposed to be a
backdrop for. This is exactly what `ir.Canvas`'s grid rendering already
solves; pydsl scripts simply can't reach it.

## Non-goals

- No IR or renderer changes — every field this plan exposes is already
  defined in `ir.Canvas` and already rendered by both `to_tikz.py` and
  `to_svg.py`.
- No auto-fit-plus-grid mode. When `diagram.canvas` is not `None`, both
  renderers compute bounds by starting from the canvas's own
  `xmin`/`xmax`/`ymin`/`ymax` and only *growing* the box to include any
  geometry that falls outside it — they never shrink below the canvas's
  specified bounds (`to_svg.py`'s bounds computation, `to_tikz.py`'s
  equivalent `expand only when computed points fall outside the LLM's
  canvas bounds` comment). `recipe/lower.py`'s `_auto_canvas()` *does*
  compute an auto-fit `Canvas` for the DSL path when no `CanvasOp` is
  given — but it hardcodes `grid=False`; there's no path anywhere in the
  codebase today that auto-fits bounds AND shows a grid. The recipe DSL's
  own `CanvasOp` requires explicit `x_range`/`y_range` for exactly this
  reason. This plan mirrors that: `canvas()`'s bounds are required, not
  optional — building an auto-fit-with-grid mode would need new logic in
  both renderers, out of scope here.
- No `clip` exposure. `ir.Canvas.clip` defaults to `True`, which is the
  sensible behavior; nothing in this plan's motivating cases needs it
  overridden. (`ir.Canvas.kind` is also left untouched — it's a
  fixed `Literal["cartesian"]` with no other value to set.)

## API surface

One new top-level function in `api.py`, following the same pattern as
`draw()`/`mark_angle()` — it records configuration rather than returning a
handle:

```python
_TARGET_LINES = 10        # nice-step heuristic aims for roughly this many grid/tick lines
_MAX_GRID_LINES = 500     # backstop for an explicit override, not the common path


def _nice_step(span: float, target_lines: float = _TARGET_LINES) -> float:
    """Round span/target_lines up to a 'nice' number: 1, 2, or 5 times a power
    of 10 — the same heuristic chart libraries use for axis tick spacing.
    E.g. span=8 -> 1.0; span=500 -> 50.0; span=1000 -> 100.0."""
    if span <= 0:
        return 1.0
    raw = span / target_lines
    magnitude = 10 ** math.floor(math.log10(raw))
    residual = raw / magnitude
    if residual < 1.5:
        nice = 1
    elif residual < 3:
        nice = 2
    elif residual < 7:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


def canvas(
    x_range: "tuple[float, float] | list[float]",
    y_range: "tuple[float, float] | list[float]",
    grid: bool = False,
    grid_step: "float | None" = None,
    axes: bool = False,
    tick_step: "float | None" = None,
    show_ticks: bool = False,
    show_tick_labels: bool = False,
    show_axis_labels: bool = False,
) -> None:
    """Set canvas bounds and optional grid/axes styling for the diagram.
    Call at most once per script. grid_step/tick_step default to an
    automatically chosen 'nice' number (1, 2, 5, 10, ...) based on the
    canvas size if not given. Note: if axes=True, the displayed bounds
    expand to include the origin even if x_range/y_range don't."""
    from geometry_diagrams.ir.ir import Canvas as CanvasDef

    builder = get_builder()
    if builder._canvas is not None:
        raise ValueError(
            "canvas() was already called once in this script — only one call is allowed"
        )
    xmin, xmax = x_range
    ymin, ymax = y_range
    if xmin >= xmax:
        raise ValueError(f"canvas(): x_range must satisfy x_range[0] < x_range[1], got {list(x_range)!r}")
    if ymin >= ymax:
        raise ValueError(f"canvas(): y_range must satisfy y_range[0] < y_range[1], got {list(y_range)!r}")
    if grid_step is not None and grid_step <= 0:
        raise ValueError(f"canvas(): grid_step must be > 0, got {grid_step!r}")
    if tick_step is not None and tick_step <= 0:
        raise ValueError(f"canvas(): tick_step must be > 0, got {tick_step!r}")

    span = max(xmax - xmin, ymax - ymin)
    effective_grid_step = grid_step if grid_step is not None else _nice_step(span)
    effective_tick_step = tick_step if tick_step is not None else _nice_step(span)

    if grid:
        n_grid_lines = (xmax - xmin) / effective_grid_step + (ymax - ymin) / effective_grid_step
        if n_grid_lines > _MAX_GRID_LINES:
            raise ValueError(
                f"canvas(): grid_step={effective_grid_step!r} over this range would draw "
                f"~{int(n_grid_lines)} grid lines (limit {_MAX_GRID_LINES}) — use a larger grid_step"
            )
    if show_ticks or show_tick_labels:
        n_tick_lines = (xmax - xmin) / effective_tick_step + (ymax - ymin) / effective_tick_step
        if n_tick_lines > _MAX_GRID_LINES:
            raise ValueError(
                f"canvas(): tick_step={effective_tick_step!r} over this range would draw "
                f"~{int(n_tick_lines)} ticks (limit {_MAX_GRID_LINES}) — use a larger tick_step"
            )
    builder._canvas = CanvasDef(
        xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax,
        grid=grid, grid_step=effective_grid_step,
        axes=axes, tick_step=effective_tick_step,
        show_ticks=show_ticks, show_tick_labels=show_tick_labels,
        show_axis_labels=show_axis_labels,
    )
```

`x_range`/`y_range` have no defaults — bounds must be explicit; both tuples
and lists work (LLM scripts write both interchangeably, and nothing here
relies on tuple-specific behavior — the function only unpacks and indexes).
`grid`, `axes`, `show_ticks`, `show_tick_labels`, `show_axis_labels` mirror
`ir.Canvas`'s own defaults exactly (all `False`). `grid_step`/`tick_step`
diverge from `ir.Canvas`'s literal default (`1.0`) by design — see below.

**`grid_step`/`tick_step` default to `None`, auto-computed via `_nice_step`,
each independently** — this is the actual fix for the density problem, not
just a guard against it. A first draft of this spec defaulted both to
`ir.Canvas`'s literal `1.0` and relied entirely on a hard reject
(`_MAX_GRID_LINES`) to catch bad requests; the concern raised in review was
that a fixed cap is the wrong shape of fix — it stops a diagram from
breaking but does nothing to prevent an LLM from picking an unreasonable
step in the first place (a script drawing a diagram spanning hundreds of
units, with `grid_step` left at the literal default of `1.0`, would still
hit the cap and fail for no good reason). `_nice_step` removes that failure
mode by construction: it picks a step proportional to the canvas size
(`span=8` → `1.0`, matching what both models already chose by hand for the
motivating scenario; `span=500` → `50.0`; `span=1000` → `100.0`), so the
common case — a script that cares about "on/off," not the exact spacing —
never has a reason to specify a bad value. `grid_step` and `tick_step` are
computed independently (not from a single shared value) per your call,
since nothing requires them to coincide, even though in practice they
usually will for the same canvas span.

Three validation checks remain, but two of them (non-positive step,
excessive density) are now backstops for an *explicit* override gone wrong
rather than the default path — real gaps a Fable review of this spec's
first draft found, verified by actually running the unvalidated version
through the sandbox:

- **Inverted bounds** (`x_range=(8, 0)`): without a check, this renders
  *silently* with wrong-looking-but-plausible output — the grow-only bounds
  expansion partially "rescues" it using whatever geometry exists, which is
  worse than an error because nothing indicates the request was malformed.
- **Non-positive explicit `grid_step`/`tick_step`**: both renderers already
  guard with `step if step > 0 else 1.0` at render time (`to_svg.py`'s
  `_append_grid`/`_append_axes`, `to_tikz.py`'s `_emit_grid`/`_emit_axes`),
  so an explicit `grid_step=0` doesn't crash — it silently renders as if
  `grid_step=1.0` had been requested instead. Catching this in `canvas()`
  turns silent surprise into an immediate, clear error. (The auto-computed
  default is always positive by construction, so this only fires on an
  explicit bad override.)
- **Pathologically small explicit `grid_step`/`tick_step`**: neither
  renderer caps grid/tick density — it's driven by a `while` loop with no
  line-count limit, and this happens at render time, well after `Builder`'s
  own `_op_cap` (which only bounds `_defs`/`_render`, not canvas rendering
  density). An explicit `canvas(x_range=(0, 8), grid=True,
  grid_step=0.001)` would render roughly 16,000 SVG line elements from a
  single call. `canvas()` rejects any request whose *effective* grid or
  tick lines would exceed `_MAX_GRID_LINES` (500) — generous enough that
  the auto-computed default (~10-20 lines total) never comes close to it;
  this check now only matters for a deliberately-small explicit override.

Calling `canvas()` a second time in the same script raises `ValueError`
immediately, naming the conflict, rather than silently overwriting (a
deliberate divergence from the DSL's own `CanvasOp`, which silently lets
the last call in the construction list win — chosen here because an LLM
script calling `canvas()` twice is more likely a mistake worth surfacing
than a deliberate reconfiguration).

There is no ordering constraint — `canvas()` may be called before or after
other construction/render calls in the script; like the DSL, only the
recorded values matter at `build()` time, not when the call happened.

One more existing-behavior interaction worth documenting rather than
"fixing" later: `render_util.py`'s `effective_canvas_bounds` (used by both
renderers) expands the bounds to include the origin whenever `axes=True` —
so `canvas(x_range=(2, 8), y_range=(2, 8), axes=True)` actually displays
from `(0, 0)`, not `(2, 2)`. This is existing, deliberate behavior (axes
need the origin in view to mean anything); the `canvas()` docstring and the
`instructions_python_full.py` bullet should mention it so a future reader
doesn't mistake it for a bug.

## Data flow

`Builder.__init__` (`geometry_diagrams/pydsl/builder.py`) gains a new field:

```python
self._canvas = None  # set at most once, by canvas(); type is ir.Canvas | None
```

`Builder.build()` changes from:

```python
def build(self) -> DiagramIR:
    return DiagramIR(define=list(self._defs), render=list(self._render), canvas=None)
```

to:

```python
def build(self) -> DiagramIR:
    return DiagramIR(define=list(self._defs), render=list(self._render), canvas=self._canvas)
```

A script that never calls `canvas()` still gets `canvas=None` — today's
auto-fit-bounds behavior is unchanged; this is purely additive.

`canvas` must be added to `geometry_diagrams/pydsl/__init__.py`'s import
line and `__all__` — learned directly from the labeling work: both
`stub.py`'s prompt-generation and `sandbox.py`'s tool-injection key off
`__all__`, and skipping this makes the function exist in `api.py` but be
uncallable from any real script.

`stub.py` needs no changes — `canvas` is a plain top-level function with a
docstring and type-hinted signature, exactly like every other function in
`api.py`; `generate_stub()`'s existing function-introspection loop picks it
up automatically. `_nice_step`/`_TARGET_LINES`/`_MAX_GRID_LINES` are
private (underscore-prefixed) and must NOT be added to `__all__` — only
`canvas` itself is part of the public surface. `api.py` already has
`import math` at the top (used by `circumcircle`'s radius computation), so
`_nice_step` needs no new import.

One new bullet in `instructions_python_full.py`'s Rules section, explicitly
steering models toward `canvas(x_range=..., y_range=..., grid=True)`
instead of hand-drawing a grid out of individual segments/lines — the exact
failure mode this plan was written to close.

## Testing

New file `tests/test_pydsl_canvas.py`, TDD, covering:

- `_nice_step` directly, as a unit: `_nice_step(8) == 1.0`,
  `_nice_step(500) == 50.0`, `_nice_step(1000) == 100.0`, plus a couple of
  boundary cases across the 1.5/3/7 residual thresholds (e.g. spans that
  land just below and just above each breakpoint) to pin the rounding
  behavior precisely rather than only spot-checking round numbers.
- `canvas(x_range=(0, 8), y_range=(0, 6), grid=True)` (no `grid_step`
  given) → `DiagramIR.canvas.grid_step == 1.0` (the auto-computed value for
  this span), `axes=False`, `tick_step == 1.0` (also auto-computed,
  independently), and the rest at `ir.Canvas`'s own defaults
  (`show_ticks=False`, `show_tick_labels=False`, `show_axis_labels=False`).
- `canvas(x_range=(0, 500), y_range=(0, 10), grid=True)` → `grid_step`
  auto-computes from the larger span (500), landing at `50.0` — confirms
  the "larger of x/y span drives the step" behavior, not just the
  single-span case above.
- Passing an explicit `grid_step`/`tick_step` overrides the auto-computed
  value — all other non-default fields (`axes`, `show_ticks`,
  `show_tick_labels`, `show_axis_labels`) also land correctly on the
  resulting `ir.Canvas`.
- Calling `canvas()` twice in the same builder context raises `ValueError`.
- `canvas(x_range=[0, 8], y_range=[0, 6])` (lists, not tuples) works
  identically to the tuple form.
- `x_range=(8, 0)` (inverted) and `x_range=(4, 4)` (degenerate/equal) both
  raise `ValueError` before any `Canvas` is constructed. Same for `y_range`.
- Explicit `grid_step=0`, `grid_step=-1`, `tick_step=0`, `tick_step=-1`
  each raise `ValueError` (the auto-computed default is never checked
  against this, since `_nice_step` cannot produce a non-positive value).
- An explicit `canvas(x_range=(0, 8), y_range=(0, 6), grid=True,
  grid_step=0.001)` raises `ValueError` naming the line-count limit, rather
  than succeeding and later rendering thousands of grid lines. Same for an
  explicit, pathologically small `tick_step` with `show_ticks=True`. A
  large span relying on the *auto-computed* default (e.g. `span=10000`)
  should NOT raise — confirming the backstop only fires on bad explicit
  input, never on the default path.
- A script with no `canvas()` call → `DiagramIR.canvas is None` (regression
  guard for today's auto-fit-bounds behavior); and separately, a script
  that does call `canvas()` never sets `clip` away from its `ir.Canvas`
  default of `True` (regression guard for the clip non-goal).
- A sandbox-path test (`geometry_diagrams.pydsl.sandbox.run_script`, not
  `new_builder_context()` directly) proving `canvas()` works through the
  real sandboxed execution path — matching the precedent set by the
  labeling plan's sandbox-path coverage requirement. Include a
  sandbox-path double-call case too (not just the direct-builder-context
  one above) — this is the case that actually pins down what error
  classification/retry message a model sees when it makes this mistake for
  real, which the direct-builder-context test can't observe.
- An SVG end-to-end test: build a diagram with `canvas(grid=True)` plus at
  least one drawn shape, compile it, render via `SVGRenderer`, and assert
  the output contains a `stroke="#ccc"` grid line — the concrete
  distinct-from-geometry styling this feature exists to provide, not just
  "some canvas-shaped output got produced."

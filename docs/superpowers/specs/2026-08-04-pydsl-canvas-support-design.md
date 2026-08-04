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
_MAX_GRID_LINES = 500  # total vertical + horizontal grid/tick lines a single canvas() may request


def canvas(
    x_range: "tuple[float, float] | list[float]",
    y_range: "tuple[float, float] | list[float]",
    grid: bool = False,
    grid_step: float = 1.0,
    axes: bool = False,
    tick_step: float = 1.0,
    show_ticks: bool = False,
    show_tick_labels: bool = False,
    show_axis_labels: bool = False,
) -> None:
    """Set canvas bounds and optional grid/axes styling for the diagram.
    Call at most once per script. Note: if axes=True, the displayed bounds
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
    if grid_step <= 0:
        raise ValueError(f"canvas(): grid_step must be > 0, got {grid_step!r}")
    if tick_step <= 0:
        raise ValueError(f"canvas(): tick_step must be > 0, got {tick_step!r}")
    if grid:
        n_grid_lines = (xmax - xmin) / grid_step + (ymax - ymin) / grid_step
        if n_grid_lines > _MAX_GRID_LINES:
            raise ValueError(
                f"canvas(): grid_step={grid_step!r} over this range would draw "
                f"~{int(n_grid_lines)} grid lines (limit {_MAX_GRID_LINES}) — use a larger grid_step"
            )
    if show_ticks or show_tick_labels:
        n_tick_lines = (xmax - xmin) / tick_step + (ymax - ymin) / tick_step
        if n_tick_lines > _MAX_GRID_LINES:
            raise ValueError(
                f"canvas(): tick_step={tick_step!r} over this range would draw "
                f"~{int(n_tick_lines)} ticks (limit {_MAX_GRID_LINES}) — use a larger tick_step"
            )
    builder._canvas = CanvasDef(
        xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax,
        grid=grid, grid_step=grid_step,
        axes=axes, tick_step=tick_step,
        show_ticks=show_ticks, show_tick_labels=show_tick_labels,
        show_axis_labels=show_axis_labels,
    )
```

Every field name and default is a direct 1:1 mirror of `ir.Canvas` (skipping
only `clip`/`kind`, per Non-goals). `x_range`/`y_range` have no defaults —
bounds must be explicit; both tuples and lists work (LLM scripts write both
interchangeably, and nothing here relies on tuple-specific behavior — the
function only unpacks and indexes).

Four validation checks exist because a Fable review of this spec's first
draft found each is a real gap, not a hypothetical one — verified by
actually running the unvalidated version through the sandbox:

- **Inverted bounds** (`x_range=(8, 0)`): without a check, this renders
  *silently* with wrong-looking-but-plausible output — the grow-only bounds
  expansion partially "rescues" it using whatever geometry exists, which is
  worse than an error because nothing indicates the request was malformed.
- **Non-positive `grid_step`/`tick_step`**: both renderers already guard
  with `step if step > 0 else 1.0` at render time (`to_svg.py`'s
  `_append_grid`/`_append_axes`, `to_tikz.py`'s `_emit_grid`/`_emit_axes`),
  so `grid_step=0` doesn't crash — it silently renders as if `grid_step=1.0`
  had been requested. Catching this in `canvas()` turns silent surprise
  into an immediate, clear error.
- **Pathologically small `grid_step`/`tick_step`**: neither renderer caps
  grid/tick density — it's driven by a `while` loop with no line-count
  limit, and this happens at render time, well after `Builder`'s own
  `_op_cap` (which only bounds `_defs`/`_render`, not canvas rendering
  density). `canvas(x_range=(0, 8), grid=True, grid_step=0.001)` would
  render roughly 16,000 SVG line elements from a single call. `canvas()`
  rejects any request whose grid or tick lines would exceed
  `_MAX_GRID_LINES` (500 — generous for any real diagram; a typical grid
  request in this plan's motivating cases is well under 20 lines).

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
up automatically.

One new bullet in `instructions_python_full.py`'s Rules section, explicitly
steering models toward `canvas(x_range=..., y_range=..., grid=True)`
instead of hand-drawing a grid out of individual segments/lines — the exact
failure mode this plan was written to close.

## Testing

New file `tests/test_pydsl_canvas.py`, TDD, covering:

- `canvas(x_range=(0, 8), y_range=(0, 6), grid=True)` → `DiagramIR.canvas`
  is an `ir.Canvas` with `xmin=0, xmax=8, ymin=0, ymax=6, grid=True`, and
  every other field at its stated default (`grid_step=1.0`, `axes=False`,
  `tick_step=1.0`, `show_ticks=False`, `show_tick_labels=False`,
  `show_axis_labels=False`).
- Passing every non-default field (all of `grid_step`, `axes`, `tick_step`,
  `show_ticks`, `show_tick_labels`, `show_axis_labels`) → all land correctly
  on the resulting `ir.Canvas`.
- Calling `canvas()` twice in the same builder context raises `ValueError`.
- `canvas(x_range=[0, 8], y_range=[0, 6])` (lists, not tuples) works
  identically to the tuple form.
- `x_range=(8, 0)` (inverted) and `x_range=(4, 4)` (degenerate/equal) both
  raise `ValueError` before any `Canvas` is constructed. Same for `y_range`.
- `grid_step=0`, `grid_step=-1`, `tick_step=0`, `tick_step=-1` each raise
  `ValueError`.
- `canvas(x_range=(0, 8), y_range=(0, 6), grid=True, grid_step=0.001)`
  raises `ValueError` naming the line-count limit, rather than succeeding
  and later rendering thousands of grid lines. Same for a pathologically
  small `tick_step` with `show_ticks=True`.
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

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
  canvas bounds` comment). There is no existing mechanism for "auto-fit
  bounds to geometry AND show a grid" — the recipe DSL's own `CanvasOp`
  requires explicit `x_range`/`y_range` for the same reason. This plan
  mirrors that: `canvas()`'s bounds are required, not optional.
- No `clip` exposure. `ir.Canvas.clip` defaults to `True`, which is the
  sensible behavior; nothing in this plan's motivating cases needs it
  overridden.

## API surface

One new top-level function in `api.py`, following the same pattern as
`draw()`/`mark_angle()` — it records configuration rather than returning a
handle:

```python
def canvas(
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    grid: bool = False,
    grid_step: float = 1.0,
    axes: bool = False,
    tick_step: float = 1.0,
    show_ticks: bool = False,
    show_tick_labels: bool = False,
    show_axis_labels: bool = False,
) -> None:
    """Set canvas bounds and optional grid/axes styling for the diagram.
    Call at most once per script."""
    from geometry_diagrams.ir.ir import Canvas as CanvasDef

    builder = get_builder()
    if builder._canvas is not None:
        raise ValueError(
            "canvas() was already called once in this script — only one call is allowed"
        )
    builder._canvas = CanvasDef(
        xmin=x_range[0], xmax=x_range[1],
        ymin=y_range[0], ymax=y_range[1],
        grid=grid, grid_step=grid_step,
        axes=axes, tick_step=tick_step,
        show_ticks=show_ticks, show_tick_labels=show_tick_labels,
        show_axis_labels=show_axis_labels,
    )
```

Every field name and default is a direct 1:1 mirror of `ir.Canvas` (skipping
only `clip`, per Non-goals). `x_range`/`y_range` have no defaults — bounds
must be explicit. Calling `canvas()` a second time in the same script raises
`ValueError` immediately, naming the conflict, rather than silently
overwriting (a deliberate divergence from the DSL's own `CanvasOp`, which
silently lets the last call in the construction list win — chosen here
because an LLM script calling `canvas()` twice is more likely a mistake
worth surfacing than a deliberate reconfiguration).

There is no ordering constraint — `canvas()` may be called before or after
other construction/render calls in the script; like the DSL, only the
recorded values matter at `build()` time, not when the call happened.

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
- A script with no `canvas()` call → `DiagramIR.canvas is None` (regression
  guard for today's auto-fit-bounds behavior).
- A sandbox-path test (`geometry_diagrams.pydsl.sandbox.run_script`, not
  `new_builder_context()` directly) proving `canvas()` works through the
  real sandboxed execution path — matching the precedent set by the
  labeling plan's sandbox-path coverage requirement.
- An SVG end-to-end test: build a diagram with `canvas(grid=True)` plus at
  least one drawn shape, compile it, render via `SVGRenderer`, and assert
  the output contains a `stroke="#ccc"` grid line — the concrete
  distinct-from-geometry styling this feature exists to provide, not just
  "some canvas-shaped output got produced."

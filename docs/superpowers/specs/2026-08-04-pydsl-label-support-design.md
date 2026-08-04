# pydsl Label Support — Design

## Problem

pydsl scripts have no way to put text on a diagram — no naming a point `A`,
no labeling a length `r`, no labeling an angle. The stacking-pyramids
curriculum scenario (`geo-m4-t2-l3-gs-stacking-pyramids-1`) explicitly asks
for "label the bottom circle's radius r and the total height h", and no
model attempt has ever been able to satisfy that half of the prompt, because
the capability doesn't exist in the API surface at all.

The underlying IR is not the gap. `geometry_diagrams/ir/ir.py` already
defines four label `RenderOp` kinds — `LabelPoint`, `LabelSegment`,
`LabelAngle`, `LabelFreeText` — and both `to_tikz.py` and `to_svg.py` already
render all four. The `recipe`/DSL system already uses them. This is purely a
pydsl-exposure gap.

A second, closely related gap: `LabelSegment` needs a `Segment` id, and
pydsl currently only produces `Segment` handles via `Triangle.side()` /
`Polygon.side()` — there's no way to get a segment between two arbitrary
points (e.g. a circle's radius, center-to-edge). This was flagged as a known
open gap in the `python_full` model-comparison artifact from the stacking-
pyramids rerun. Closing it is small and directly enables the radius/height
labeling case, so it's in scope here.

## Non-goals

- No IR or renderer changes — everything needed already exists and is
  exercised by `recipe`/`structured`.
- No changes to `Circle`, `Triangle`, `Polygon`, or `Line` beyond what's
  needed to label points/segments/angles derived from them.
- No support for labeling at an unresolved (non-literal) point's location —
  `label_text(at=...)` takes raw floats, not a `Point` handle, to sidestep
  points whose coordinates aren't known until SymPy resolves them later
  (`point_on`, `rotate_point`, etc. — see `Point._known()` in `handles.py`).

## API surface

All four additions follow the existing lazy-import pattern in
`handles.py` (see `Point.__add__` / `_record_literal_point`), which avoids a
handles↔api circular import: label-recording code lives in the method body
via a local `from geometry_diagrams.ir.ir import ...` / `from
geometry_diagrams.pydsl.builder import get_builder` import, not a module-level
one.

### `Point.label(text, pos="auto", show_coords=False) -> None`

Records `LabelPoint(p=self.id, text=text, pos=pos, show_coords=show_coords)`.

`text` is a **required** positional argument — no default. `LabelPoint.text`
is `Optional[str]` at the IR level and falls back to the object's own id when
`None` (see `to_svg.py`'s `label = text if text is not None else p`), but a
pydsl point's id is an internal hidden name like `__pydsl_pt_5`. That must
never be the thing that ends up on a rendered diagram, so pydsl's wrapper
does not expose the `None` fallback at all.

`pos` accepts the same literal set the IR does: `"auto"`, `"above"`,
`"below"`, `"left"`, `"right"`, `"above left"`, `"above right"`,
`"below left"`, `"below right"`.

### `segment(p: Point, q: Point) -> Segment` (new, `api.py`)

```python
def segment(p: Point, q: Point) -> Segment:
    """A segment between any two points (deduplicated with segments already
    obtained via Triangle.side()/Polygon.side() for the same pair)."""
    builder = get_builder()
    return builder._get_or_create_segment(p.id, q.id)
```

Thin wrapper over `Builder._get_or_create_segment`, the same dedup'd path
`Triangle.side()` and `Polygon.side()` already call. No new IR — `Segment`
is an existing `DefStmt`.

### `Segment.label(text: str, pos: float | None = None) -> None`

Records `LabelSegment(seg=self.id, text=text, pos=pos)`. Works identically
whether the `Segment` handle came from `segment(p, q)` or a `.side()` call —
both produce the same handle type.

`text` is required (matches `LabelSegment.text: str` at the IR level — no
`None` fallback exists to worry about here).

### `AngleRef.label(text: str, pos: float | None = None) -> None`

Records `LabelAngle(angle=AnglePoints(a=self.a.id, o=self.o.id,
b=self.b.id), text=text, pos=pos)`.

Independent of `mark_angle()` (which draws the arc) — a script that wants
both the arc and a label calls both, matching how drawing and labeling are
separate everywhere else in the API (`draw()` vs. the new `.label()` calls).

`text` is required (matches `LabelAngle.text: str`).

### `label_text(text: str, at: tuple[float, float] | None = None, centroid_of: Triangle | Polygon | None = None) -> None` (new, `api.py`)

Records `LabelFreeText(text=text, at=list(at) if at is not None else None,
centroid_of=centroid_of.id if centroid_of is not None else None)`.

Exactly one of `at` / `centroid_of` must be given. The IR's own
`@model_validator` already enforces this, but that would only surface as a
`pydantic.ValidationError` at `builder.build()` time — far from the call
site and confusing for an LLM script-writer to debug. `label_text()`
validates this itself and raises a `ValueError` naming the problem
immediately, the same way `Point._known()` and `Triangle.side()` raise
immediately rather than deferring to a downstream compile error.

`centroid_of` accepts `Triangle` or `Polygon` only (the two handle types with
a `.vertices` field — the only ones `to_svg.py`/`to_tikz.py`'s `centroid_of`
handling actually computes a centroid from).

## Data flow

No new plumbing. `Builder._add_render()` already exists and is exactly what
`draw()`/`draw_points()`/`mark_angle()` call; the new methods/functions call
it the same way, with the four label `RenderOp` types instead of `Draw` /
`DrawPoints` / `MarkAngles`.

`stub.py`'s existing method-introspection loop
(`inspect.getmembers(obj, predicate=inspect.isfunction)` over each handle
class, skipping underscore-prefixed names) already surfaces `.label()`
automatically in the generated stub — unlike the `.x`/`.y` arithmetic
operators (dunders, filtered out, and manually documented in
`instructions_python_full.py`), `.label()` is a plain method and needs no
special-casing there.

One addition to `instructions_python_full.py`'s Rules section: a short
worked example showing `segment()` + `.label()` together for the
radius/height-labeling case, since that's the exact shape of prompt this
closes a gap for and is worth modeling once explicitly rather than trusting
the auto-generated stub signature alone to convey the pattern.

## Testing

New file `tests/test_pydsl_labels.py`, TDD, covering:

- `Point.label("A")` → `DiagramIR.render` contains a matching `LabelPoint`
  with the right `p`/`text`/`pos`/`show_coords`.
- `segment(p, q)` returns a `Segment` handle; calling it twice for the same
  pair (in either order) returns the same segment id (dedup, matching
  `Triangle.side()`'s existing dedup behavior).
- `Segment.label("r")` on a `segment()`-obtained handle → matching
  `LabelSegment`.
- `Segment.label("r")` on a `.side()`-obtained handle → matching
  `LabelSegment` (same code path, both handle sources).
- `AngleRef.label("θ")` → matching `LabelAngle` with the right `a`/`o`/`b`
  ids.
- `label_text("h", at=(1.0, 2.0))` → matching `LabelFreeText` with `at` set,
  `centroid_of` unset.
- `label_text("h", centroid_of=some_triangle)` → matching `LabelFreeText`
  with `centroid_of` set, `at` unset.
- `label_text("h")` (neither) and `label_text("h", at=(0, 0),
  centroid_of=t)` (both) each raise `ValueError` immediately, before
  `builder.build()` is ever called.

Then one small end-to-end test: build a diagram using at least one of each
new call, run it through `SVGRenderer`, and confirm the label text appears
in the rendered SVG output (`<text>` elements) — closing the loop from
pydsl call to actual pixels, not just IR shape.

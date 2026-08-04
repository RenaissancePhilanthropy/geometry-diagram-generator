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
`Polygon.side()` (also `Median.segment`/`Altitude.segment`, but never a
bare pair of points) — there's no way to get a segment between two arbitrary
points (e.g. a circle's radius, center-to-edge). This was flagged as a known
open gap in the `python_full` model-comparison artifact from the stacking-
pyramids rerun. Closing it is small and directly enables the radius/height
labeling case, so it's in scope here.

## Pre-existing bug this design depends on fixing

A Fable review of this spec's first draft found, and a direct repro against
`sandbox.run_script()` confirmed, that **`Point.__add__`/`__sub__`/`__mul__`
— already shipped and committed earlier this session — are silently broken
in the actual sandboxed execution path**, despite passing every existing
test. This matters here because the originally-drafted `.label()` methods
would have shipped with the identical bug.

Root cause: `sandbox.py`'s `_run_in_subprocess` wraps only the top-level
callables in `pydsl.__all__` with `_bind_to_builder`, which sets the
`_current_builder` contextvar for the duration of that one call and resets
it on return (see the module docstring's explanation of why — the whole
script runs in a `LocalPythonExecutor` worker thread that doesn't inherit
the calling thread's contextvar state). Any code that calls `get_builder()`
from *outside* one of those wrapped calls — e.g. a script's own `a + b`
statement — finds no active builder and raises. `Triangle.side()` and
`Polygon.side()` don't hit this because `Triangle`/`Polygon` already carry
their own `_builder` reference (a private field set at construction time),
bypassing the contextvar for all their later method calls. `Point`,
`Segment`, and `AngleRef` carry no such reference, so `Point.__add__`
(shipped) and the newly-proposed `Point.label()`/`Segment.label()`/
`AngleRef.label()` all hit the same wall.

Confirmed live:
```python
# Through new_builder_context() directly: passes (existing tests use this)
# Through sandbox.run_script(): fails
script = "a = point(0, 0)\nb = point(4, 0)\nc = a + b\n"
run_script(script)
# -> RuntimeError: no active Builder — call inside new_builder_context()
```

**Fix, in scope for this plan:** give `Point`, `Segment`, and `AngleRef` a
`_builder` field, mirroring the existing `Triangle`/`Polygon` pattern
exactly (`field(repr=False, compare=False)`, excluded from equality/hash so
two otherwise-identical handles from different scripts still compare equal).
This is mechanical but touches every site that constructs one of these three
handles — enumerated here so the implementation plan can assign them
precisely:

- **Point**: `handles.py::_record_literal_point`; `api.py::point()`,
  `circumcircle()`, `incircle()` (via `Circle.center`), `median()` (via
  `Median.midpoint`), `altitude()` (via `Altitude.foot`), `point_on()`,
  `rotate_point()`, `reflect_point()`, `dilate_point()`;
  `handles.py::Triangle.angle_at()` and `Polygon.angle_at()` (the two
  synthesized `Point(id=...)` wrappers for the non-vertex angle-ref points).
- **Segment**: `builder.py::Builder._get_or_create_segment` (both return
  paths — cache hit and cache miss); `api.py::median()` and `altitude()`
  (their own `Segment(id=seg_id)` construction, separate from the one
  `_get_or_create_segment` returns).
- **AngleRef**: `handles.py::Triangle.angle_at()` and `Polygon.angle_at()`.

Each site already has a `Builder` instance in scope (either the local
`builder = get_builder()` result, or `self._builder` inside a
`Triangle`/`Polygon` method) — this is purely a matter of passing it
through, not obtaining it from anywhere new. No call site needs a default
value for the field; every constructor call is being touched anyway; a
missing `_builder` should never be silently tolerated by giving the field a
`None` default, since that would just reintroduce this exact bug under a
different name the next time someone adds a Point-returning function and
forgets the parameter.

This fix also retroactively repairs the pre-existing `Point.__add__`/
`__sub__`/`__mul__` sandbox bug, since it goes through the same field.

**Follow-up, explicitly not in scope here:** this is a mechanical fix, not
a structural one. It repairs every currently-known instance of "a handle
method calls `get_builder()` without a captured builder reference," but the
trap itself — that pattern being available at all — still exists for any
future handle. Closing it for good would mean making the sandbox's
`_current_builder` contextvar work for the entire script execution inside
its `LocalPythonExecutor` worker thread, so `get_builder()` just succeeds
everywhere, with no per-handle bookkeeping required. That's a change to the
sandbox's actual thread/isolation model (see `sandbox.py`'s docstring on why
per-call wrap-and-reset was chosen in the first place — contextvars don't
propagate across the thread boundary `LocalPythonExecutor` introduces), so
it deserves its own design pass rather than riding along with a labeling
feature. Tracked as future work, not part of this plan.

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
    if p.id == q.id:
        raise ValueError(f"segment() needs two distinct points, got {p.id!r} twice")
    builder = get_builder()
    return builder._get_or_create_segment(p.id, q.id)
```

Thin wrapper over `Builder._get_or_create_segment`, the same dedup'd path
`Triangle.side()` and `Polygon.side()` already call. No new IR — `Segment`
is an existing `DefStmt`. The identity check mirrors `Triangle.side()`'s own
input validation (raise immediately, don't let a degenerate zero-length
segment surface as a confusing downstream compile error).

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

Exactly one of `at` / `centroid_of` must be given, and that check runs
**before** `get_builder()` is called — `label_text("h")` (neither) must
raise a `ValueError` even with no active builder context, not a confusing
`RuntimeError` about a missing builder. The IR's own `@model_validator`
already enforces the same one-of rule, but that only surfaces as a
`pydantic.ValidationError` at `builder.build()` time — far from the call
site and confusing for an LLM script-writer to debug. `label_text()`
validates this itself and raises a `ValueError` naming the problem
immediately, the same way `Point._known()` and `Triangle.side()` raise
immediately rather than deferring to a downstream compile error.

`centroid_of` accepts `Triangle` or `Polygon` only — the two handle types
whose *compiled SymPy object* exposes a `.vertices` sequence, which is what
`to_svg.py`/`to_tikz.py`'s `centroid_of` handling actually averages over
(not the pydsl handle's own `.vertices` field, though for these two types
the vertex sets are the same points either way).

## Data flow

`Builder._add_render()` already exists and is exactly what
`draw()`/`draw_points()`/`mark_angle()` call; the new methods/functions call
it the same way, with the four label `RenderOp` types instead of `Draw` /
`DrawPoints` / `MarkAngles` — that part needs no new plumbing.

What **does** need new plumbing, beyond what the first draft of this spec
assumed: the `_builder`-threading fix above (its own section), and two
`pydsl/__init__.py` additions — `segment` and `label_text` must be added to
that module's imports and `__all__`. This isn't cosmetic: `stub.py` iterates
`pydsl_module.__all__` to build the prompt text, and
`sandbox.py::_run_in_subprocess` iterates the same `__all__` to build the
dict of callables actually injected into the sandboxed script's namespace.
Skip this and the new functions exist in `api.py` but are uncallable from
any real script.

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
  `builder.build()` is ever called — and, per the ordering requirement
  above, even with **no** active builder context (call it outside
  `new_builder_context()` entirely and assert `ValueError`, not
  `RuntimeError`).

**Sandbox-path coverage (the gap that let the `Point.__add__` bug ship
unnoticed):** none of the tests above go through `sandbox.run_script()` —
they all call the API functions directly inside `new_builder_context()`.
That is exactly the blind spot that let `Point.__add__` pass every existing
test while being broken in production. At least one test in this file must
build a script as a string and run it through `run_script()`, using
`.label()` and `segment()` together (e.g. a point, a second point, a
`segment()` between them, and `.label()` on the result), and assert
`result.error is None` and the resulting `diagram_ir` contains the expected
label op. This is the test that would have caught the pre-existing bug, and
it's the test that proves the `_builder`-threading fix actually works end
to end rather than just in the direct-builder-context unit tests.

Then one small non-sandbox end-to-end test: build a diagram using at least
one of each new call via `new_builder_context()`, compile it (`compile_defs`
— see existing tests for the pattern), run it through `SVGRenderer`, and
confirm the label text appears in the rendered SVG output (`<text>`
elements). Keep test labels to plain strings (`"A"`, `"r"`, `"h"`) rather
than LaTeX-command text (e.g. `"\theta"`) — the renderer classifies
LaTeX-command labels as mathtext and emits `<path>` glyphs instead of
`<text>`, which would make this assertion fragile for reasons unrelated to
what this test is actually checking.

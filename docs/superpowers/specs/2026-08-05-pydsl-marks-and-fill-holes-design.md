# pydsl Congruence/Right-Angle Marks and Fill Holes — Design

## Problem

A four-agent parallel audit of gaps between pydsl and (a) the recipe DSL,
(b) the underlying IR's renderer-supported-but-unexposed capabilities, and
(c) broader math-diagram needs, converged on three concrete, cheap gaps —
all fully implemented in both `to_tikz.py` and `to_svg.py`, with zero pydsl
exposure today:

- **`MarkSegments`** — tick marks (`|`, `||`, `|||`, ...) or chevrons
  (`>`, `>>`, `>>>`) on a group of segments, used for "these sides are
  equal," "these lines are parallel," or "these sides are proportional."
  Extremely common in textbook-style proof diagrams; there is currently no
  way to express this from pydsl at all.
- **`MarkRightAngles`** — the small square symbol at a right angle,
  distinct from `mark_angle()`'s existing arc-based `MarkAngles`. Also
  common (right triangles, perpendicular constructions) and also entirely
  unexposed.
- **`Fill.holes`** — an even-odd cutout: fill one shape's interior except
  for the regions covered by one or more other shapes (rings, annuli,
  "shade between the circle and the square"). This is a rendering-time
  boolean operation, not a geometric construction, so a pydsl script has
  no way to compose it from existing primitives — it genuinely needs new
  API surface, unlike most of Clusters A–D's gaps.

## A real wrinkle found during investigation: `mark_proportional()` is visually identical to `mark_equal()`

Confirmed directly in both renderers' `MarkSegments`-grouping logic
(`to_tikz.py` lines ~121-139, `to_svg.py` lines ~280-299): the routing rule
is exactly `if group.startswith("parallel"): use chevron cycle; else: use
tick-mark cycle`. There is no third symbol set for "proportional" — the
recipe DSL's `MarkProportional` op lowers to the exact same `_MARK_SYMBOLS`
tick cycle as `MarkEqualLengths`, distinguished only by an internal
group-string prefix that exists to avoid counter collisions between the
two concepts, not to produce a different visual mark. So `mark_equal(a,
b)` and `mark_proportional(a, b)` render byte-for-byte identically.

This was raised explicitly with the user, who chose to expose
`mark_proportional()` anyway despite the visual identity — the reasoning
being that the semantic intent ("equal" vs. "proportional") can matter for
a script's own readability and future maintainability even when the
rendered diagram looks the same. This is a deliberate, informed choice,
not an oversight — noted here so a future reader doesn't "fix" it by
merging the two functions.

## API surface

### Builder plumbing (prerequisite for `mark_equal`/`mark_parallel`/`mark_proportional`)

`Builder` gains one new method:

```python
def _fresh_mark_group(self, kind: str) -> str:
    """Return a fresh, globally-unique group string prefixed by kind
    (e.g. "parallel_3", "equal_1"). Uniqueness matters (so unrelated
    mark_equal()/mark_parallel() calls never collide into the same
    visual symbol); the "parallel" prefix specifically matters because
    both renderers route purely on `group.startswith("parallel")` to
    pick the chevron cycle instead of the tick-mark cycle — kind must be
    passed as literally "parallel" for mark_parallel() to render
    correctly."""
    self._mark_group_counter += 1
    return f"{kind}_{self._mark_group_counter}"
```

`self._mark_group_counter = 0` added to `Builder.__init__`, alongside the
existing `self._hidden_id_counter`.

### `mark_equal()`, `mark_parallel()`, `mark_proportional()`

```python
def mark_equal(*segments: Segment) -> None:
    """Mark segments as equal in length with matching tick marks. Each
    call gets a fresh tick symbol automatically — pass all mutually-equal
    segments in ONE call (e.g. mark_equal(ab, cd, ef)) rather than
    multiple calls, since separate calls always get visually distinct
    symbols, never the same one. Requires at least 2 segments. Note: only
    6 distinct tick symbols exist (shared with mark_proportional()'s
    calls too) and marks draw at each segment's midpoint — more than 6
    mark_equal()/mark_proportional() calls in one diagram silently reuse
    a symbol, and a segment passed to two different mark_*() calls gets
    overlapping marks at the same midpoint."""


def mark_parallel(*segments: Segment) -> None:
    """Mark segments as parallel with matching chevron marks (>, >>, >>>,
    ...). Same one-call-per-group contract as mark_equal(). Requires at
    least 2 segments. Note: only 3 distinct chevron counts exist — a 4th
    mark_parallel() call in one diagram silently reuses one."""


def mark_proportional(*segments: Segment) -> None:
    """Mark segments as proportional (not necessarily equal) — NOTE:
    renders with the same tick-mark symbols as mark_equal(), since the
    underlying renderer has no separate visual convention for
    "proportional." Use this over mark_equal() only for the script's own
    semantic clarity; the diagram itself won't look different. Requires
    at least 2 segments. Shares mark_equal()'s 6-symbol limit (see its
    docstring) — the two functions draw from the same symbol cycle."""
```

All three share one implementation shape. `MarkSegments` needs a new
import in `api.py`'s existing `from geometry_diagrams.ir.ir import ...`
line (it isn't there today):

```python
def _mark_segments(kind: str, segments: tuple[Segment, ...]) -> None:
    if len(segments) < 2:
        raise ValueError(f"mark_{kind}() requires at least 2 segments, got {len(segments)}")
    builder = get_builder()
    group = builder._fresh_mark_group(kind)
    builder._add_render(MarkSegments(segs=[s.id for s in segments], group=group))


def mark_equal(*segments: Segment) -> None:
    """..."""
    _mark_segments("equal", segments)


def mark_parallel(*segments: Segment) -> None:
    """..."""
    _mark_segments("parallel", segments)


def mark_proportional(*segments: Segment) -> None:
    """..."""
    _mark_segments("proportional", segments)
```

(`_mark_segments` is a private module-level helper in `api.py`, not part
of the public surface — mirrors the existing `_validate_on_circle`
private-helper pattern from Cluster C.)

### `mark_right_angle()`

```python
def mark_right_angle(ref: AngleRef) -> None:
    """Mark an angle with the right-angle square symbol, e.g.
    mark_right_angle(t.angle_at(b)) — distinct from mark_angle()'s arc.
    Takes exactly one angle per call (no group parameter, unlike
    mark_angle()'s optional equal-angle group) — a right angle is
    unambiguously 90°, so there's no equivalence class to group."""
    from geometry_diagrams.ir.ir import MarkRightAngles

    builder = get_builder()
    builder._add_render(
        MarkRightAngles(angles=[AnglePoints(a=ref.a.id, o=ref.o.id, b=ref.b.id)])
    )
```

Mirrors `mark_angle()`'s exact structure (same `AnglePoints` construction
from `ref.a`/`ref.o`/`ref.b`), minus the `group` parameter.

### `fill()` gains `holes`

```python
def fill(
    obj,
    color: "str | None" = None,
    opacity: float = 1.0,
    holes: "Iterable | tuple" = (),
) -> None:
    """... (existing docstring, plus:) holes: shapes whose interiors are
    punched out as transparent cutouts (rings, annuli, "the region
    between the circle and the square") — each must be a previously
    constructed shape with an interior (triangle, polygon, circle,
    ellipse, sector), not a Point or AngleRef. No containment check is
    performed — same permissiveness as the underlying renderer, which
    silently applies the even-odd rule regardless of whether a hole is
    fully inside obj, partially overlapping, or outside it entirely."""
    if isinstance(obj, Point):
        raise ValueError("fill() doesn't take a Point — use draw_points(...) instead")
    if isinstance(obj, AngleRef):
        raise ValueError("fill() doesn't take an AngleRef — use mark_angle(...) instead")
    if not 0 <= opacity <= 1:
        raise ValueError(f"fill(): opacity must be between 0 and 1, got {opacity!r}")
    holes = tuple(holes)  # materialize once: the loop below and the [h.id for h in
                           # holes] construction later must see the same items, which
                           # silently breaks for a one-shot generator argument
    for hole in holes:
        if isinstance(hole, Point):
            raise ValueError("fill(): a hole can't be a Point — use draw_points(...) instead")
        if isinstance(hole, AngleRef):
            raise ValueError("fill(): a hole can't be an AngleRef — use mark_angle(...) instead")

    from geometry_diagrams.ir.ir import Fill

    style: dict = {}
    if color is not None:
        style["color"] = color
    if opacity != 1.0:
        style["opacity"] = opacity

    builder = get_builder()
    style_key = builder._register_style(style) if style else None
    builder._add_render(Fill(
        obj=obj.id, holes=[h.id for h in holes], opacity=opacity, style=style_key,
    ))
```

Everything above `holes` is the existing `fill()` body from Cluster D,
unchanged — this is additive. No self-hole guard (`holes` containing
`obj` itself) — considered and explicitly dropped as not worth guarding:
it's a niche mistake, not a common one, and the renderer's own even-odd
math handles it without crashing (it just inverts/cancels the overlapping
region, a real but rare-enough outcome not worth new validation for).

### Correction: no renderer fix needed — `Sector` support already exists

An earlier draft of this spec (based on a Fable review finding) claimed
`to_svg.py`'s `_obj_to_svg_subpath` — the helper `fill()`'s `holes`
compound-fill path uses to build both the outer shape's path and each
hole's path — lacked a `Sector` case, and planned to add one. **This was
wrong.** Reading the complete function (not a truncated excerpt) shows a
working `if isinstance(sym_obj, Sector): ...` branch already present,
immediately after the `Ellipse` case. Verified empirically too: compiling
a hand-built `DiagramIR` with `Fill(obj="poly", holes=["sec"], ...)` where
`sec` is a `SectorCenterStartEnd`, through `ir_to_svg`, produces
`fill-rule="evenodd"` in the output with zero warnings — `fill(shape,
holes=[sector])` and `fill(sector, holes=[...])` both already work
correctly under SVG today. (`_obj_to_svg_subpath`'s docstring — "Supports
Polygon/Triangle, Circle, and Ellipse" — is itself stale, predating the
`Sector` branch; not touched by this plan since fixing a comment isn't
this cluster's job, but noted here so nobody re-derives the same false
gap from it later.)

No `to_svg.py` or `to_tikz.py` change is needed anywhere in this cluster.
This plan adds a regression test locking in the already-correct behavior
(see Testing) instead of a code fix.

## Non-goals

- No dedicated `ring()`/`annulus()` convenience function — `fill(outer,
  holes=[inner])` is the general primitive; a dedicated wrapper would be
  redundant sugar over it, the same reasoning that dropped
  `circle_through_3()` in Cluster B.
- No `group=` parameter exposed on `mark_equal()`/`mark_parallel()`/
  `mark_proportional()` (unlike the DSL's manual `group` field, and unlike
  `mark_angle()`'s own optional `group`) — every call gets a fresh,
  automatically-distinct symbol; a script wanting several segments in one
  equivalence class passes them all to one call. This removes a whole
  class of bookkeeping the DSL required (manually choosing non-colliding
  group numbers) without losing any real expressiveness — a script can
  always merge into one call.
- No containment validation on `fill()`'s `holes` — matches the
  renderer's own lack of validation; see the `fill()` docstring above.

## Testing

New file `tests/test_pydsl_marks_and_holes.py`, TDD, covering:

- `Builder._fresh_mark_group()`: returns strings prefixed correctly
  (`"parallel_1"`, `"equal_1"`, etc.); two calls with the same `kind`
  return distinct strings.
- `mark_equal()`/`mark_parallel()`/`mark_proportional()`: each records a
  `MarkSegments` with the correct `segs` ids and a group string with the
  correct prefix; each rejects fewer than 2 segments with a `ValueError`
  mentioning "at least 2"; two separate `mark_equal()` calls produce two
  `MarkSegments` records with two DIFFERENT group strings (proving the
  auto-fresh-group behavior, not an accidental shared/hardcoded key).
- A render-level test (constructing a real `DiagramIR` with two
  `mark_equal()` groups and one `mark_parallel()` group, compiling via
  `ir_to_svg`/`ir_to_tikz`) confirming the first equal-group gets `"|"`,
  the second gets `"||"`, and the parallel group gets a `">"`-based
  chevron — proving the whole pipeline (not just the recorded IR) behaves
  as documented.
- `mark_right_angle()`: records a `MarkRightAngles` with a single-element
  `angles` list containing the correct `AnglePoints` mapping.
- `fill()`'s `holes`: records the correct `holes` id list; a hole that's a
  `Point` or `AngleRef` raises the same way the primary `obj` check does;
  `fill()` with no `holes` argument still records `holes=[]` (the IR
  field's own default) and behaves exactly as before this cluster (a
  non-regression check against Cluster D's existing fill() tests); a
  render-level test with one shape and one hole shape, compiled via
  `ir_to_svg`/`ir_to_tikz`, confirming the output actually contains an
  even-odd/cutout construct (e.g. for SVG, a `fill-rule="evenodd"` path
  with a concatenated sub-path for the hole; for TikZ, `even odd rule` in
  the emitted `\fill` command).
- **`holes` accepts a one-shot generator, not just a list/tuple** —
  regression test for the double-iteration bug found in review: call
  `fill(shape, holes=(h for h in [hole_shape]))` (a genuine generator
  expression, not a list) and confirm the resulting `Fill.holes` is
  non-empty — this would silently record `holes=[]` if `holes = tuple(holes)`
  were ever removed from the implementation, since the validation loop
  would exhaust the generator before the `[h.id for h in holes]` line ran.
- **Sector as a hole and as the outer shape, under SVG** — a coverage
  test (not a regression test for a fix, since no fix is needed — see the
  "Correction" section above): call pydsl's `fill(polygon_obj,
  holes=[sector_obj])` and `fill(sector_obj, holes=[circle_obj])`, build
  the resulting `DiagramIR`, and compile it through `ir_to_svg`, asserting
  the output contains a `fill-rule="evenodd"` path and no "unsupported
  shape type" warning. This locks in already-correct behavior so nobody
  accidentally regresses it while touching `_obj_to_svg_subpath` for
  something else later.
- A sandbox-path test (`run_script`) exercising `mark_equal()`,
  `mark_right_angle()`, and `fill(..., holes=[...])` through the real
  sandbox, confirming all three names resolve and the resulting
  `DiagramIR` contains the expected render ops.

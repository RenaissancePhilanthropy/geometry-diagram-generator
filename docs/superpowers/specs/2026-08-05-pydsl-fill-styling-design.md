# pydsl Fill and Draw Styling — Design

## Problem

pydsl has zero styling surface. `draw(obj)` takes no style argument at all
— it unconditionally records a bare `Draw(obj=obj.id)` with `style=None`.
There is no `fill()` function; the IR's existing `Fill` op is never
constructed anywhere in `pydsl/`. This was surfaced directly by Cluster C's
review: `sector()` was documented as "fillable," but nothing in pydsl could
actually fill it — the pitch was a dead end.

Investigating the underlying plumbing surfaced a second, blocking gap:
`Builder.build()` doesn't even pass `styles=` to `DiagramIR` — any style
dict a script builds today would silently vanish, because the IR's own
`RenderBase.style` field is just a string key into `DiagramIR.styles`
(`Dict[str, Dict[str, str|int|float|bool]]`), and nothing in `builder.py`
populates that dict. This is fixed here, since every function in this
cluster depends on it.

## What already exists vs. what's genuinely missing

- **IR layer**: `RenderBase.style: Optional[StyleId]` (a string key) on
  both `Draw` and `DrawPoints`; a separate `Fill(RenderBase)` op with
  `obj`, `holes: List[ObjId] = []`, `opacity: float = 1.0`. No structured
  `Style` model anywhere — `DiagramIR.styles` is an unvalidated free-form
  dict of primitives, interpretation left entirely to the renderer. This
  is why pydsl's own API isn't constrained by the IR's shape at all.
- **Recipe DSL**: scripts pass either a bare color string or a style dict;
  `lower.py._resolve_style()` auto-registers dicts under a generated key
  into `DiagramIR.styles`. pydsl needs the equivalent registration step
  (see Builder plumbing below) — the DSL already solved this problem,
  pydsl just never got the equivalent wiring.
- **Renderers**: `to_tikz.py::_style_str()` is a *generic pass-through* —
  any dict entry becomes a literal `key=value` (or bare `key` for
  `True`) TikZ option, so almost anything valid TikZ syntax already
  works today with zero renderer changes. `to_svg.py` is the opposite: a
  fixed, hardcoded vocabulary (`color`, `thick`, `thin`, `dashed`,
  `dotted`, `->`/`<-`/`<->` on `_stroke_attrs`; `fill`/`color`/`opacity`
  on `_fill_attrs`) — anything outside that list silently does nothing
  under `SVGRenderer`, which is what every pydsl example so far has
  actually rendered through (no Docker needed).
- **pydsl**: confirmed zero style capability — `draw()`'s signature has no
  style parameter, and no `fill()` exists.

## Scope: SVG's vocabulary, plus one deliberate addition

Because `SVGRenderer` is the actual renderer every pydsl script has run
through in this project so far, and `to_svg.py`'s vocabulary is a fixed,
smaller subset of what TikZ's pass-through allows, this design scopes
pydsl's style API to what SVG can actually render — **except** for one
addition: numeric stroke width, which is worth a small, scoped change to
`to_svg.py` (see below) rather than leaving it out.

**In scope:** stroke color, thick/thin presets, an explicit numeric
stroke width override, dashed/dotted, arrow direction, fill color, fill
opacity.

**Explicitly out of scope** (real TikZ-only capabilities today; backlogged
as a future `SVGRenderer` improvement, not solved by this cluster):
- Fill patterns (TikZ's `pattern=north east lines` etc. — `to_svg.py` has
  no SVG `<pattern>` element wiring at all).
- Stroke opacity (only `Fill`'s opacity field exists on the IR/renderer
  side; there's no stroke-opacity equivalent).
- Custom dash spacing (SVG's `dashed`/`dotted` are fixed `stroke-dasharray`
  values, not parameterized).
- Gradients, or any other TikZ option not in `to_svg.py`'s fixed list.

A script that needs one of these today has no path to it through pydsl,
same as before this cluster — this design doesn't regress anything, it
just doesn't attempt to paper over renderer gaps that are genuinely
renderer work, not API-surface work.

## API surface

### Builder plumbing (prerequisite for everything else)

`geometry_diagrams/pydsl/builder.py`'s `Builder` gains:

```python
self._styles: dict[str, dict] = {}
```

and a new method:

```python
def _register_style(self, style: dict) -> str:
    """Register a non-empty style dict, returning a fresh key into
    DiagramIR.styles. Always creates a fresh key — no dedup across
    identical style dicts; the number of draw()/fill() calls in a real
    script is small enough that this isn't worth the complexity."""
    key = self._fresh_hidden_id("style")
    self._styles[key] = style
    return key
```

`build()` changes from:
```python
return DiagramIR(define=list(self._defs), render=list(self._render), canvas=self._canvas)
```
to:
```python
return DiagramIR(define=list(self._defs), render=list(self._render), canvas=self._canvas, styles=dict(self._styles))
```

### `draw()`

```python
def draw(
    obj,
    color: "str | None" = None,
    thick: bool = False,
    thin: bool = False,
    width: "float | None" = None,
    dashed: bool = False,
    dotted: bool = False,
    arrow_start: bool = False,
    arrow_end: bool = False,
) -> None:
    """Draw a constructed object (triangle, polygon, circle, arc, sector,
    line, or segment), with optional stroke styling:
    - color: any string the renderer understands (not validated by pydsl
      itself — passed straight through, matching the recipe DSL's own
      permissiveness).
    - thick/thin: preset stroke widths. Give at most one, and not
      together with width.
    - width: an explicit numeric stroke width, given instead of
      thick/thin (must be positive).
    - dashed/dotted: give at most one.
    - arrow_start/arrow_end: draw an arrowhead at the start/end of the
      shape's path. For an open shape (line/segment/ray/arc) this marks
      the obvious start/end point. For a closed shape (polygon, circle,
      sector) the underlying renderers do not treat this consistently —
      SVG's polygon/path elements DO honor start/end markers at the
      shape's first/last recorded vertex (confirmed directly in
      to_svg.py — attrs including marker-start/marker-end spread onto
      the <polygon>/<path> element the same as any other shape), so an
      arrow can visibly appear on a polygon under SVGRenderer even
      though nothing here explicitly asked for that. Not rejected, but
      the correct expectation is "an arrow may appear at an arbitrary
      vertex," not "no effect."
    """
```

Validation (immediate, before any builder call — mirrors `ellipse()`'s
exactly-one-of-a-group style):

```python
    if isinstance(obj, Point):
        raise ValueError("draw() doesn't take a Point — use draw_points(...) instead")
    if isinstance(obj, AngleRef):
        raise ValueError("draw() doesn't take an AngleRef — use mark_angle(...) instead")
    width_group = [thick, thin, width is not None]
    if sum(width_group) > 1:
        raise ValueError("draw(): give at most one of thick, thin, or width")
    if width is not None and width <= 0:
        raise ValueError(f"draw(): width must be positive, got {width!r}")
    if dashed and dotted:
        raise ValueError("draw(): give at most one of dashed or dotted")

    style: dict = {}
    if color is not None:
        style["color"] = color
    if thick:
        style["thick"] = True
    if thin:
        style["thin"] = True
    if width is not None:
        style["line_width"] = width
    if dashed:
        style["dashed"] = True
    if dotted:
        style["dotted"] = True
    if arrow_start and arrow_end:
        style["<->"] = True
    elif arrow_start:
        style["<-"] = True
    elif arrow_end:
        style["->"] = True

    builder = get_builder()
    style_key = builder._register_style(style) if style else None
    builder._add_render(Draw(obj=obj.id, style=style_key))
```

The existing `Point`/`AngleRef` rejection checks are unchanged — this is
additive to `draw()`'s current body, not a rewrite of its validation.

### `fill()`

```python
def fill(obj, color: "str | None" = None, opacity: float = 1.0) -> None:
    """Fill a constructed object's interior (triangle, polygon, circle,
    sector) with the given color. opacity is 0 (fully transparent) to 1
    (fully opaque). Filling a shape with no enclosed interior (a line,
    segment, ray, or arc) has no defined visual effect and is not
    rejected — same permissiveness as draw()'s arrow_start/arrow_end on a
    closed shape."""
    if isinstance(obj, Point):
        raise ValueError("fill() doesn't take a Point — use draw_points(...) instead")
    if isinstance(obj, AngleRef):
        raise ValueError("fill() doesn't take an AngleRef — use mark_angle(...) instead")
    if not 0 <= opacity <= 1:
        raise ValueError(f"fill(): opacity must be between 0 and 1, got {opacity!r}")

    from geometry_diagrams.ir.ir import Fill

    style: dict = {}
    if color is not None:
        style["color"] = color
    # opacity is ALSO written into the style dict, not left to Fill's own
    # `opacity` field alone. to_tikz.py's Fill handler (verified directly —
    # lines 281-286) only merges in Fill.opacity when NO style dict is
    # registered; the moment a style dict exists (e.g. because color was
    # given), the TikZ path builds its options string purely from that
    # dict and Fill.opacity is silently ignored, rendering fully opaque
    # regardless of what was asked for. Writing "opacity" into the style
    # dict closes this: to_svg.py's _fill_attrs already prefers the style
    # dict's opacity over the Fill op's own field (`d.get("opacity",
    # opacity)`), and to_tikz.py's generic pass-through emits a valid
    # `opacity=0.3` TikZ option from the same dict entry. Fill.opacity is
    # still also set below, so a script with no color still gets correct
    # opacity via to_tikz.py's else-branch fallback (`opacity={opacity}`).
    if opacity != 1.0:
        style["opacity"] = opacity

    builder = get_builder()
    style_key = builder._register_style(style) if style else None
    builder._add_render(Fill(obj=obj.id, opacity=opacity, style=style_key))
```

`Fill` is imported locally (matching the existing local-import style used
elsewhere in `api.py`, e.g. `circumcircle()`'s `CircleCenterPoint`).

### Renderer changes: the `line_width` style key

`to_svg.py::_stroke_attrs` gains one branch, alongside the existing
`thick`/`thin` checks:

```python
        if "line_width" in d:
            attrs["stroke-width"] = str(d["line_width"])
```

`to_tikz.py::_style_str` needs a **correctness fix**, not just a new
capability: its current generic pass-through (`f"{k}={v}"`) would emit
`line_width=2.0`, which is not valid TikZ syntax (the real option is
`line width=2pt`, with a space and a unit). Add a special case before the
generic fallback:

```python
def _style_str(style_key: str | None, styles: dict) -> str:
    """Return a TikZ option string like '[color=red,thick]' or '' if no style.

    If style_key is found in the styles dict, format its entries as TikZ options.
    If not found but the key is a recognized TikZ color name, return '[color=<name>]'
    so that LLM-generated style values like "red" work without a populated styles dict.
    """
    if not style_key:
        return ""
    if style_key in styles:
        parts = []
        for k, v in styles[style_key].items():
            if v is False:
                continue
            if k == "line_width":
                parts.append(f"line width={v}pt")
            elif v is True:
                parts.append(k)
            else:
                parts.append(f"{k}={v}")
        return f"[{','.join(parts)}]" if parts else ""
    if style_key in _TIKZ_COLOR_NAMES:
        return f"[color={style_key}]"
    return ""
```

This means a pydsl script using `draw(obj, width=2.0)` renders correctly
under **both** `SVGRenderer` and `TikZRenderer` — the one place in this
cluster where a renderer change benefits both paths, not just SVG's. One
caveat worth stating plainly rather than leaving implicit: "correctly"
means *valid syntax that the renderer accepts*, not *visually identical
thickness* — SVG's stroke-width is in user units (default 1.5, `thick`
preset 2.5) while TikZ's line width is in points (default 0.4pt, `thick`
preset 0.8pt). `width=2.5` looks like the `thick` preset under SVG but
is roughly 3x the `thick` preset's actual thickness under TikZ. This is
a pre-existing unit mismatch between the two renderers' style
vocabularies (not something this cluster introduces or needs to
reconcile) — worth documenting so nobody later tries to "fix" a
perceived rendering discrepancy that's actually just SVG-vs-TikZ unit
semantics.

## Non-goals

- Fill patterns, stroke opacity, custom dash spacing, gradients — see
  "Scope" above. Backlogged as future `SVGRenderer` work, not attempted
  here.
- No color-name validation. `color` is passed straight through
  unvalidated, by explicit choice — matches the recipe DSL's own
  permissiveness; a typo'd color name renders as whatever the renderer's
  own fallback does (SVG: browsers already reject unknown CSS color
  values gracefully by rendering `currentColor`'s default; TikZ: an
  undefined color name is a LaTeX compile error surfaced through the
  existing render-pipeline error path, not a new silent-failure mode this
  cluster introduces).
- No style deduplication in `Builder._register_style` — every styled
  `draw()`/`fill()` call gets its own fresh entry in `DiagramIR.styles`.
  Not worth the complexity for typical script sizes.
- No combined `draw(obj, fill_color=...)` — `draw()`/`fill()` stay
  separate, matching the IR's own Draw/Fill separation (confirmed
  explicitly with the user during brainstorming).

## Testing

New file `tests/test_pydsl_styling.py`, TDD, covering:

- `Builder._register_style()`: registers a style dict under a fresh key,
  returns that key; `build()`'s resulting `DiagramIR.styles` contains it
  with the exact dict given.
- `draw()`: each style kwarg (`color`, `thick`, `thin`, `width`, `dashed`,
  `dotted`, `arrow_start`, `arrow_end`) individually produces the correct
  single-key style dict, recorded via the correct `Draw.style` key,
  record-level (inspect `ir.styles[recorded_key]`); calling `draw(obj)`
  with no style kwargs records `style=None` and adds nothing to
  `ir.styles` (existing zero-overhead behavior preserved); `thick`+`width`
  together raises `ValueError` mentioning "at most one"; `thick`+`thin`
  together raises the same; `dashed`+`dotted` together raises;
  `width=0` and `width=-1` both raise `ValueError` mentioning "positive";
  the existing `Point`/`AngleRef` rejection tests still pass unchanged.
- `fill()`: records a `Fill` op with correct `obj`/`opacity`/`style`
  fields; `opacity` outside `[0, 1]` raises; `color=None, opacity=1.0`
  (both defaults) records `style=None` (no dict registered) — same
  zero-overhead-when-unused behavior as `draw()`; `color=None,
  opacity=0.5` (non-default opacity, no color) still registers a style
  dict containing `{"opacity": 0.5}` even though no color was given —
  this is required for the TikZ-path fix below to work regardless of
  whether a color is also specified.
- **The TikZ fill-opacity regression** (found during spec review — a real
  bug in the *existing* renderer, not something introduced by this
  cluster, but one this cluster's `fill()` must not reproduce): a
  render-level test asserting `fill(obj, color="red", opacity=0.3)`
  produces a TikZ options string containing `opacity=0.3` — this is the
  case that was previously silently dropped, since `to_tikz.py`'s `Fill`
  handler only merges in `Fill.opacity` when no style dict is registered
  at all, and giving a color always registers one. Test both with and
  without a color to confirm opacity survives either way.
- `to_svg.py`'s new `line_width` branch: a compile-level/render-level test
  (using the existing SVG-checking utilities in `geometry_diagrams/util/`
  or a direct call into `to_svg.py`'s rendering function) asserting a
  `draw(obj, width=3.5)` call produces an SVG element with
  `stroke-width="3.5"`.
- `to_tikz.py`'s `line_width` special case: a direct test of `_style_str`
  (or the equivalent public rendering entry point) asserting
  `draw(obj, width=2.0)` produces `line width=2.0pt` in the TikZ options
  string, not the invalid `line_width=2.0`. Also test that every
  existing, previously-supported style key (`color`, `thick`, `thin`,
  `dashed`, `dotted`, `->`, `<-`, `<->`) still produces identical output
  to before this cluster's `_style_str` rewrite — a regression test for
  the rewrite itself, not just the new key.
- A sandbox-path test (`run_script`) exercising `draw(obj, color=...,
  width=...)` and `fill(obj, color=..., opacity=...)` through the real
  sandbox, confirming the resulting `DiagramIR` has correctly-populated
  `styles` and the right `Draw`/`Fill` render ops.

# pydsl Elliptical Arcs/Sectors and Open Polylines — Design

## Problem

Reframing an earlier broad "enable the most math diagrams" audit finding
specifically for this project's actual domain — geometry diagrams, not
general algebra/graphing — surfaced two gaps that are genuinely
*geometric*, unlike a generic function-plotter or number-line (both
descoped as more algebra-domain than geometry-domain):

- **Elliptical arcs/sectors don't exist at all.** Circles have
  `ArcCenterStartEnd`/`SectorCenterStartEnd`; ellipses have only
  whole-shape definitions (`EllipseCenterAxes`, `EllipseBBox`,
  `EllipseFoci`, `EllipseCenterEccentricity`) — no partial-ellipse concept
  anywhere in the IR.
- **No open (non-closing) multi-point path exists.** `Polygon` and its
  variants (`PolygonExterior`, `PolygonOnEdge`) are all closed-only. This
  blocks locus tracing — a classical synthetic-geometry topic ("trace the
  path of the midpoint of PQ as P moves around circle C") — which has no
  workaround today: connecting N points into a visible open curve simply
  isn't possible.

Unlike every prior cluster this session (A–D, Tier 1), which wrapped IR
capabilities that were *already fully rendered* — pure pydsl-layer
exposure — **neither of these exists in the IR at all yet**. Both need new
IR schema, new `to_sympy.py` compilation, and new rendering logic in both
`to_tikz.py` and `to_svg.py`. Scoped directly against the actual code
before committing to this (not estimated abstractly): both turned out to
be moderate, well-contained extensions, not rewrites — see each section
below for exactly why.

**Explicitly out of scope** (per the domain reframing that produced this
spec): generic `plot(f(x))` function graphing, a number-line primitive,
and any actual locus-solving/curve-fitting — `polyline()` is a raw
connect-the-dots primitive; a script computes its own points in its own
loop, the same way `walk()` already works. Nothing here attempts to find
or trace a locus automatically.

## Elliptical arcs/sectors

### The real geometric subtlety, verified directly against the renderer code

`ArcCenterStartEnd`/`SectorCenterStartEnd` derive their radius from
`center.distance(start)` at compile time (`to_sympy.py`) — this doesn't
generalize to an ellipse, since "distance from center" isn't a
well-defined single number for an ellipse boundary point. So the new IR
classes store `hradius`/`vradius` explicitly, mirroring
`EllipseCenterAxes`'s fields, rather than deriving them.

More subtly: `render_util.py::arc_params()` (used by both renderers)
computes each endpoint's angle via plain `atan2(y-cy, x-cx)` — correct for
a circle, but **wrong for an ellipse**. A point on an ellipse's boundary
is parameterized as `(cx + a·cos t, cy + b·sin t)`, so the correct
parametric angle is `atan2((y-cy)/b, (x-cx)/a)`, not plain `atan2`. Using
the wrong formula would silently compute the wrong start/end angles
whenever `hradius != vradius`. This is a genuine geometric correction,
not just a signature change — confirmed by reading `arc_params()`'s full
implementation directly.

**Both renderers already support non-uniform (elliptical) radii at the
syntax level, requiring no new drawing primitive:** TikZ's native `arc`
operation accepts `x radius=`/`y radius=` as separate keys (confirmed TikZ
syntax); SVG's path `A` (arc) command already takes separate `rx`/`ry`
parameters — today's circular-arc code just happens to pass the same
value for both. So the renderer changes are small, mechanical
substitutions once the angle math above is corrected, not new rendering
architecture.

### API surface: extend `arc()`/`sector()`, don't add new functions

Rather than a parallel `elliptical_arc()`/`elliptical_sector()` family,
`arc()`/`sector()` are extended to accept either a `Circle` or an
`Ellipse` — one mental model ("the arc/sector between two points on some
conic's boundary"), not two parallel APIs. **This is a deliberate
ergonomics bet the user is explicitly skeptical of** — not because the
mechanism is wrong, but because it's unclear whether an LLM writing a
script will reach for `arc(ellipse, ...)` naturally or find it confusing
that the same function's first parameter can be two different shape
types. Rather than resolve this by further design discussion, the plan is
to implement it as specified here and evaluate with real LLM-generated
examples afterward — the same validation approach used for every prior
cluster's ergonomics questions. If real usage shows confusion, revisit
before iterating further, since redesigning without evidence would just
be guessing at greater risk than the small implementation cost of trying
it first.

```python
def arc(shape: "Circle | Ellipse", start: Point, end: Point, reflex: bool = False) -> Arc:
    """The arc between start and end on shape's boundary (shape can be a
    circle() or an ellipse() — both must lie on shape; use point_on(shape,
    angle) to construct them). reflex=False (the default) draws whichever
    of the two arcs spans <=180° (in the parametric angle sense for an
    ellipse); reflex=True draws the other one."""


def sector(shape: "Circle | Ellipse", start: Point, end: Point, reflex: bool = False) -> Sector:
    """The closed pie-slice region bounded by the two radii to start and
    end and the arc between them, on shape's boundary. Same start/end
    contract as arc()."""
```

The `shape` parameter name (not `circle`, to accommodate both types) is a
signature-breaking rename from the current `arc(circle, start, end,
reflex=False)`. Since this session's convention has consistently favored
positional calls in generated examples over keyword `circle=` calls, and a
grep of the existing test suite confirms no test currently calls
`arc(circle=...)`/`sector(circle=...)` by keyword, this rename is safe —
confirm this grep again at implementation time before committing to it,
since it's the one place this spec assumes something about calling
convention that should be re-verified against the actual test suite
immediately before making the change.

Both functions share one private dispatcher (mirroring the
`_mark_segments` shared-helper pattern from the Tier 1 cluster):

```python
def _arc_or_sector(kind: str, shape, start: Point, end: Point, reflex: bool) -> str:
    """Build and record the correct IR def (circular or elliptical
    arc/sector) based on whether shape is a Circle or Ellipse. Returns the
    fresh id. kind is "arc" or "sector"."""
    from geometry_diagrams.ir.ir import (
        ArcCenterStartEnd, EllipticalArcCenterStartEnd,
        EllipticalSectorCenterStartEnd, SectorCenterStartEnd,
    )

    if isinstance(shape, Ellipse):
        _validate_on_ellipse(kind, shape, start, "start")
        _validate_on_ellipse(kind, shape, end, "end")
        # shape.hradius/.vradius are lazy thunks (Circle/Ellipse's established
        # pattern) — for an ellipse() built from corner1/corner2 whose corners
        # aren't concrete yet, this thunk raises NotImplementedError (the
        # exact same failure mode circumcircle(...).radius already has).
        # Re-raise as a ValueError naming arc()/sector() specifically, since
        # a bare NotImplementedError about ".hradius" would be a confusing
        # error to see from a call that never mentioned hradius/vradius at all.
        try:
            hradius, vradius = shape.hradius, shape.vradius
        except NotImplementedError:
            raise ValueError(
                f"{kind}(): shape's hradius/vradius aren't resolvable yet — "
                "this happens for an ellipse(corner1=..., corner2=...) built "
                "from non-literal corners. Use a literal ellipse(center=...) "
                "or a circle() instead."
            )
        builder = get_builder()
        new_id = builder._fresh_hidden_id(kind)
        def_cls = EllipticalArcCenterStartEnd if kind == "arc" else EllipticalSectorCenterStartEnd
        builder._add(def_cls(
            id=new_id, center=shape.center.id, hradius=hradius,
            vradius=vradius, start=start.id, end=end.id, reflex=reflex,
        ))
    else:
        _validate_on_circle(kind, shape, start, "start")
        _validate_on_circle(kind, shape, end, "end")
        builder = get_builder()
        new_id = builder._fresh_hidden_id(kind)
        def_cls = ArcCenterStartEnd if kind == "arc" else SectorCenterStartEnd
        builder._add(def_cls(id=new_id, center=shape.center.id, start=start.id, end=end.id, reflex=reflex))
    return new_id


def arc(shape, start, end, reflex=False):
    """..."""
    return Arc(id=_arc_or_sector("arc", shape, start, end, reflex))


def sector(shape, start, end, reflex=False):
    """..."""
    return Sector(id=_arc_or_sector("sector", shape, start, end, reflex))
```

### New validation guard: `_validate_on_ellipse`

Mirrors `_validate_on_circle` exactly in structure and skip-policy (skip
silently whenever any needed value isn't yet a concrete number), but
checks the ellipse boundary equation instead of a simple distance:

```python
def _validate_on_ellipse(fn_name: str, ellipse: "Ellipse", point: Point, point_role: str) -> None:
    """Raise if point is knowably NOT on ellipse's boundary. Same
    skip-when-unknowable policy as _validate_on_circle."""
    cx, cy = ellipse.center.x, ellipse.center.y
    px, py = point.x, point.y
    if cx is None or cy is None or px is None or py is None:
        return
    hr, vr = ellipse.hradius, ellipse.vradius
    if isinstance(hr, str) or isinstance(vr, str):
        return  # symbolic radii — not comparable; same defense-in-depth as circle's str-radius skip
    value = ((px - cx) / hr) ** 2 + ((py - cy) / vr) ** 2
    if abs(value - 1.0) > 1e-6:
        raise ValueError(
            f"{fn_name}(): {point_role} point {point.id!r} is not on the given "
            f"ellipse's boundary. Use point_on(ellipse, angle) to get a point "
            "guaranteed to lie on it."
        )
```

### `point_on()`'s docstring must be updated

Found during Fable review: `point_on()`'s error messages above, and this
whole spec's guidance, depend on `point_on(ellipse, angle)` being the
correct way to build `arc()`/`sector()`'s points for an ellipse — it
already works today (`to_sympy.py`'s `_eval_param` has an
`isinstance(obj, spg.Ellipse)` branch, confirmed), but `point_on()`'s own
docstring currently only mentions "a line or segment... or at angle t
(radians) on a circle" — it doesn't mention ellipses at all. Since
docstrings are the actual LLM-facing API contract in this project (via
`generate_stub()`), this gap would silently steer generated scripts away
from the one correct construction path this whole spec relies on. Update
`point_on()`'s docstring to mention ellipses alongside circles.

### New IR classes (`ir.py`)

```python
class EllipticalArcCenterStartEnd(DefBase):
    """Elliptical arc between `start` and `end` around `center`, with
    semi-axis lengths hradius/vradius. Draws the minor (parametric-angle
    <=180°) arc by default; set `reflex=True` for the other one."""
    kind: Literal["elliptical_arc_center_start_end"] = "elliptical_arc_center_start_end"
    center: PointId
    hradius: Union[int, float, str]
    vradius: Union[int, float, str]
    start: PointId
    end: PointId
    reflex: bool = False


class EllipticalSectorCenterStartEnd(DefBase):
    """Closed elliptical sector between `start` and `end` around `center`.
    Unlike EllipticalArcCenterStartEnd, this is a closed region and can be
    used as the `obj` of a Fill render op."""
    kind: Literal["elliptical_sector_center_start_end"] = "elliptical_sector_center_start_end"
    center: PointId
    hradius: Union[int, float, str]
    vradius: Union[int, float, str]
    start: PointId
    end: PointId
    reflex: bool = False
```

Both added to the `Def`/`DefStmt` discriminated union alongside the
existing circular versions.

### `to_sympy.py`: new marker classes, not modified existing ones

New `EllipticalArc`/`EllipticalSector` marker classes, parallel to the
existing `Arc`/`Sector` (which are left untouched — this cluster is
additive-only to avoid any regression risk to the already-fuzz-tested
circular-arc code from Cluster C):

```python
class EllipticalArc:
    """Marker type for an elliptical arc in the symbol table. Parallel to
    Arc, but with separate hradius/vradius instead of a single radius
    (an ellipse boundary point has no single well-defined distance from
    center, so hradius/vradius must be stored explicitly rather than
    derived)."""
    __slots__ = ("center", "start", "end", "hradius", "vradius", "reflex")

    def __init__(self, center, start, end, hradius, vradius, reflex=False):
        self.center = center
        self.start = start
        self.end = end
        self.hradius = hradius
        self.vradius = vradius
        self.reflex = reflex


class EllipticalSector:
    """Marker type for a closed elliptical sector. Parallel to Sector."""
    __slots__ = ("center", "start", "end", "hradius", "vradius", "reflex")

    def __init__(self, center, start, end, hradius, vradius, reflex=False):
        self.center = center
        self.start = start
        self.end = end
        self.hradius = hradius
        self.vradius = vradius
        self.reflex = reflex
```

Compilation cases, parallel to the existing circular ones — **and to
`EllipseCenterAxes`'s own case, not just `ArcCenterStartEnd`'s**: found
during Fable review, `EllipseCenterAxes` (`to_sympy.py:454-460`) resolves
`hradius`/`vradius` through `ev()` (SymPy's expression evaluator — needed
because the IR schema legally allows a `str` radius, e.g. a symbolic
length expression) and validates both are positive before constructing
anything. The circular `ArcCenterStartEnd` case never needed this because
its radius is *derived* from `center.distance(start)`, never taken as a
raw schema field — but the elliptical case takes `hradius`/`vradius`
directly from the schema, so it needs exactly the same `ev()` +
positivity check `EllipseCenterAxes` already does, or a `str` radius
would survive uncaught into `elliptical_arc_params()`'s `sympy_to_float()`
and crash there instead, with a confusing error far from the actual
problem:

```python
case ir.EllipticalArcCenterStartEnd(center=center_id, hradius=hradius, vradius=vradius, start=start_id, end=end_id, reflex=reflex):
    c, s, e = ref(center_id), ref(start_id), ref(end_id)
    hr, vr = ev(hradius), ev(vradius)
    if float(hr.evalf()) <= 0 or float(vr.evalf()) <= 0:
        raise IRCompileError(
            did, f"elliptical_arc_center_start_end: hradius and vradius must be positive, got {hr}, {vr}"
        )
    return EllipticalArc(center=c, start=s, end=e, hradius=hr, vradius=vr, reflex=reflex)

case ir.EllipticalSectorCenterStartEnd(center=center_id, hradius=hradius, vradius=vradius, start=start_id, end=end_id, reflex=reflex):
    c, s, e = ref(center_id), ref(start_id), ref(end_id)
    hr, vr = ev(hradius), ev(vradius)
    if float(hr.evalf()) <= 0 or float(vr.evalf()) <= 0:
        raise IRCompileError(
            did, f"elliptical_sector_center_start_end: hradius and vradius must be positive, got {hr}, {vr}"
        )
    return EllipticalSector(center=c, start=s, end=e, hradius=hr, vradius=vr, reflex=reflex)
```

### `render_util.py`: new `elliptical_arc_params()`, not a modified `arc_params()`

Same additive-only reasoning as the marker classes — a new function,
parallel to `arc_params()`, with the corrected parametric-angle math:

```python
def elliptical_arc_params(arc_id: str, sym: "SymTable") -> tuple[float, float, float, float, float, float, float, float]:
    """Return (cx, cy, hr, vr, start_deg, end_deg, sx, sy) for the given
    elliptical arc id — parallel to arc_params(), but for an ellipse's two
    independent radii. The angle computation uses the ellipse's parametric
    form: atan2((y-cy)/vr, (x-cx)/hr), NOT plain atan2(y-cy, x-cx) — the
    latter is only correct when hr == vr (a circle). Getting this wrong
    would silently compute the wrong start/end angles whenever hradius !=
    vradius."""
    arc = sym[arc_id]
    cx = sympy_to_float(arc.center.x)
    cy = sympy_to_float(arc.center.y)
    hr = sympy_to_float(arc.hradius)
    vr = sympy_to_float(arc.vradius)
    sx = sympy_to_float(arc.start.x)
    sy = sympy_to_float(arc.start.y)
    ex = sympy_to_float(arc.end.x)
    ey = sympy_to_float(arc.end.y)
    s_deg = math.degrees(math.atan2((sy - cy) / vr, (sx - cx) / hr)) % 360.0
    e_deg = math.degrees(math.atan2((ey - cy) / vr, (ex - cx) / hr)) % 360.0
    ccw = (e_deg - s_deg) % 360.0
    if ccw == 0:
        ccw = 360.0
    is_ccw_minor = ccw <= 180.0
    want_reflex = bool(getattr(arc, "reflex", False))
    if is_ccw_minor == want_reflex:
        sx, sy, ex, ey = ex, ey, sx, sy
        s_deg, e_deg = e_deg, s_deg
    if e_deg <= s_deg:
        e_deg += 360.0
    return (cx, cy, hr, vr, s_deg, e_deg, sx, sy)
```

(The minor/reflex swap and normalization logic is copied verbatim from
`arc_params()` — confirmed during scoping that this part of the algorithm
carries over unchanged once the angle computation itself is fixed.)

### Renderer changes

**`to_tikz.py`**: new `elif isinstance(sym_obj, EllipticalArc):` /
`EllipticalSector` branches alongside the existing `Arc`/`Sector` ones (in
both the Draw and Fill handlers), calling `elliptical_arc_params()` and
emitting `\draw ... arc[start angle=...,end angle=...,x radius=...,y
radius=...]` instead of the circular version's single `radius=...`.

**`to_svg.py`**: new parallel branches computing the endpoint via the
ellipse's parametric form (`ex_g = cx_g + hr_g*cos(end_rad)`, `ey_g = cy_g
+ vr_g*sin(end_rad)` — NOT the circular version's single-radius formula),
and emitting the `A` path command with separate `rx`/`ry` instead of a
repeated single radius. This applies to both the plain-fill `Sector`-style
branch and `_obj_to_svg_subpath` (the holes-compound-fill helper from the
Tier 1 cluster) — both need their own new `EllipticalSector`/parametric
branch, following the exact same additive pattern already established for
`Sector` in that function.

No changes to `checks.py`/`queries.py` — confirmed neither module has any
circular-arc-specific logic to parallel.

### `render_util.py`'s bounds-expansion also needs a new branch

Found during Fable review: `expand_bounds_for_geometry` (or equivalently
named bounds-computation function, `render_util.py:218-243`) has a
branch for `spg.Ellipse` (whole ellipses) and one for the circular `Arc`
marker (using its full enclosing circle, `cx±r`/`cy±r`, as a conservative
bound) — but no branch for the new `EllipticalArc` marker at all. Without
one, an elliptical arc whose curve bulges outside the bounding box of its
own defined points would get clipped by the canvas, which is exactly the
failure mode the existing circular `Arc` branch exists to prevent. Add a
parallel branch using the ellipse's own two independent radii as the
conservative bound:

```python
elif isinstance(obj, EllipticalArc):
    cx, cy = sympy_to_float(obj.center.x), sympy_to_float(obj.center.y)
    hr = sympy_to_float(obj.hradius)
    vr = sympy_to_float(obj.vradius)
    # Conservatively use the full enclosing ellipse.
    if cx - hr < xmin:
        xmin = cx - hr - BOUNDS_PADDING
    if cx + hr > xmax:
        xmax = cx + hr + BOUNDS_PADDING
    if cy - vr < ymin:
        ymin = cy - vr - BOUNDS_PADDING
    if cy + vr > ymax:
        ymax = cy + vr + BOUNDS_PADDING
```

Note the existing `Arc` branch's bounds check has no `Sector` counterpart
either (a pre-existing gap, not something this cluster introduces) — this
cluster adds `EllipticalArc` only, matching that same existing asymmetry
rather than fixing an unrelated pre-existing gap outside its scope.

## Open polylines

### Why this is moderate, not architecturally risky

`Polygon`'s Pydantic schema (`ir.py`) has no closure encoded in it at all
— just `points: List[PointId]`; the docstring's "closed automatically" is
purely a downstream compile/render-time behavior, not a schema
constraint. Confirmed directly: closure lives at each renderer call site
(SVG's `<polygon>` element vs. the already-existing, unused-until-now
`<polyline>` element; TikZ's trailing `" -- cycle"` string) — not buried
in shared geometry math. This means an open variant is mechanical
duplication of ~8 call sites minus the closing edge, not a redesign.

SymPy itself has no open-multi-point-path geometry type (`spg.Polygon` is
inherently closed; `spg.Segment`/`spg.Ray` are 2-point-only). So the
compiled representation for a polyline is deliberately NOT a SymPy
geometry object — just a plain list of `spg.Point2D`, since no
closure-sensitive property (area, "is a point inside this") is ever
needed for an open path.

### API surface

```python
def polyline(*points: Point) -> Polyline:
    """An open path through 2 or more points, in order — unlike polygon(),
    this does NOT connect the last point back to the first. Use this for
    tracing a locus or any curve built from a sequence of computed points
    (e.g. from a loop calling rotate_point()/dilate_point()/point_on()
    repeatedly as a parameter sweeps) — polyline() only connects the dots
    you give it; it does not compute or solve for a locus itself."""
    if len(points) < 2:
        raise ValueError(f"polyline requires at least 2 points, got {len(points)}")
    for i in range(len(points) - 1):  # consecutive pairs only — no
        prev, cur = points[i], points[i + 1]  # wraparound check, unlike
        if prev.x is None or prev.y is None or cur.x is None or cur.y is None:  # polygon(),
            continue  # since there's no closing edge to
        if math.hypot(cur.x - prev.x, cur.y - prev.y) < 1e-9:  # accidentally duplicate
            raise ValueError(
                f"polyline() vertices {prev.id!r} and {cur.id!r} are coincident."
            )
    builder = get_builder()
    pid = builder._fresh_hidden_id("polyline")
    builder._add(PolylineOpen(id=pid, points=[p.id for p in points]))
    return Polyline(id=pid, vertices=tuple(points), _builder=builder)
```

`draw()` needs no changes — it already dispatches generically on
`obj.id`. `fill()` needs no changes either, in either of its two forms:
`fill(polyline)` (no holes) hits none of the renderer's
`isinstance(sym_obj, (spg.Triangle, spg.Polygon, spg.Circle, ...))`
branches and produces no output at all, no exception, no warning —
identical to today's existing behavior for `Segment`/`Ray`/`Arc` (already
documented in `fill()`'s own docstring as intentional permissiveness).
`fill(shape, holes=[polyline])` (polyline as a hole) is a different code
path — verified during Fable review — and produces a **warning**, not
silence: it routes through `_obj_to_svg_subpath`/`_obj_to_tikz_path`,
which return `None` for an unrecognized type, and the `Fill` handler logs
an explicit "unsupported shape type" warning for that hole rather than
failing silently. Both outcomes are already-existing, correct behavior
for any other unfillable type passed as a hole — no new code needed for
either case, just worth stating precisely rather than a blanket "silently
no-ops" that's only accurate for the first form.

### New IR class

```python
class PolylineOpen(DefBase):
    """Open path through 2+ points, in order. Unlike Polygon, does NOT
    close back to the first point."""
    kind: Literal["polyline_open"] = "polyline_open"
    points: List[PointId]
```

### `to_sympy.py`

```python
case ir.PolylineOpen(points=point_ids):
    return [ref(pid) for pid in point_ids]
```

Returns a plain Python list of `spg.Point2D`, not a SymPy geometry
object — this is a deliberate, minimal representation; there is no
existing SymPy type for an open point sequence, and none of the
downstream operations that matter for a polyline (draw it, don't fill it,
don't query its area) need one.

### `render_util.py`

New `poly_verts`-equivalent is not needed — the compiled representation is
already a plain point-id-ordered list from the case above; existing
`poly_verts()` used by Polygon is a separate function reading `stmt_by_id`
for `Polygon` specifically and doesn't need a parallel version, since
callers can get a `PolylineOpen`'s points directly from
`stmt_by_id[obj_id].points` the same way.

### Renderer changes (both files, ~8 call sites total, mechanical)

Each existing `isinstance(sym_obj, (spg.Triangle, spg.Polygon))` dispatch
site gains a sibling `elif isinstance(sym_obj, list):` branch (the
compiled `PolylineOpen` representation is a plain list, distinguishing it
structurally from every other compiled type without needing a dedicated
marker class):

- **SVG Draw**: emit `<polyline points="x1,y1 x2,y2 ...">` (SVG's native
  open counterpart to `<polygon>`) instead of `<polygon points="...">` —
  no `Z`/closing coordinate.
- **TikZ Draw**: emit `\draw (p1) -- (p2) -- ... -- (pn);` — same
  `" -- ".join(...)` construction Polygon already uses, just WITHOUT the
  trailing `" -- cycle"`.
- **`drawn_segments` loop** (SVG, used for downstream label-collision
  avoidance): iterate consecutive pairs `range(len(sv) - 1)`, not
  `(i+1) % len(sv)` — drop the wraparound pair.
- **Fill (both renderers)**: no new branch needed — `fill()` already
  no-ops on unmatched types (see above); the existing `isinstance(sym_obj,
  (spg.Triangle, spg.Polygon))` checks in the Fill handlers simply won't
  match a plain list, which is the correct, no-code-needed behavior.

### New handle (`handles.py`)

```python
@dataclass(frozen=True)
class Polyline:
    id: str
    vertices: tuple[Point, ...]
    _builder: "object" = field(repr=False, compare=False)
```

Deliberately minimal — no `.side()`/`.angle_at()` methods (unlike
`Polygon`'s handle). A `.side()`-equivalent for consecutive-point access
isn't clearly needed yet for the locus-tracing use case this is built for
(a script already has each point from its own loop, before ever calling
`polyline()`); add one later if a real need surfaces, per this session's
consistent YAGNI bias.

## Non-goals

- No automatic locus-solving, curve-fitting, or symbolic tracing —
  `polyline()` only connects points a script explicitly computed and
  passed in. Finding a locus is the script's own job (a loop over a
  parameter, calling existing point-construction functions), same as
  `walk()`'s existing division of responsibility.
- No generic `plot(f(x))` function-graphing primitive, no number-line
  primitive — both assessed as more algebra/precalc-domain than
  geometry-domain; explicitly descoped by the reframing that produced
  this spec.
- No `elliptical_arc()`/`elliptical_sector()` as separate functions — see
  the ergonomics discussion above; `arc()`/`sector()` are extended
  polymorphically instead, as an explicit experiment to validate with real
  LLM usage rather than resolved by further up-front design debate.
- No `.side()`/`.angle_at()` methods on the `Polyline` handle (see above).
- No changes to the existing circular `Arc`/`Sector` marker classes,
  `arc_params()`, or any of their existing test coverage — this cluster
  is additive-only for the elliptical case, to avoid any regression risk
  to the already-fuzz-tested Cluster C code.

## Testing

New file `tests/test_pydsl_ellipse_arcs_and_polylines.py`, TDD, covering:

- **Elliptical arc/sector**: `arc()`/`sector()` called with an `Ellipse`
  record the correct `EllipticalArcCenterStartEnd`/
  `EllipticalSectorCenterStartEnd` with correct `hradius`/`vradius`/
  `reflex` field mapping; called with a `Circle` still record the
  original circular defs unchanged (non-regression); `_validate_on_ellipse`
  rejects an off-ellipse point (both start and end, mirroring the
  Cluster-C dual-check regression test) and accepts a point exactly on
  the ellipse's boundary (hand-computed literal coordinates satisfying
  the boundary equation exactly); a compile-level test proving
  `elliptical_arc_params()`'s parametric-angle correction actually
  matters, using the exact numeric example verified during Fable review
  (independently re-derived, not just asserted): a real non-circular
  ellipse centered at the origin with `hradius=4`, `vradius=1`; the point
  at parametric angle `t=60deg` is `(4*cos60, 1*sin60) = (2.0, 0.8660)`.
  The correct parametric angle recovers exactly `60.0deg`
  (`atan2(0.8660/1, 2.0/4)`); plain, non-parametric `atan2(0.8660, 2.0)`
  gives `23.413deg` instead — a ~36.6-degree error. Assert the
  implementation produces `60.0` (within float tolerance), not `23.413`
  — this specific pair of numbers is what proves the fix is
  load-bearing, not cosmetic, since feeding the wrong angle back into
  the ellipse's parametric form lands nowhere near the original point
  (`(3.671, 0.397)` instead of `(2.0, 0.866)`); a render-level test for
  each renderer confirming `x radius=`/`y radius=`
  (TikZ) and separate `rx`/`ry` (SVG) actually appear with the correct,
  distinct values (not the same value repeated, which would silently mean
  the ellipse-specific code path was never reached).
- **Polyline**: `polyline()` records `PolylineOpen` with correct point-id
  order; rejects fewer than 2 points; rejects consecutive coincident
  points but does NOT reject a first/last coincidence (proving there's no
  accidental wraparound check — construct a polyline where the first and
  last points ARE coincident and confirm it's accepted, since that's a
  meaningful "closed-looking but still open" path, unlike `polygon()`
  where it would be redundant — a coincident-endpoint `<polyline>`/TikZ
  chain genuinely renders closed-looking, verified during Fable review:
  the only visual difference from a `polygon()` is the line join at the
  seam, invisible at normal stroke widths); a THREE-point degenerate case
  — `polyline(A, B, A)` — is explicitly accepted-and-degenerate, not an
  error: it passes the coincident-consecutive-pair guard (no two
  *consecutive* points are equal) and renders as an invisible retrace of
  segment A–B on the way back to A. This is harmless but should be
  pinned by a test asserting it does NOT raise, so nobody "fixes" it
  later into an error that would also reject the meaningful n≥4
  closed-looking-locus case just above; a render-level test for each renderer
  confirming the output is a `<polyline>` (SVG, not `<polygon>`) / lacks
  a trailing `-- cycle` (TikZ) for a 3+ point open path; `fill()` called
  on a `Polyline` doesn't raise and doesn't fill anything (matches
  existing Segment/Ray/Arc permissiveness, verified by asserting no fill
  element is added to the rendered output).
- A sandbox-path test (`run_script`) exercising `arc()`/`sector()` with
  an `Ellipse` and `polyline()` through the real sandbox, confirming
  names resolve and the resulting `DiagramIR` contains the expected def
  kinds.

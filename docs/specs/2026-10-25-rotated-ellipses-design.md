# Rotated (Tilted) Ellipses: Design

Design for letting the IR represent an ellipse whose axes are not horizontal
and vertical. Written for ticket 05 of the `curve-measures-and-gaps` effort
(branch `curve-measures-and-gaps`, after commit c6a32f1). This document
changes no code. It recommends a representation, inventories every place the
code assumes axis alignment, and proposes a staged rollout behind a feature gate. The first three
tickets are drafted for the human to approve; nothing is to be implemented
before that.

Function names below are the ones in the tree at c6a32f1. Line numbers are
left out on purpose because they drift.

## Problem and scope

Ellipses in scanned or PDF diagrams are often tilted. Every ellipse the IR can
express today is axis-aligned. The four full-ellipse kinds in `ir/ir.py`
(`EllipseCenterAxes`, `EllipseBBox`, `EllipseFoci`,
`EllipseCenterEccentricity`) and the two elliptical arc kinds
(`EllipticalArcCenterStartEnd`, `EllipticalSectorCenterStartEnd`) carry only
`hradius`/`vradius` (or an `orientation` of `horizontal`/`vertical`), and
`to_sympy._compile_one` turns them into `sympy.geometry.Ellipse`, which is
axis-aligned by construction. `EllipseFoci` refuses outright: foci that are not
on one horizontal or vertical line raise `IRCompileError` ("foci must be
axis-aligned").

In scope: the representation, how compiled geometry carries it, every consumer
of an ellipse, and the rollout. Out of scope: general affine transforms of
arbitrary objects, conics other than ellipses, and the open
elliptical-arc-and-sector intersection gap with float radii (already noted in
the ledger as an existing limit). The stage-2 solver happens to close part of
that gap, but closing it is not a goal here.

## Recommendation

1. **IR:** add one optional field, `rotation_deg: int | float | str = 0`,
   degrees counter-clockwise from the +x axis to the `hradius` axis. It goes
   on `ellipse_center_axes`, `ellipse_center_eccentricity`,
   `elliptical_arc_center_start_end` and `elliptical_sector_center_start_end`.
   `ellipse_foci` gets no field: its tilted-foci lift derives the rotation from
   the direction of the foci and arrives in stage 4 with the gate removal (see
   Feature gate); until then it keeps today's axis-aligned error. `ellipse_bbox` stays axis-aligned, because a bounding box is
   axis-aligned by definition. With the default of 0, stored IR is unchanged
   and compiles exactly as before.
2. **Compiled form:** a rotation whose evaluated value is exactly 0 after
   `% 360` (a literal 0, or an expression that evaluates to exactly 0.0)
   compiles to the same `spg.Ellipse` as today, so existing output stays byte-identical. Any
   other rotation compiles to a new non-SymPy marker type, `RotatedEllipse`
   (center, hradius, vradius, rotation in float radians), next to the existing
   `EllipticalArc` marker. The elliptical arc markers gain a `rotation` slot
   that defaults to 0. Every operation works in the ellipse's local frame: map
   points and lines into the frame with a float rotation, use the existing
   axis-aligned code or SymPy there, and map results back as `sp.Float`
   points.
3. **Gate:** a new feature group, `tilted_ellipses`, off by default, guards
   every generation surface through stages 1 to 3. With the group off,
   `require_features` rejects a generated diagram that uses a nonzero
   `rotation_deg`, and every default prompt stays byte-identical. Compile and
   render accept tilted ellipses either way. Stage 4 removes the group after
   an eval run (see Feature gate).
4. **Rollout:** stages 1, 1b, 2, 3 and 4. Stage 1 makes a tilted full ellipse
   compile, draw in both renderers at equal axis units and pass the basic
   checks and queries. Stage 1b adds SVG drawing under a non-unit canvas
   aspect and label nudging against the tilted outline. Stage 2 adds tangent
   lines and intersections. Stage 3 adds tilted elliptical arcs and sectors.
   Stage 4 adds the recipe and pydsl authoring surfaces, lifts the tilted-foci
   restriction, adds the prompts and evals, and removes the gate. Stages 1, 2
   and 1b are drafted as tickets 06, 07 and 08.

### Rejected alternatives

- **Subclass `spg.Ellipse` with a rotation attribute.** About 31
  `isinstance(obj, spg.Ellipse)` sites (to_sympy 15, checks 3, queries 4,
  render_util 2, to_svg 3, to_tikz 3, curve_measures 1) and SymPy's own
  methods (`intersection`, `tangent_lines`, `contains`, `equation`) would
  silently treat the object as axis-aligned and return wrong answers instead
  of errors.
- **Always use the marker, even when rotation is 0.** This breaks byte
  identity for every existing ellipse and gives up the exact SymPy path for
  the common case, for no benefit.
- **Rotation as an exact SymPy angle (`pi * deg / 180`).** SymPy cannot
  rotate an `Ellipse` by anything other than a multiple of pi/2, and exact
  angles that do not simplify (37 degrees, for example) make intersection and
  tangent solving take more than 30 s (see Measured facts).
- **Foci-and-point as the only way to tilt.** That is a construction, not a
  representation, and it still needs the rotated compiled form. It is kept as
  a construction: `ellipse_foci` stops rejecting tilted foci in stage 4.
- **A transform wrapper (`transformed: {of, rotate, about}`).** It is a wider
  feature: rotated polygons are already expressible with `point_rotate`, and
  points are the only other thing that could be wrapped. It adds an extra id
  that the model must name and draw, and it compiles to the same rotated
  marker anyway.
- **Radians for the IR field.** `point_rotate.angle` uses radians, but tilts
  are stated in degrees in source diagrams, the expression function `angle()`
  returns degrees (so `rotation_deg: "angle(X, O, F2)"` needs no wrapper), and
  prism `depth_angle` and recipe `rotation` already use degrees. The `_deg`
  suffix removes the ambiguity, as it does for `expected_deg`. pydsl keeps
  radians at its own surface (see Authoring surfaces).

## Representation in the IR

`rotation_deg: Union[int, float, str] = 0`. A string is an expression, as for
`hradius`. It must be added to `refs._EXPR_FIELDS` so that ids named inside
the expression take part in the topological sort, and to `_NON_REF_FIELDS`.
Rotation is about the ellipse's center, counter-clockwise, measured to the
`hradius` axis. "hradius" therefore means "the semi-axis along `rotation_deg`",
which is horizontal only when the rotation is 0. The field names stay as they
are so stored IR stays valid. The docstrings change from "Axis-aligned ..." to
say this.

- `ellipse_center_axes`: gets the field.
- `ellipse_center_eccentricity`: gets the field. `orientation: vertical` stays
  and composes with it: vertical is the same as horizontal plus 90 degrees, so
  the compiler can fold orientation into the rotation, except that the
  semi-axis naming must be kept as today when the rotation is 0.
- `ellipse_foci`: no field. The rotation is `atan2(dy, dx)` of focus1 to
  focus2. When dx == 0 or dy == 0 the compiler keeps today's exact
  axis-aligned path, so existing foci IR is byte-identical. For tilted foci it
  builds `RotatedEllipse(center, a, b, rotation)`, with `a` on the focal axis.
  This lift waits for stage 4, when the gate is removed. Whether foci are
  tilted is known only after the points compile, so `require_features`, which
  runs on the uncompiled diagram, could not gate it. Keeping today's
  axis-aligned error until then avoids a post-compile gate. It also keeps the
  recipe, the main strategy, from producing tilted ellipses through its
  existing foci form before the feature is complete.
- `ellipse_bbox`: no field.
- `elliptical_arc_center_start_end` / `elliptical_sector_center_start_end`: get
  the field. An elliptical arc does not reference a parent ellipse id; it
  repeats the center and radii. So the rotation is repeated too, and the
  authoring surfaces copy it from the parent ellipse.

Serialization: `model_dump` of re-serialized IR gains `"rotation_deg": 0` on
those kinds, the same way `reflex: false` already appears. No test fixture
pins a dumped IR containing an ellipse (grep of `tests/`); old IR loads
unchanged.

## How compiled geometry carries it

`RotatedEllipse` lives in `to_sympy.py` with the other markers (`Arc`,
`EllipticalArc`, ...). It exposes `center` (an `spg.Point`), `hradius`,
`vradius` (SymPy numbers), `rotation` (a Python float, radians), and two
helpers that every consumer uses instead of re-deriving the math:
`to_local(x, y) -> (u, v)` (subtract the center, rotate by -rotation) and
`to_world(u, v) -> (x, y)`. Elliptical arc markers gain `rotation` (default
0.0) and the same two helpers. A shared helper in `to_sympy.py` (for example
`local_axis_ellipse(obj) -> spg.Ellipse` centered at the origin) gives
consumers an axis-aligned SymPy ellipse to work with in the local frame.

Because the marker is not an `spg.Ellipse`, any site that has not been taught
about it falls through to that site's "unsupported type" branch instead of
computing an axis-aligned answer. That makes partial support loud. Stage 1
must make sure each fall-through is a typed error and not a crash or a silent
skip. Three known risks:

- `PointIntersection` calls `obj1.intersection(obj2)`, which would raise
  `AttributeError` on the marker.
- the SVG Draw/Fill dispatch has no final `else`, so an unknown type is
  silently not drawn.
- `_sample_param` returns `rng.random()` (range [0, 1)) for any type that is
  not an `spg.Ellipse`, which is the wrong range for a full ellipse.

**Numerical robustness.** The rotation is evaluated once to a Python float
(`float(ev(rotation_deg)) % 360`, then converted to radians). Exactly 0 takes
the existing exact path. Any other value builds the marker, and all
world-space results are lifted as `sp.Float(x, 17)` through the existing
`_lift`, which is how circular and elliptical arc points are already produced
by `_eval_param`. A float rotation is never turned into an exact Rational:
the solids decision record already notes that floats turn into 16-digit
rationals inside SymPy, and the experiments below show that exact
non-simplifying angles stall the solver. Double precision is far tighter than
the tolerances involved (`PICK_CONTAINS_TOL`, `INTERSECT_TANGENT_TOL`, the 5e-3
check default).

Only an evaluated rotation of exactly 0 (after `% 360`) is normalized. An
expression-valued rotation that evaluates to about 1e-15 is not snapped to 0:
it builds a marker. A 180 degree rotation gives the same curve but
moves the start of the parametric angle by pi, and 90 degrees swaps the
`hradius` direction, so normalizing either one would change
`point_on(ellipse, t)`. A marker with equal radii and a nonzero rotation stays
a marker (SymPy would turn `Ellipse(c, r, r)` into a `Circle` and lose the
start of the parametric angle). The radius checks already accept hr == vr as
circular.

## Parametric angle and sweep semantics

On a rotated ellipse, the point at parametric angle t is
`C + R(rotation) . (hr cos t, vr sin t)`. t is measured in the local frame,
from the `hradius` axis. The inverse is `atan2(v / vr, u / hr)` of the local
coordinates. This is the only definition that keeps `point_on(e, t)` the same
curve-relative position at every tilt.

**`arc_param_frame` survives.** It returns `(cx, cy, hr, vr, start, end)`
with start and end as parametric angles. If it computes start and end from
the local coordinates of the arc's start and end points, the 6-tuple keeps its
meaning. Its consumers that only use `hr, vr, start, end` (`curve_length`,
`query_area`, `query_perimeter`, `_check_congruent_arcs`) then need no change
at all. The consumers that map back to world space (`_eval_param`,
`_invert_param`, `_point_in_arc_sweep`) additionally apply `obj.rotation`.
The same goes for `render_util.elliptical_arc_params` (the renderer's copy of
that frame) and `to_sympy._reflex_for_bulge_toward`, which recomputes
parametric angles with plain `atan2((y - cy) / vr, (x - cx) / hr)`.
`arc_param_frame` is already a public name.
This change is a good time to give it a `rotation` companion,
for example a small frame object with `to_local`/`to_world`.

**Reflex and CCW survive.** A rotation is a rigid motion that keeps
orientation, so counter-clockwise in the local frame is counter-clockwise in
the world, and the parametric span is the same. The swap rule shared by
`arc_param_frame`, `arc_sweep_degrees` and `elliptical_arc_params`
(`(ccw <= pi) == reflex`) is valid unchanged once the angles are local.

**`ArcBetweenConstraint`** (`_check_spatial_constraint`) measures polar angle
about the center, and its comment justifies that by saying polar angle is
increasing in parametric angle for an axis-aligned ellipse. That still holds
after a rotation, because polar angle only shifts by a constant, so it needs
no change. Only the comment needs updating.

## Tangent lines, intersections and the sweep filter

- **`line_tangent`** (the `ir.LineTangent` case) calls
  `_underlying_conic(target).tangent_lines(point)`. For a rotated ellipse:
  move the point into the local frame (in floats), call `tangent_lines` on the
  local axis-aligned SymPy ellipse, and rotate the lines back.
  Measured: 0.04 s with a float angle, versus a timeout with an exact
  37-degree angle.
- **`_tangent_touch_point`** (used by line_tangent's picks and by the
  `Tangent` check) finds the extreme point along the line normal for an
  axis-aligned ellipse. Rotate the line coefficients into the local frame
  first: `(a, b)` becomes `(a cos r + b sin r, -a sin r + b cos r)`, and the
  constant term is shifted for the center.
- **`Tangent` check** (`checks._check_one`): the support-function distance
  `hypot(hr * a, vr * b) / norm` must use the local-frame normal. Its
  `_conic_frame` helper returns `(cx, cy, hr, vr)` and has to return or expose
  the rotation as well. `_conic_frame` is shared with the radius checks, which
  are rotation-invariant (see below).
- **Line, segment or ray x rotated ellipse** (`PointIntersection`): transform
  the line into the local frame, intersect it with the local SymPy ellipse,
  and map the points back. `_tangent_candidates` already solves line x
  ellipse in the ellipse's unit-circle frame from `ha, va` and the line
  endpoints. Feeding it local-frame endpoints is the whole change there.
- **Circle x rotated ellipse:** a circle stays a circle in the local frame,
  so rotate its center (as a float) and use SymPy's ellipse x circle (1.45 s
  measured with a float angle; it timed out with an exact rotation of the
  center).
- **Ellipse x ellipse where either one is rotated:** neither can be expressed
  as an `spg.Ellipse` in the other's frame. Use a numeric solver: put one
  ellipse's half-angle parametrization into the other's implicit quadratic,
  which gives a quartic. Solve it with `mpmath.polyroots` (which ships with
  SymPy, so no new dependency), check t = pi separately because the half-angle
  substitution misses it, polish with Newton if needed, and lift the points.
  Measured: 0.02 s, the same root count as `sp.solve` (3.5 s).
  `_count_ellipse_crossings` (the "could not solve" diagnostic) samples an
  axis-aligned parametrization against an axis-aligned implicit form, and both
  need the transforms. This solver could also replace SymPy for float-radius
  axis-aligned pairs, which is the existing documented limit, but that would
  be a separate decision.
- **Sweep filter:** `_point_in_arc_sweep` comes along automatically once
  `arc_param_frame` is local. The filter itself (`within = [...]` in
  `PointIntersection`) does not change.
- **`_on_object`** (pick_on_object on a non-arc object) needs a
  `RotatedEllipse` branch: the local implicit equation within
  `PICK_CONTAINS_TOL`.

## Congruent arcs under rotation

The symmetry argument does not change. That surprised me, so here is why.
`_ellipse_arcs_congruent` decides whether two arcs, each written as
`(hr, vr, start, end)` in its own ellipse's parametric angle, are related by a
rigid motion. It enumerates the symmetries of an axis-aligned ellipse (the
half turn, reflection across either axis, and the swapped-axes quarter turn).
A rotated arc is the image of an axis-aligned arc under a rotation, which is
itself a rigid motion. Two rotated arcs are congruent exactly when their
local-frame descriptions are congruent. So once `arc_param_frame` reports
local angles, the existing test is correct for any pair of tilts, and no code
in `checks.py` changes.

Worked check of the swapped case: an arc on `(hr 3, vr 2, rotation 90)` is
the same point set as one on `(hr 2, vr 3, rotation 0)` with every parametric
angle shifted by pi/2. This is the `base = pi/2` branch that already exists.

What the stage-3 ticket needs is tests: the same arc at two different tilts
is congruent, an arc and its tilted mirror image are congruent, and two equal
spans at different positions on tilted ellipses are not.

## Curve measures and queries

Length, area and perimeter are rotation-invariant. `curve_measures.curve_length`
reads `hr, vr, start, end` from `arc_param_frame` for arcs and `hradius`/`vradius`
for full ellipses. Its only change is accepting `RotatedEllipse` next to
`spg.Ellipse` in the type dispatch. In `queries.py`, `query_length`
(which rejects a full ellipse), `query_radius`, `query_area` and
`query_perimeter` each branch on `isinstance(obj, spg.Ellipse)`. They need the
marker added to that tuple, and their arithmetic stays the same.
`query_perimeter`'s sector edges, `hypot(hr cos t, vr sin t)`, are
center-to-endpoint distances and are also invariant. `list_objects` reports
`type(obj).__name__`, so a tilted ellipse shows up as `RotatedEllipse`.
Whether to report it as `Ellipse` is a small open question. Nothing needs a
new query. A `rotation` key in `query_radius`'s result is optional and not
recommended for stage 1.

The radius checks (`EqualRadius`, `RadiusEquals` through `_conic_frame` and
`_circular_radius`) only need type acceptance. `equal_radius` compares ordered
`(hr, vr)` pairs. That means `(3, 2, rotation 0)` and `(2, 3, rotation 90)`,
which are the same curve, compare as unequal. The same is already true today
for two axis-aligned ellipses with their axes swapped. The design keeps that
behavior and lists it as an open question rather than changing a check's
meaning on the way through.

## Canvas and bounds

- `render_util.expand_bounds_for_geometry`: a full ellipse grows the bounds by
  `cx +/- hr` and `cy +/- vr`. Rotated half-widths are
  `sqrt(hr^2 cos^2 r + vr^2 sin^2 r)` and `sqrt(hr^2 sin^2 r + vr^2 cos^2 r)`.
- `render_util._arc_extent`: takes the endpoints plus the parametric extremes
  at 0, 90, 180 and 270 degrees, which are only the x/y extremes of an
  axis-aligned ellipse. Rotated, the x extremes are at
  `t = atan2(-vr sin r, hr cos r) + k pi`, and the y extremes at
  `t = atan2(vr cos r, hr sin r) + k pi`. Include those that fall inside the
  sweep and map them to world space.
- `render_util.synthesize_helpers`: `_ec_{id}` is only the center, so no
  change. The full-ellipse kinds are listed by statement class there, and that
  list does not change.
- `recipe/lower.py` `_Lowerer._auto_canvas`: its `ellipse_center_axes` branch
  adds `cx +/- a` and `cy +/- b`. This moves to the rotated half-widths in the
  authoring stage, when the recipe can first emit a rotation.

## Renderers

**SVG** (`to_svg.py`). The Draw and Fill branches for `spg.Ellipse` emit
`<ellipse rx=hr*sx ry=vr*sy>`. The elliptical arc and sector branches emit a
path `A hr*sx vr*sy 0 large 0 x y`. The fill-subpath builder (used for fills
with holes) emits two half-ellipse `A` commands. Under a non-uniform
`Canvas.aspect`, `scale.sx != scale.sy`, and the screen image of a rotated
ellipse is another ellipse with different axes and a different angle. So the
design adds one helper, `screen_ellipse(hr, vr, rotation, sx, sy) -> (rx, ry,
phi_deg)`. It computes the principal axes of `diag(sx, -sy) . R(r) . diag(hr,
vr)` in closed form (verified to a residual of 1e-15 in four cases, including
an anisotropic one). Full ellipses then emit
`<ellipse ... transform="rotate(phi cx cy)">`. Arcs, sectors and fill
subpaths put `phi` into the SVG arc's x-axis-rotation slot. Endpoints are
mapped from world space as today. The large-arc flag carries over unchanged:
a parametric sweep greater than pi means the center is on the arc's side of
the chord, and affine maps preserve that. The existing branches stay as they
are for rotation 0, which keeps byte identity.

SVG label nudging: `drawn_ellipses` holds axis-aligned screen tuples
`(cx, cy, rx, ry)`. These are consumed by `_ellipse_clearance` and
`_nearest_point_on_ellipse` (a Newton search in the centered frame), and by
`_label_clear_of_obstacles` and `_gravitate_to_ideal_axis`. Add `phi` to the
tuple and rotate the label center into the ellipse's screen frame before the
nearest-point search, then rotate the result back. This is stage 1b. Until
then, stage 1 does not register a tilted ellipse in `drawn_ellipses` at all,
because nudging labels against the axis-aligned outline would be wrong.
Labels are simply not nudged by it, and the feature is gated meanwhile.

**TikZ** (`to_tikz.py`). TikZ draws equal units only, and `canvas.aspect` is
rejected up front, so a plain rotation is enough. Verified with local
lualatex (TeX Live 2024):
`\draw[rotate around={deg:(cx,cy)}] (cx,cy) ellipse (a and b);` draws the
full ellipse. For an arc, keep today's
`arc[start angle=s, end angle=e, x radius, y radius]` with parametric angles,
but give the **unrotated** local start point `(cx + hr cos s, cy + vr sin s)`
and put `rotate around` on the path. The compiled endpoints matched the
world-space computation to within 1e-5. For fill fragments returned by the
fill-path builder, the inline option form `ellipse[x radius=..,y radius=..,
rotate=deg]` and a braced `{[rotate around=...] ...}` path scope gave the same
geometry. The Draw branch of `to_tikz` also has the fallback
`% Draw: unhandled type`, which stage 1 replaces for the marker.

**Tick marks and text along the curve** (`render_util`:
`tick_mark_elliptical_arcs`, `elliptical_arc_text_glyph_layout`,
`_ellipse_normal`, `_offset_curve_velocity`, `_min_curvature_radius`). They
walk the axis-aligned curve by arc length in the local frame, which is still
correct. Only the outputs need rotating: each point goes through `to_world`,
each normal is rotated by `rotation`, and each glyph's `rot` gains
`degrees(rotation)`. One subtle site: `up_sign` chooses upright text from
`_ellipse_normal(...)[1]`, the local y of the normal. It must use the
**world** normal's y, or text on the lower half of a tilted ellipse comes out
upside down. Callers in `to_svg.py` and `to_tikz.py` pass `cx, cy, hr, vr,
s_deg, e_deg` from `elliptical_arc_params`, and they need the rotation as
well. The ledger's deferred item about the duplicated "is this elliptical?"
dispatch in both backends is the natural place to thread it once.

**Label anchors** (`render_util.elliptical_arc_label_anchor`, reached through
`label_segment_arc_anchor`): evaluate the anchor point with `to_world`. The
returned `r` (center-to-point distance) is invariant. `centroid_of_obj` uses
only the center (or the center, start and end), so it does not change.

## Authoring surfaces

**Recipe** (`recipe/dsl.py` `EllipseOp`, `recipe/lower.py`
`Lowerer._lower_ellipse`): add `rotation: float = 0` (degrees CCW, which is
already the recipe convention on its polygon ops) and lower it to
`rotation_deg` for the center_axes and eccentricity forms. A nonzero rotation
on the bbox form is a validation error. The foci form needs no new field:
tilted foci work once the compiler accepts them in stage 4, which is also when
the gate goes, so the recipe never produces a tilted ellipse while the
feature is half built. The recipe has no elliptical
arc or sector op at all (`ArcOp`/`SectorOp` lower only to the circular kinds),
so there is nothing to extend for arcs. The catalog's `oval` doc entry
(`catalog.py`, currently "axis-aligned non-circular oval") and
`recipes/default/ellipse_axis_aligned.yaml` describe the old limit. Changing
that text changes the recipe prompt, so `tests/recipe_prompt_pre_solids.json`
must be regenerated in the same commit, with the reason stated (CLAUDE.md
rule).

**pydsl** (`pydsl/api.py` `ellipse`, `pydsl/handles.py` `Ellipse`): add
`rotation: float = 0.0`. It is in **radians**, because the python_full prompt
states "All angles (rotation, and walk()'s heading below) are radians" and
`rectangle(rotation=...)` already follows that rule. The function records
`rotation_deg = math.degrees(rotation)`. The `Ellipse` handle exposes
`rotation`. `_validate_on_ellipse` (the start/end-on-curve guard for
`arc()`/`sector()`) must test the local-frame equation. `_arc_or_sector` must
copy the parent's rotation into the elliptical arc def. The
`tangent_line(at=)` rejection for ellipses already exists and stays. The stub
is generated from signatures and docstrings, so the python_full prompt
fixture (`tests/python_full_prompt_pre_solids.json`) changes.

## Prompts and evals

- **Structured:** the prompt text does not list the ellipse kinds; the model
  sees them through the bound `DiagramIR` schema. That schema is static, so
  `rotation_deg` is visible from stage 1 whatever the feature setting, as the
  solids kinds are. The gate below is what stops it from being used by
  default. Stage 1 still makes every operation that a later stage owns a
  typed error on a tilted ellipse, so a run with the group on fails cleanly
  and retries instead of crashing.
- **What a model must be told** (stage 4, in all three surfaces): the unit and
  direction ("degrees counter-clockwise from +x to the hradius axis"); that
  `hradius` is the semi-axis along the rotation, not "horizontal"; that
  `point_on(ellipse, t)` measures t from the hradius axis; that a tilted arc
  or sector must repeat the parent's rotation (pydsl does this for you);
  that `ellipse_foci` accepts tilted foci; and that bbox ellipses cannot be
  tilted.
- **Feature gate:** see the next section.
- **Evals:** add a few scenarios with original prompts (not derived from the
  Geometry Evals Data dataset) to an existing scenarios file. Candidates: a
  tilted ellipse with labeled axes; a tangent from an external point to a
  tilted ellipse; a tilted ellipse's foci. The existing structural checks
  (labels, draw entities) and the queries are enough. A new eval property
  (for example `ellipse_rotation`) is not needed for a first measurement.

## Feature gate

Stages 1 to 3 build tilted support in pieces. Until stage 2 a tilted ellipse
cannot take a tangent or an intersection, and until stage 3 a tilted arc
cannot be expressed. The structured schema exposes `rotation_deg` from stage
1. So, like `solids`, tilted ellipses are gated at the generation surfaces and
are never gated in compile or render.

- **Group:** add `tilted_ellipses` to `features.FEATURE_GROUPS`. It is off by
  default and enabled the existing ways (`GeometryConfig.features`,
  `GEOMETRY_FEATURES`, evals `--features`).
- **What it rejects:** any authored definition of a kind that has the field
  (`ellipse_center_axes`, `ellipse_center_eccentricity`, and from stage 3 the
  two elliptical arc kinds) whose `rotation_deg` is not a literal 0. A string
  expression counts as tilted unless it is literally `"0"`, because
  `require_features` runs before compile and cannot evaluate an expression.
  Tilted foci are not gated: they stay a compile error until stage 4 (see
  Representation in the IR).
- **Where it is checked:** `features.require_features` is kind-based today. It
  walks `diagram.define` and asks the derived registry for each statement's
  group, and ellipses are not registry kinds. It needs a second, field-level
  rule, for example a small table that maps a kind to a predicate and a group,
  consulted in the same loop and raising the same `FeatureNotEnabledError`
  with a message that names the definition id and the field. The structured,
  recipe and python_full strategies already call `require_features` before
  `run_ir_pipeline` and feed its error back through their retry paths. The
  recipe has no rotation field until stage 4, so `recipe/dsl.py`
  `reject_disabled_ops` needs no entry, and the IR-level check stays the
  backstop. pydsl has no `rotation` parameter until stage 4, so
  `pydsl.GROUPED_NAMES` needs nothing. The parametrized regression test in
  `tests/test_feature_gating.py` gets a tilted-ellipse case.
- **Gated prompt text:** stages 1 to 3 add no prompt text by default. Any
  guidance written for the group on (a short structured fragment explaining
  `rotation_deg`, the hradius-axis meaning and the parametric angle, and a
  query-tool line if one is needed) goes through the existing
  `tagged_fragment` / `tagged_insertions` machinery. For example, the
  structured fragment is a `GROUPED_FRAGMENTS["tilted_ellipses"]` entry in
  `instructions_structured.py`. With the group off, every prompt is
  byte-identical, and the `tests/*_pre_solids.json` fixture tests pass
  unchanged.
- **Evals while gated:** tilted-ellipse scenarios declare
  `requires_features: [tilted_ellipses]`, so they are skipped unless the group
  is enabled.
- **Removal (stage 4):** after an eval run with the group on, the stage-4
  ticket removes the group and its rejection rule, turns the tagged guidance
  into default prompt text, and regenerates the pinned fixtures in the same
  commit, saying why (CLAUDE.md rule).

## Blast-radius inventory

S = a few lines plus tests. M = a function or two of real logic. L = new
algorithm.

| # | Area | Module: function(s) assuming axis alignment | What changes | Size | Stage |
|---|------|---------------------------------------------|--------------|------|-------|
| 1 | IR schema | `ir.py`: `EllipseCenterAxes`, `EllipseCenterEccentricity`, `EllipticalArcCenterStartEnd`, `EllipticalSectorCenterStartEnd` (docstrings say "Axis-aligned"); `refs.py`: `_EXPR_FIELDS`, `_NON_REF_FIELDS` | `rotation_deg` field, docstrings, ref extraction | S | 1 (arcs 3) |
| 2 | Compile, full ellipse | `to_sympy._compile_one`: `EllipseCenterAxes`, `EllipseFoci` (raises on tilted foci), `EllipseCenterEccentricity` cases | `RotatedEllipse` marker; exact-0 path kept; tilted-foci lift deferred to stage 4 (with the gate removal) | M | 1 |
| 3 | Compile, arcs | `to_sympy._compile_one` elliptical arc/sector cases; `EllipticalArc`/`EllipticalSector` markers; `_reflex_for_bulge_toward` | `rotation` slot; local parametric angles in bulge test | S | 3 |
| 4 | Parametric placement and inverse | `to_sympy._eval_param`, `_invert_param` (inverse used by pydsl `Builder._pin_point_on`), `_sample_param`, `arc_param_frame`, `_underlying_conic` | local frame in, `to_world` out; marker branch in sampler | S | 1 (arcs 3) |
| 5 | Point-on and pick | `to_sympy.point_on_arc`, `_on_object`, `_apply_pick` (`PickOnObject`); `checks._contains` | local implicit equation | S | 1 (arcs 3) |
| 6 | Tangent lines | `to_sympy` `LineTangent` case (`spg.Ellipse.tangent_lines`), `_tangent_touch_point`; `checks` `Tangent` case via `_conic_frame` | local-frame point/line, rotate back | M | 2 |
| 7 | Intersections | `to_sympy` `PointIntersection` case, `_underlying_conic`, `_tangent_candidates` (unit-circle frame from `ha, va`), `_count_ellipse_crossings` | local transform for line/circle; new numeric quartic for ellipse x ellipse | L | 2 |
| 8 | Sweep filter | `to_sympy._point_in_arc_sweep` (via `arc_param_frame`) | none beyond row 4 | S | 3 |
| 9 | Radius checks | `checks._conic_frame`, `_circular_radius`, `EqualRadius`, `RadiusEquals` | accept marker; values rotation-invariant | S | 1 |
| 10 | Congruent arcs | `checks._ellipse_arcs_congruent`, `_check_congruent_arcs` | no logic change (rigid-motion argument); tests only | S | 3 |
| 11 | Curve measures | `curve_measures.curve_length`, `_radii` | accept marker in dispatch | S | 1 |
| 12 | Queries | `queries.query_length`, `query_radius`, `query_area`, `query_perimeter`, `_radii`, `list_objects` | accept marker; arithmetic unchanged | S | 1 |
| 13 | Bounds and canvas | `render_util.expand_bounds_for_geometry`, `_arc_extent`; `recipe/lower.py` `_auto_canvas` | rotated half-widths; rotated extreme parameters | S | 1 (arcs 3, recipe 4) |
| 14 | SVG draw and fill | `to_svg` Draw/Fill `spg.Ellipse`, `EllipticalArc`, `EllipticalSector` branches; fill-subpath builder | equal units: `transform`/x-axis-rotation (S); non-unit aspect: `screen_ellipse` helper (M) | S + M | 1 equal units, 1b aspect (arcs 3) |
| 15 | SVG label nudging | `to_svg`: `drawn_ellipses`, `_ellipse_clearance`, `_nearest_point_on_ellipse`, `_newton_refine_ellipse_param`, `_label_clear_of_obstacles`, `_gravitate_to_ideal_axis` | `phi` in tuple; rotate into screen frame | M | 1b |
| 16 | TikZ draw and fill | `to_tikz` Draw `spg.Ellipse` / elliptical arc / sector branches; fill-path builder (`... ellipse[x radius, y radius]`) | `rotate around` / inline `rotate`; unrotated local start point for arcs | S | 1 (arcs 3) |
| 17 | Ticks and text along curve | `render_util.tick_mark_elliptical_arcs`, `elliptical_arc_text_glyph_layout` (`up_sign` from local normal), `_ellipse_normal`; callers in `to_svg`/`to_tikz` | rotate outputs; world-normal upright test | M | 3 |
| 18 | Label anchors | `render_util.elliptical_arc_label_anchor`, `elliptical_arc_params`, `label_segment_arc_anchor` | `to_world` on anchor; local angles in params | S | 3 |
| 19 | Recipe | `recipe/dsl.py` `EllipseOp`; `recipe/lower.py` `_lower_ellipse`; `catalog.py` oval docs; `recipes/default/ellipse_axis_aligned.yaml` | `rotation` (deg) field; docs; prompt fixture regenerated | S | 4 |
| 20 | pydsl | `api.ellipse`, `handles.Ellipse`, `api._validate_on_ellipse`, `api._arc_or_sector`; generated stub | `rotation` (rad); copy to arcs; local-frame validation; prompt fixture regenerated | M | 4 (arc copy 3) |
| 21 | Prompts | `instructions_python_full.py` ellipse/arc lines; `catalog.py`; structured schema field description; `tests/*_pre_solids.json` | wording; fixture regeneration | S | 4 |
| 22 | Evals | `evals/scenarios*.yaml` | 2-3 original tilted-ellipse scenarios | S | 4 |
| 23 | Docs | `docs/geometry-dsl-spec.md` ellipse and elliptical arc sections; CLAUDE.md IR bullets | describe `rotation_deg` and semantics | S | each stage |
| 24 | Feature gate | `features.py`: `FEATURE_GROUPS`, `require_features` (kind-based only); `instructions_structured.GROUPED_FRAGMENTS`; `tests/test_feature_gating.py` | `tilted_ellipses` group; field-level rejection rule; gated fragment; removed in stage 4 | S | 1 (removal 4) |

Not affected (checked): `checks._build_linear_pairs` (sector radii are ordinary
segments), `render_util.centroid_of_obj` and `synthesize_helpers` (center
only), `_check_spatial_constraint`'s `ArcBetweenConstraint` (comment only),
`edit_diagnostics.py` (positions through `centroid_of_obj`), `derived.py` (no
ellipse entries), `util/svg_checks.py` (counts `<ellipse>` tags only),
`evals/run.py` (no ellipse geometry, only query docs).

## Staged rollout

1. **Stage 1, tilted full ellipse end to end behind the gate (draft ticket
   06).** Rows 1 (full kinds), 2 (without the foci lift), 4, 5, 9, 11, 12, 13
   (renderer bounds), 14 (equal units), 16 for full ellipses, and 24 (the
   gate). It also adds typed errors for everything later stages own:
   `line_tangent`, intersection and the `tangent` check on a rotated ellipse
   fail with a message naming the id and saying tilted ellipses do not
   support it yet. The SVG renderer raises a typed error for a tilted ellipse
   on a canvas with a non-unit `aspect`; TikZ already rejects `aspect`. Label
   nudging does not yet treat a tilted ellipse as an obstacle. From here on,
   only a run with `tilted_ellipses` enabled can generate the field.
1b. **Stage 1b, SVG under a non-unit aspect, and label nudging (draft ticket
   08, blocked by 06).** Rows 14 (`screen_ellipse`) and 15. This lifts the
   stage-1 aspect error and registers tilted ellipses as nudging obstacles.
   It is independent of stage 2.
2. **Stage 2, tangents and intersections on a tilted full ellipse (draft
   ticket 07, blocked by 06).** Rows 6 and 7. This lifts the stage-1 typed
   errors.
3. **Stage 3, tilted elliptical arcs and sectors.** Rows 1 (arc kinds), 3, 4,
   5, 8, 10, 13 (`_arc_extent`), 14, 16, 17 and 18 for arcs, plus pydsl's
   rotation copy in `_arc_or_sector`. The gate's rejection rule extends to the
   two arc kinds. Not drafted yet: its shape depends on how stages 1 and 2
   land the frame helper.
4. **Stage 4, authoring, prompts and removing the gate.** Rows 19 to 22: recipe
   and pydsl surfaces, the tilted-foci lift (row 2), prompt text, eval
   scenarios, an eval run with the group on, then removal of the gate (row
   24) and fixture regeneration in the same commit.

Stage 4 could move ahead of stage 3 for full ellipses only, if the human
wants recipe and pydsl authors to have tilted full ellipses early. In that
case, the gate would stay on until stage 3 lands, and the tilted-foci lift
stays with the gate removal (it cannot be gated, since whether foci are
tilted is known only after compile), so it would wait for stage 3 too.

## Test plan for stage 1

- IR: an `ellipse_center_axes` without `rotation_deg` validates and dumps with
  `rotation_deg: 0`. A string expression `rotation_deg: "angle(X, O, F)"`
  orders after its referenced points (refs test).
- Compile: `rotation_deg: 0` (and 360) produces an `spg.Ellipse` equal to
  today's. `rotation_deg: 30` produces a `RotatedEllipse` whose float rotation
  is pi/6. `ellipse_foci` with tilted foci still raises today's error (the
  lift is stage 4).
- Gate: with `tilted_ellipses` off, `require_features` rejects a diagram
  whose ellipse has `rotation_deg: 30` or `"pi"`, naming the definition id
  and the group, and accepts `rotation_deg: 0` and an omitted field. With the
  group on, it accepts them. Compiling and rendering the same IR succeed with
  the group off. All `*_pre_solids.json` prompt fixtures pass unchanged.
- point_on: on `hr 3, vr 1, rotation 30`, `t = 0` lands at the center plus
  3·(cos 30°, sin 30°), and `t = pi/2` lands at the center plus 1·(-sin 30°,
  cos 30°). `_invert_param` round-trips a sampled point (pinning path).
  `PointOnRandom` samples land on the curve.
- Contains and pick: a point built by `point_on` passes `contains`. The
  axis-aligned point with the same coordinates offset fails. `pick_on_object`
  picks the on-curve candidate.
- Radius and measures: `radius_equals` and `equal_radius` behave as for the
  unrotated ellipse. `query_area`, `query_perimeter` and `query_radius` return
  the same values as the unrotated twin. `curve_length` equals the unrotated
  perimeter.
- Bounds: the computed canvas contains the rotated extremes (hand-derived
  half-widths for 3x1 at 30 degrees) and is narrower than the unrotated
  bounding box in x.
- **Rendered through both renderers:** the same tilted-ellipse IR (drawn and
  filled, with a labeled center and one labeled `point_on` point) renders
  - in SVG: an `<ellipse>` with `transform="rotate(-30 cx cy)"` (the sign is
    flipped for y-down) and `rx`/`ry` equal to `hr`/`vr` times the scale.
    With a `canvas.aspect` set to anything other than 1, rendering fails
    with a typed error naming the ellipse (stage 1b lifts this).
  - in TikZ: a `\draw[rotate around={30:(cx,cy)}] ... ellipse (3 and 1);` and
    the matching fill. The TikZ code compiles with the renderer container, or
    with local lualatex when the container is down.
- Typed errors: `line_tangent`, `point_intersection` and the `tangent` check
  on a rotated ellipse each fail with a typed error naming the id, not an
  `AttributeError` and not a silent skip.
- Byte identity: with `PYTHONHASHSEED=0`, every existing scenario's SVG and
  TikZ output is unchanged (the ticket-04 72-scenario capture can be
  reused).

## Measured facts

All with `.venv/bin/python` (SymPy 1.14.0) on 2026-10-25. Each case was
timed separately with a 30 s alarm.

| Experiment | Result |
|---|---|
| `spg.Ellipse(O, 3, 2).rotate(a)` for a = pi/2, pi | returns an `Ellipse` (radii swapped for pi/2) |
| same for pi/6, Rational(1, 3), 0.5 | `NotImplementedError: Only rotations of pi/2 are currently supported for Ellipse.` |
| `spg.Ellipse(O, 2, 2)` | returns a `Circle` |
| local-frame line x ellipse, exact pi/6 / float 0.5236 / exact 37·pi/180 | 0.11 s / 0.04 s / timeout > 30 s |
| local-frame `tangent_lines`, exact pi/6 / float / exact 37·pi/180 | 0.29 s / 0.04 s / timeout > 30 s |
| local-frame circle x ellipse, circle center rotated exactly by pi/6 / by float 0.5 | timeout > 30 s / 1.45 s |
| `sp.solve` of implicit tilted (pi/6) ellipse x circle | 0.1 s, 4 solutions |
| `sp.solve` of implicit tilted (float 0.5) ellipse x axis-aligned ellipse | 3.5 s, 2 solutions |
| half-angle quartic + `mpmath.polyroots`, same pair | 0.02 s, 2 points |
| TikZ `rotate around` + unrotated local start + parametric `arc[...]`, lualatex 2024 | endpoints match the world computation to 1e-5 |
| TikZ inline `ellipse[..., rotate=30]` vs braced `{[rotate around=...] ...}` | identical geometry |
| `screen_ellipse` closed form, 4 cases incl. sx=40, sy=10 | implicit residual <= 1.3e-15 |

Conclusion: carry the rotation as a float. Exact symbolic angles are fast
only when they simplify to surds (pi/6), and they are unusable otherwise.

## Open questions for the human

1. Field name and unit: `rotation_deg` in degrees in the IR (recommended),
   versus `rotation` in radians to match `point_rotate`? pydsl stays in
   radians either way.
2. Should `equal_radius` treat swapped axes (`3x2` versus `2x3`, the same curve
   when rotated 90 degrees) as equal? Today it does not, even for axis-aligned
   ellipses.
3. Gate name and scope: `tilted_ellipses` covering stages 1 to 3
   (recommended). Should stage 4 remove it entirely, or leave the group defined but enabled
   by default for one release before deleting it?
4. `list_objects` / query output: report a tilted ellipse as `Ellipse`, or as
   `RotatedEllipse`?
5. Order of stages 3 and 4: arcs first (recommended), or authoring for full
   ellipses first?

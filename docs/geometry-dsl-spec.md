# Geometry DSL: Contracts Reference

This file records the behavior contracts that are not obvious from the code:
the solids, curve semantics, rendering rules, pipeline warnings and checks.
It is not a reference for the recipe operations, selectors, expression
language or annotations. For those:

- the schema is the pydantic models in `geometry_diagrams/recipe/dsl.py` (recipe
  ops) and `geometry_diagrams/ir/ir.py` (IR definitions, render ops, checks);
- the text shown to the model is `DSL_DOCS` in `geometry_diagrams/recipe/catalog.py`
  (`dsl_docs_for(features)` adds the gated solids guidance);
- how a recipe is written is covered by the `geometry-recipe-maker` skill and the
  YAML files under `geometry_diagrams/recipe/recipes/`.

The pipeline is described in [CLAUDE.md](../CLAUDE.md#architecture) and the
strategies in [strategies.md](strategies.md).

---

## Curves

### Tilted ellipses (`rotation_deg`)

The IR ellipse kinds `ellipse_center_axes` and `ellipse_center_eccentricity`
take an optional `rotation_deg` (number or expression string, default 0):
degrees counter-clockwise from +x to the `hradius` axis, about the center.
`hradius` is the semi-axis along that direction and `vradius` the one
perpendicular to it; for the eccentricity form the figure given by
`orientation` is turned as a whole. `point_on` with a parameter t measures the
parametric angle in the ellipse's own frame, from the `hradius` axis: the
point is `center + R(rotation) (hradius cos t, vradius sin t)`, so t = 0 is
the end of the tilted `hradius` axis. A rotation that is exactly 0 after
`% 360` compiles to the usual axis-aligned ellipse (byte-identical output);
any other value compiles to a tilted ellipse carrying a float rotation.
`ellipse_bbox`, `ellipse_foci` (tilted foci are still an error) and the
elliptical arc/sector kinds stay axis-aligned.

Tilted ellipses belong to the `tilted_ellipses` feature group (off by
default): with it off, a generated diagram whose ellipse has a `rotation_deg`
that is not a literal 0 (an expression string counts as tilted unless it is
`"0"`) is rejected at the generation surfaces, naming the definition and the
group (conservatively, a literal 360 is rejected too, although compile snaps an evaluated 360 to 0). Stored diagrams always compile and render. Supported on a tilted
ellipse: draw and fill (also with holes) in both renderers, canvas bounds,
`point_on` (param and random), `pick_on_object`, `contains`, the radius
checks and the length/radius/area/perimeter queries (all as for the untilted
ellipse). Also supported, through one numeric conic kernel (`conic_kernel.py`,
numpy only): `point_intersection` of a tilted ellipse with a line, segment,
ray, circle, axis-aligned ellipse or another tilted ellipse (an arc or sector
of the other operand is filtered by its sweep after near-tangent pairs snap to
their touch point; two copies of one curve are an error naming both ids),
`line_tangent` from an external point (two tangent lines, `pick` chooses by
the touch point; a point inside is "no tangent lines"; a point on the curve
has exactly one tangent) and the `tangent` check. The kernel also solves
ellipse x ellipse and circle x ellipse pairs carrying any float (SymPy rationalizes float point coordinates, so in practice a float radius or axis), which SymPy
cannot, so those no longer fail; untilted pairs with all-exact coordinates and radii keep the
exact SymPy result. SVG also draws and fills a tilted ellipse on a canvas with a
non-unit `aspect`: its screen image is another ellipse, whose axes and angle
`render_util.screen_ellipse` computes in closed form (TikZ rejects any `aspect`,
as for every diagram), and label nudging treats the tilted ellipse as an
obstacle at its true screen angle.

### Circular arcs and sectors (`radius`)

IR kinds `arc_center_start_end` and `sector_center_start_end` take `center`,
`start`, `end`, optional `reflex` / `bulge_toward` and an optional `radius`
(a number or an expression string such as `radius(K)` or `length(P, Q)`, like
every other radius field; it is a dependency, so it may name definitions listed
later). Without `radius` the circle is the one about `center` through `start`
and `end` is only a direction, as always. With `radius` the circle is the one
about `center` with that radius and **both** `start` and `end` are only
directions from `center`: the compiled arc/sector runs between the points of
that circle in those directions, wherever the given points lie. A `start` or
`end` already on the circle (within 1e-9) is used unchanged, so a redundant
`radius` changes nothing; a non-positive radius, or a `start`/`end` at the
centre (no direction), is a compile error naming the definition. `reflex` and
`bulge_toward` act on the corrected circle. The compiled marker carries the
explicit radius and on-circle endpoints, so renderers, `point_on`, `contains`,
intersections, tangents, queries and checks all see that one circle.

The elliptical kinds snap an off-curve `start`/`end` onto the ellipse the same
way, along the parametric angle (`atan2((y - cy) / vradius, (x - cx) / hradius)`),
and leave an on-curve one unchanged; a `start`/`end` at the centre (no direction) is a compile error naming the definition.

## Solid Operations

Solids belong to the `solids` feature group (off by default for generation;
see `geometry_diagrams/features.py`). A stored diagram containing a solid
always compiles and renders, whatever the feature setting.

#### `rectangular_prism`
A right rectangular prism (box) drawn as a parallel projection. The
IR-level definition is `ir.RectangularPrism`; the recipe DSL op of the same
fields is named `prism` (`recipe.dsl.PrismOp`).

| Field          | Type            | Description |
|----------------|-----------------|-------------|
| `id`           | string          | Name for the prism |
| `origin`       | string          | Point id of the front-bottom-left corner (may be a derived point) |
| `length`       | number or expr  | Along the front bottom edge (positive) |
| `width`        | number or expr  | Along the right bottom edge, i.e. the depth (positive) |
| `height`       | number or expr  | Vertical (positive) |
| `unit_cubes`   | bool            | Unit-cube prism (default false); the three dimensions must then be literal positive integers, each at most 100 |
| `vertex_names` | list of 8 strings | Optional corner names, in corner-bit order `000, 001, 010, 011, 100, 101, 110, 111` |
| `view`         | string          | `"oblique"` (default) or `"isometric"` |
| `depth_angle`  | number          | Oblique only: angle of the receding depth edge in degrees, in (0, 90); default 45 |
| `depth_scale`  | number          | Oblique only: scales the depth axis (the prism's width): the drawn length of the receding edge per unit of width, positive; default 1/2 |
| `side`         | string          | `"right"` (default) or `"left"` (mirrored); applies to both views |
| `length_label`, `width_label`, `height_label` | string | Optional dimension labels, text used verbatim (see [Label fields](#prism-label-fields)); omitted for no label, an empty string is rejected by the schema (`min_length=1`) |
| `base_area_label` | string       | Optional free text centered on the bottom face (see [Label fields](#prism-label-fields)); same rules |

Giving `depth_angle` or `depth_scale` with `view: "isometric"` is a compile
error. Oblique maps length to (1, 0), height to (0, 1) and width to
`depth_scale * (cos a, sin a)` (side left negates the x part). Isometric
maps length to (cos 30, -sin 30), height to (0, 1), width to (cos 30, sin 30);
side left maps length to (cos 30, sin 30) and width to (-cos 30, sin 30).

The vocabulary is the same in every view. With `side: "right"` the visible
faces are front, right and top and the hidden corner (the one farthest from
the viewer) is back-bottom-left, bits `001`; with `side: "left"` the visible
faces are front, left and top and the hidden corner is back-bottom-right,
bits `101`. Both are derived from the projection's viewer direction.

**Public derived ids.** A corner's bits are `(length, height, width)`, each
0 or 1 (`000` is the origin, `111` the opposite corner).

| Entity  | Id | Notes |
|---------|----|-------|
| Corners (8 points) | `{id}_v{abc}`, e.g. `P_v000`, `P_v111` | Replaced by `vertex_names` when given |
| Edges (12 segments) | `{id}_e_{abc}_{abc}`, the two endpoint bit strings with the smaller first, e.g. `P_e_000_100` (front bottom edge, the length), `P_e_000_001` (left bottom edge, the width), `P_e_000_010` (front left edge, the height) | Always named by bits, even with `vertex_names`; the endpoints are then the renamed corners |
| Faces (6 polygons) | `{id}_front`, `{id}_back`, `{id}_left`, `{id}_right`, `{id}_top`, `{id}_bottom` | The bottom face is also called the base; there is no separate base id |

Edges and faces are ordinary segment and polygon definitions: fill a face
(`fill` on `P_bottom`), label an edge (`label_segment` on `P_e_000_100`), or
draw individual faces and edges by id. They are derived, never part of the
authored IR, and do not count in authored-IR metrics such as
`polygon_count`. An authored definition whose id equals any corner, edge or
face id of a prism (or any other derived id) is a compile error, never a
silent shadow.

**Drawing.** A draw whose `obj` is the prism id draws:

- the three visible face outlines, with the draw's style; and
- unless `unit_cubes`, the three edges meeting at the hidden corner, dashed,
  with the draw's style merged with `dashed` (a `dotted` pattern in the style
  is replaced by dashed).

For a unit-cube prism the three visible face outlines are drawn (no hidden
edges) plus thin gray gridlines on those faces, built from derived points and
segments with hidden `__{id}_gp{n}` / `__{id}_g{n}` ids. Unit-cube dimensions
are limited to 100 per dimension (a larger value is a compile error telling
the author to use wireframe mode, `unit_cubes=false`). The gridlines come only
from a draw of the prism id, so a unit-cube prism must be drawn by its id (fills
on its face ids still shade it); a unit-cube prism whose id is never drawn
renders with a pipeline warning saying its gridlines are missing. For a solid
look on a non-unit-cube prism (no hidden edges), draw and fill the visible face
ids instead of the prism id.

**Shading and labels.** Shade a face with `fill` on its face id; colors go
through the shared color forms (see [Color forms](#color-forms)), so an opaque tint such as `rgb(230,159,0)` paints the same
color in SVG and TikZ. Label an edge with `label_segment` on its edge id (or
on any segment joining two corners); label a face with `label_free_text` and
`centroid_of` the face id (e.g. "60 square units" on `P_bottom`); and
`label_free_text` with `centroid_of` the prism id itself centers the text on
the prism's projected center (the middle of the drawn silhouette).

A `label_segment` on a segment joining two corners of one prism (a dimension
label) is placed on the side of the segment away from the prism's projected
center, with the whole label clear of the segment's line. On a slanted
edge in the SVG renderer (the away normal's horizontal component strictly
between 0.3 and 0.95 in magnitude: the depth edge, and the length edge in
isometric views) the label box also slides along the edge so its nearest
corner touches the edge's line at the edge midpoint, with the same
perpendicular clearance (near-horizontal and near-vertical edges are placed
without sliding; TikZ does not slide, since that needs the text size). On an outline
(silhouette) edge it sits outside the figure; which edges are outline edges
depends on `side` (for `side: "right"`, e.g. left of the front-left vertical
edge, below the front bottom edge, right of the right-hand edges; `side:
"left"` mirrors the right-hand cases to the left). On a hidden or interior edge
or a face diagonal the label still goes on the side away from the box center,
which may put it on top of a face. When the center lies on the segment's line (a space diagonal) the ordinary
segment-label placement applies. In TikZ the same side is given as a node
placement (`left`, `below right`, ...). Labels on other segments are
unaffected. In TikZ, words in a `label_segment` render in math mode
("6units"); use `label_free_text` for worded labels there.

<a id="prism-label-fields"></a>
**Label fields.** `length_label`, `width_label`, `height_label` and
`base_area_label` let the prism own its standard labels, so an author never
reasons about edge ids or coordinates. Each is optional text used **verbatim**
(no unit is added: write `"6 ft"` or `"11"` as it should read) and, when set,
non-empty. A dimension field labels the one **silhouette** edge of that
dimension, derived from the projection's hidden corner `h` (bits `h0 h1 h2`,
`h0` is 0 for `side: "right"` and 1 for `side: "left"`), so the label lands
outside the drawn figure in every view and side:

| Field | Edge (corner bits, length-height-width) | `side: "right"` | `side: "left"` |
|-------|-----------------------------------------|-----------------|----------------|
| `length_label` | `(0,0,0)-(1,0,0)`, the front bottom edge | `P_e_000_100` | `P_e_000_100` |
| `height_label` | `(h0,0,0)-(h0,1,0)`, the vertical edge on the near side of the visible lateral face | `P_e_000_010` | `P_e_100_110` |
| `width_label` | `(1-h0,0,0)-(1-h0,0,1)`, the bottom depth edge not touching the hidden corner | `P_e_100_101` | `P_e_000_001` |

(`P_e_000_001`, the width edge many authors reach for first, is **hidden** for
`side: "right"`; every edge touching the hidden corner is hidden.) Each dimension label is an ordinary `label_segment` op on
the prism's own edge id, with the field's text, so it is placed by the
dimension-label rule above (away from the prism's center, outside the
silhouette). `base_area_label` is a `label_free_text` centered on the bottom
face's centroid; for a solid prism the base is hidden, so the text then reads
over the front face: use it with a wireframe or shaded-base prism.

The labels are lowered by the registry hook `lower_labels` (see
`ir/derived.py`): **once per drawn prism**, appended after the other render
operations, however the prism is drawn. A prism is drawn when a `draw` or
`fill` operation names its id or an id it owns (a face or an edge, for a
shaded prism drawn through its face ids only; a `draw` of one edge alone
emits all four labels); drawing it twice, or through
several faces, still emits each label once. An undrawn prism emits no labels
(a `fill` of the prism id itself is an error, see below, so it never triggers
them). Setting a field and also labelling the same edge by hand gives two
labels; there is no de-duplication.

The label-dimension warning (see [Pipeline warnings](#pipeline-warnings))
also checks the three dimension fields: the first number in the text against
the true dimension. The message reads `length_label '<text>' on prism 'P' does
not match its true length N (its length): ...` (field name and dimension vary;
the manual-label form reads `Label ... does not match its true length N: ...`),
so the stable substring is `does not match its true length`. It takes the first number
only, so fraction text such as `"7/2"` or `"3 1/2 in"` falsely warns; and it
fires whether or not the prism is drawn. `base_area_label` is not checked.

*Known limits.* In TikZ a dimension label (a `label_segment`) renders in math
mode (italic, spaces collapse: `"6 units"` reads `6units`), while
`base_area_label` is plain `\node` text, where `^` (e.g. `"cm^2"`) is a LaTeX
error; the SVG renderer has neither problem. The base-area text can cross edges or
another label on extreme shapes (e.g. a 20x1x1 box at `depth_angle` 80, or a
1x1x20 box at `depth_scale` 1.5) or sit partly outside a narrow base.

Render operations that cannot work on the prism id are compile errors naming
the alternative: `fill` (or a `fill` hole) on the prism id ("fill a face id
such as `P_bottom`"), a point slot (`draw_points`, `label_point`, any angle
point) ("use a corner id such as `P_v000`"), `mark_segments` /
`label_segment` ("use an edge id such as `P_e_000_100`"), and `mark_arcs` /
`label_along_arc`. `draw` and `label_free_text` with `centroid_of` the prism
id are valid. A prism on a canvas with unequal axis scales (`canvas.aspect`)
renders with a warning: the projection is skewed.

**Measures, queries and checks.** The `prism` query returns the true
length, width and height, the volume, base area, surface area and corner
ids. Any segment definition whose two endpoints are corners of the same
prism (the prism's own edges, or a segment authored or made by a builder
under any id) is recorded at compile by its endpoint ids, never by
coordinates; the `length` query on it returns the drawn (projected 2D)
`length` plus `true_length`, the 3D distance between the two corners (an
edge gives one dimension, a face diagonal or the space diagonal the
Euclidean combination).

| Check | Fields | Meaning |
|-------|--------|---------|
| `volume_equals` | `prism`, `expected` | The prism's true volume equals `expected` |
| `true_length_equals` | `seg`, `expected` | The true 3D length of a segment joining two corners of one prism equals `expected` (any other segment fails, naming `distance_equals`) |

Both are near-exact: `|actual - expected| <= tol * max(|actual|, |expected|)` (no absolute
floor) with a
default `tol` of 1e-9 (an off-by-one volume fails); an explicit `tol` on the
check overrides it. Every other check keeps the default tolerance (5e-3).
`distance_equals`, `equal_length` and `ratio_equal` on a segment joining two
prism corners keep their 2D meaning (they measure the drawing) and add a
pipeline warning saying a projection was measured and naming
`true_length_equals`.

#### `block_stack`
An irregular stack of unit cubes drawn as a parallel projection: the
building-plan "how many cubes?" figure. The IR-level definition is
`ir.BlockStack` (compiled by `geometry_diagrams/ir/stack.py`; the recipe DSL op
of the same fields is named `stack`, `recipe.dsl.StackOp`). Like the prism
it belongs to the `solids` group.

| Field          | Type            | Description |
|----------------|-----------------|-------------|
| `id`           | string          | Name for the stack |
| `origin`       | string          | Point id of the front-bottom-left corner of the bounding box (may be a derived point) |
| `heights`      | list of rows of integers | `heights[z][x]` is the number of cubes in the column at column `x` (left to right) of row `z` (rows run front to back) |
| `cubes`        | list of `[x, y, z]` | The unit cubes of a shape a height map cannot express; each triple is the unit cube from (x, y, z) to (x+1, y+1, z+1) |
| `view`         | string          | `"oblique"` (default) or `"isometric"` |
| `depth_angle`  | number          | Oblique only: degrees in (0, 90); default 45 |
| `depth_scale`  | number          | Oblique only: scales the depth axis (the stack's z, rows front to back): the drawn length of the receding edge per unit of depth, positive; default 1/2 |
| `side`         | string          | `"right"` (default) or `"left"`; as for the prism |
| `front_color`  | string          | Fill of the front faces (default `#c3d6ef`) |
| `side_color`   | string          | Fill of the visible lateral faces, right or left per `side` (default `#97b5dc`) |
| `top_color`    | string          | Fill of the top faces (default `#e6eefa`) |
| `count_label`  | string          | Optional label for the whole stack, e.g. its cube total; text used verbatim (no unit added), non-empty (`min_length=1`); see below |

Give exactly one of `heights` and `cubes`. Every entry is a literal
non-negative integer (an integral float such as `2.0` is accepted); cubes are
one drawing unit on a side, so the stack is placed by its `origin` only.
The view fields and the three face colors take the same values and forms as
elsewhere (see [Color forms](#color-forms)); the projection comes from the
same code as the prism's, so every view and `side` behaves identically.

**Axis convention.** The axes are the prism's: x runs along the front edge
left to right (the prism's length), y is the height (up; the layer number, 0
is the bottom layer) and z is the depth (front to back, 0 is the front row;
the prism's width). In a `cubes` triple `[x, y, z]`, y is HEIGHT and z is
DEPTH; swapping them draws the stack lying flat instead of standing up. The
cube `(x, y, z)` occupies the unit cube from (x, y, z) to (x+1, y+1, z+1).
A `heights` entry `heights[z][x] = h` is the cubes `(x, 0, z) ... (x, h-1, z)`.

**Caps.** At most 400 cubes and at most 20 cells along any axis (for
`heights`: at most 20 rows, 20 columns and a tallest column of at most 20;
for `cubes`: each of x, y and z spans at most 20, measured as the largest
coordinate plus 1). Heights are validated against the caps before any cube is
built.

**Validation errors.** Each is an `IRCompileError` carrying the stack's id:

| Condition | Message names |
|-----------|---------------|
| both or neither of `heights` and `cubes` | "exactly one of heights ... and cubes ...", and which was given |
| `heights` has no rows or an empty row | "heights is empty" |
| `heights` rows of different lengths | "ragged rows", with the row lengths |
| an entry that is not a number, is not integral, or is negative | the entry, e.g. `heights[1][0]` or `cubes[2][y]`, and "integer" / "non-negative" |
| every height is 0 | "block_stack is empty" |
| more than 400 cubes | "at most 400 cubes", with the count |
| more than 20 cells along an axis | "at most 20 cells along any axis", with the size and which axis |
| `cubes` is empty | "cubes is empty" |
| a cube that is not exactly three integers | `cubes[i]` "must be an [x, y, z] triple" |
| a duplicate cube | "duplicate cube", with the index |
| `depth_angle` / `depth_scale` with `view: "isometric"`, or a value out of range | the prism's projection message, prefixed `block_stack:` |
| `origin` is not a point | "origin ... must be a point" |
| an authored id equal to a derived id of the stack (a column top id or a lattice id) | "collides ...", never a silent shadow |

A non-string entry (e.g. `"a"`) is rejected earlier, by the schema.

**Derived and public ids.** Every corner of every cube is a lattice point
with a hidden id `__{id}_l{x}_{y}_{z}` (plain points in the symbol table,
absent from object listings; they are what the faces are built on). The only
public derived ids are the column top faces:

| Entity  | Id | Notes |
|---------|----|-------|
| Column top face (polygon) | `{id}_top_{x}_{z}`, e.g. `S_top_1_0` | One per occupied column, at the plane of the column's topmost cube's top (for a cube set, the highest cube in that column, even one floating over a gap). A column with no cube has no id. |

A top face is an ordinary polygon definition: label it (`label_free_text`
with `centroid_of` its id), fill it, or draw it. It is derived, never part of
the authored IR, and does not count in authored-IR metrics. It is built
without SymPy's polygon validation (a lattice unit square under a
non-degenerate projection cannot be degenerate), which is what keeps a 20 x 20
stack at a fraction of a second to compile; the object is an ordinary SymPy
`Polygon`. The stack id itself is the stack and its center, not a polygon.

**Drawing.** A draw whose `obj` is the stack id draws every visible cube
face, farthest cubes first (painter's algorithm), each face an
[`OrderedPolygon`](#ordered-polygons): an opaque fill (the plane's color) and
an outline. Cubes are sorted by the dot product of their center with the
projection's viewer direction (ties by coordinates), which is correct for any
cube set under a parallel projection; each cube contributes its faces on the
three visible planes (front, right and top for `side: "right"`; front, left
and top for `side: "left"`) except a face covered by a neighbouring cube,
which is never emitted, so a 3 x 3 x 3 box paints 27 faces rather than 81.
The outline takes the draw's style: its `color` (black when no style, a bare
color style key is used as the color) and its width (`line_width`, else `thin`,
else `thick`, else each backend's ordinary draw width); dash patterns and
arrows do not carry. Drawing is by the stack id only: there are no per-cube
or per-edge ids.

**Position, shading and labels.** The stack's position (for
`label_free_text` with `centroid_of` the stack id, and its entry in the entity
manifest) is the center of the bounding box of the projected lattice, the
middle of the drawn silhouette. For a full box it equals the prism's center;
for a concave stack (an L shape, an arch) it can lie in a notch and so over no
cube: to put text on the stack itself, use a column top face id. Face colors
are set on the definition. A `fill` on a column top id goes through the
ordinary fill layer, which is hoisted behind the ordered polygons, so under a
drawn stack's opaque faces it is hidden (visible only when the stack is not
drawn or its `top_color` is transparent).

**Count label.** `count_label` is one `label_free_text` with an explicit `at`
position, centered horizontally on the screen bounding box of the projected
lattice and 0.5 construction units above its top edge (`stack.COUNT_LABEL_MARGIN`),
so it never sits on cubes. It comes from the registry hook `lower_labels` (see
`ir/derived.py`): emitted **once** when the stack is drawn, i.e. a `draw` of the
stack id or a `draw` / `fill` of one of its column top faces (however many such
operations there are); an undrawn stack emits none, and a `fill` of the stack id
is an error. Because a column-top `fill` counts as drawing, a top-face-only fill
labels the whole stack. Limits: the label sits above the lattice's
bounding box, not the silhouette, so over an uneven stack it floats about as
far above the shorter columns as they fall short of the tallest; the margin is
in construction units, so its pixel gap shrinks on a wide canvas; in TikZ the
free text is plain `\node` text, where `^` is a LaTeX error. The count is not
checked against the cube count: text such as `"7 cubes"` on a six-cube stack
passes silently (use a `cube_count_equals` check).

Render operations that cannot work on the stack id are compile errors naming
the alternative: `fill` (or a `fill` hole) ("set `front_color`, `side_color`
and `top_color` ... or fill a column top face id such as `S_top_0_0`"), a
point slot (`draw_points`, `label_point`, any angle point) ("use a column top
face id"), a segment slot (`mark_segments`, `label_segment`; "stacks have no
addressable edges") and an arc slot (`mark_arcs`, `label_along_arc`). `draw`
and `label_free_text` with `centroid_of` the stack id are valid.

**Warnings.** Both go through the pipeline warnings (see
[Pipeline warnings](#pipeline-warnings)) and never fail a run:

- *not a height map*: a cube set with a cube that has an empty cell directly
  beneath it (some cube with y > 0 and no cube at (x, y-1, z)), e.g. an
  arch's bridge. The stack is drawn as given. The message is
  `block_stack 'S': cube set is not a height map: cubes float above empty cells`.
  A gap at y = 0 (columns 0 and 2 occupied, 1 empty) is still a height map and
  does not warn; neither does any `heights` stack. The warning appears whether
  or not the stack is drawn.
- *skewed projection*: any authored stack when the canvas has unequal axis
  scales (`canvas.aspect` not 1), as for the prism. Like the height-map
  warning, it fires whether or not the stack is drawn.

**Queries and checks.** The `stack` query (the query tool's `query_type:
"stack"` with `params: {"stack": "S"}`; `ir.queries.query_stack`) returns:

| Key | Meaning |
|-----|---------|
| `cube_count` | Number of cubes |
| `volume` | Volume in unit cubes (equal to `cube_count`) |
| `length`, `width`, `height` | Bounding-box extents along x, z and y: a height map's columns, rows and tallest column; a cube set's largest coordinate plus 1 on each axis (trailing empty cells do not extend a cube set) |
| `is_height_map` | No cube has an empty cell directly beneath it |

| Check | Fields | Meaning |
|-------|--------|---------|
| `cube_count_equals` | `stack`, `expected` | The stack's cube count equals `expected` (an integer; `12.0` is accepted, `12.5` is rejected at validation) |

The comparison is exact and `tol` is ignored. A `stack` that is not a block
stack, or does not exist, is a plain failed check ("... is not a block
stack"), not an evaluation error. The query's description is shown to the
model only with `solids` enabled.

*Example: a heights stack.* Rows run front to back: the front row has columns
of 1 and 2 cubes, the back row 3 and 0.

```json
{
  "define": [
    {"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
    {"kind": "block_stack", "id": "S", "origin": "O", "heights": [[1, 2], [3, 0]], "top_color": "#e6eefa"}
  ],
  "checks": [{"kind": "cube_count_equals", "stack": "S", "expected": 6}],
  "render": [
    {"kind": "draw", "obj": "S"},
    {"kind": "label_free_text", "text": "6 cubes", "centroid_of": "S_top_1_0"}
  ]
}
```

```json
{"cube_count": 6, "volume": 6, "length": 2, "width": 2, "height": 3, "is_height_map": true}
```

The public ids are `S_top_0_0`, `S_top_1_0` and `S_top_0_1` (the empty
column at x = 1, z = 1 has none) and the run has no warnings.

*Example: an arch.* Two pillars two cubes high at x = 0 and x = 2, a bridge
cube at height y = 1 over the empty cell between them (all at depth z = 0).

```json
{
  "define": [
    {"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
    {"kind": "block_stack", "id": "A", "origin": "O", "view": "isometric",
     "cubes": [[0, 0, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]]}
  ],
  "checks": [{"kind": "cube_count_equals", "stack": "A", "expected": 5}],
  "render": [{"kind": "draw", "obj": "A"}]
}
```

```json
{"cube_count": 5, "volume": 5, "length": 3, "width": 1, "height": 2, "is_height_map": false}
```

The run carries the not-a-height-map warning (the bridge floats over the
empty cell `[1, 0, 0]`); the column top ids are `A_top_0_0`, `A_top_1_0` (at
plane y = 2, the bridge's top) and `A_top_2_0`.

**Other surfaces.** Each is gated by the `solids` group and wraps the same
definition and check:

- *Recipe DSL.* The `stack` op takes `id`, `origin` (an existing point id, as
  for the prism), `heights` or `cubes`, the view fields and the three colors,
  and lowers to `block_stack` (it also takes `count_label`); the auto-canvas
  contains the stack's projected bounding box. (The recipe `prism` op and the
  pydsl `prism(...)` take the same fields as `rectangular_prism`, including
  `length_label`, `width_label`, `height_label` and `base_area_label`, each
  `None` / omitted by default; pydsl rejects an empty string with a `ValueError`
  naming the field.) The `cube_count` check (`{"check": "cube_count", "stack":
  "S", "expected": 6}`) lowers to `cube_count_equals`. With `solids` off both
  are rejected before lowering.
- *Python (pydsl).* `stack(origin, heights=None, cubes=None, view="oblique",
  depth_angle=None, depth_scale=None, side="right", front_color=None,
  side_color=None, top_color=None, count_label=None)` returns a `Stack` handle (hidden id
  `__pydsl_stack_N`). The stack is compiled at the call, so a misuse is the
  script's own error with the IR's message. `Stack` has `.cube_count`,
  `.volume`, `.top(x, z)` (the column's top face as a `Polygon`, for
  placing a label; a `ValueError` listing the occupied columns for any other
  `(x, z)`) and `.label(text)` (a floating label at the stack's position).
  `draw(stack)` draws it, `label_text(..., centroid_of=stack)` places text at
  its position, and `assert_cube_count(stack, expected)` wires
  `cube_count_equals`. The names `stack`, `Stack` and `assert_cube_count` are in
  `pydsl.GROUPED_NAMES["solids"]`, so they exist in the sandbox and prompt
  stub only with `solids` enabled.
- *Evals.* `solid_count` takes `kind: block_stack` and a literal `cube_count`
  (read from the authored `heights` sum or `cubes` length, with no compile).
  Three property types are evaluated on the compiled stack through
  `query_stack`: `stack_cube_count` (`[stack id, expected]`), `stack_extents`
  (`[stack id, length, width, height]`) and `stack_is_height_map` (`[stack
  id, true|false]`). A stack id of `"*"` matches any stack in the diagram, and
  a gate failure message is prefixed `stack:`. `stack_is_height_map: false` is
  how an overhang scenario expects the not-a-height-map condition. The
  scenarios are in `evals/scenarios_solids.yaml`.
- *Eval warnings.* Every eval record carries `warnings`: the pipeline's
  warning list for that run (an empty list for failed, timed-out and raw-code
  cells). A scenario may declare `fail_on_warnings: [substring, ...]` (a list
  of non-empty strings): each substring found, case-sensitively, in any
  recorded warning adds one gate failure `warning:<substring>`, so the cell's
  `gate_status` is `fail`. `deterministic_pass` is unaffected (it covers check
  failures only). The five prism scenarios use
  `fail_on_warnings: ["does not match its true length"]`, which catches a
  dimension label on the wrong edge, whether set by hand or by field. A
  whitespace-only entry is accepted and would match almost any warning; do not
  use one.

---

---

## Rendering

These contracts hold for every diagram, in both renderers (SVG and TikZ).

### Color forms

Every color value (a `color`, `fill` or other color key of a style, a bare
color used as a render op's `style`, a pydsl `color=` argument) accepts:

| Form | Example | Notes |
|------|---------|-------|
| named color | `red`, `gray`, `lightgray` | the shared set both renderers know |
| hex | `#9ec5ea`, `#9ce` | `#rrggbb` or `#rgb` |
| `rgb(r,g,b)` | `rgb(158, 197, 234)` | integers 0-255; spaces allowed |
| `hsv(h,s,v)` | `hsv(210, 0.5, 0.8)` | h 0-360, s and v 0-1 |
| xcolor mix | `blue!30`, `red!40!blue` | `name!pct[!name2]`, pct 0-100, second color defaults to white |

Hex, `rgb()` and `hsv()` become `#rrggbb` in SVG and a `\definecolor` (xcolor
`RGB` model) in TikZ, so the same value paints the same color in both; a mix
is converted to `#rrggbb` in SVG and passed to xcolor as-is in TikZ. An
unrecognized string is passed through unchanged with a renderer warning (the
two renderers may disagree on it); in TikZ one with characters outside
`[A-Za-z0-9!.,#%()\- ]` is replaced by `black`, so it cannot inject TeX. A render op's bare `style` that is not a
key of `styles` but is itself a recognized color is honored as that color for
both draw and fill in both renderers; bare `none` is not a color (it is
accepted only as a value inside a style, e.g. `fill: none`).

### SVG viewBox growth for labels

When a label's bounding box would extend past the SVG canvas, the SVG
renderer grows the `viewBox` (and the width/height) on that side to contain
it, preserving the scale: nothing moves in user coordinates, overflow on the
left or top is absorbed by a negative `viewBox` origin. Growth happens only
when a label overflows (a diagram without overflow is unchanged) and is capped
at 200 px per side, independently; a label further out than that is left
outside and reported by the label-bounds check. The width used for that
check, and for label collision avoidance, is estimated from the bundled
font's real glyph advances (with a floor of 0.6 em, and a flat 0.65 em per
character if the font cannot be loaded).

### Ordered polygons

`ir.OrderedPolygon` is an opaque filled polygon that carries its own stroke
and is painted in strict list order, so a painter's-algorithm figure (a block
stack) hides what is behind a face. An ordinary `fill` plus `draw` cannot do
this: every fill is hoisted before every stroke, so the outlines of far faces
show through near fills.

| Field          | Type            | Description |
|----------------|-----------------|-------------|
| `kind`         | `"ordered_polygon"` | |
| `points`       | list of point ids, at least 3 | Boundary order; ids of defined points |
| `fill`         | string          | Opaque fill, any [color form](#color-forms) |
| `stroke`       | string          | Outline color (default `black`) |
| `stroke_width` | number, `"thin"`, `"thick"` or omitted | Omitted (`None`, the default) is each backend's ordinary draw width: 1.5 px in SVG, tkz-euclide's own `line style` in TikZ (measured 0.2 pt, not TikZ's bare 0.4 pt `\draw` default); the units differ, so no one number matches both. `"thin"` / `"thick"` are the backends' ordinary thin / thick widths; a number is used as-is (px in SVG, pt in TikZ, like a style's `line_width`) |

It is **not** a member of the validated `RenderOp` union and cannot be
authored in JSON (the LLM-facing schemas and prompts do not mention it): it is
emitted only by a registered definition kind's `lower_draw` hook (as
`derived.Lowering` ops), in place of the draw it lowers. Both renderers keep
it at its list position because it shares the draw z-layer with draws and
marks (a stable sort); it carries its own fill, so it is never hoisted into
the fill layer, and the ordinary `Fill` operations are hoisted behind it: an
ordinary fill under an opaque ordered polygon is hidden. An ordered polygon
naming an undefined point is skipped with a renderer warning. An
unrecognized color string passes through with the usual renderer warning. In
SVG it is a `<polygon data-role="ordered-polygon" stroke-linejoin="round">`
and its edges are obstacles for label nudging, like drawn segments; in TikZ a
`\filldraw[line style,fill=...,draw=...,line join=round] ... -- cycle;`.

**Do not serialize a lowered diagram.** Because `OrderedPolygon` is outside the
`RenderOp` union, the lowered diagram (`derived.lower_render`'s output) and the
effective diagram (`derived.effective_diagram`'s output) are *internal
render-time views*: they are built without validation, exist only in memory
inside the two renderers, and must never be dumped, persisted or re-validated
(a dump of a lowered one emits serialization warnings, `ordered_polygon` fails
`DiagramIR` validation, and the effective view loses the private
`_synthesized_by` marker, so recompiling it reports the synthesized ids as
reserved). Both are `derived.RenderTimeDiagram` instances whose `model_dump`
and `model_dump_json` raise `TypeError` ("dump the authored DiagramIR
instead"); the authored `DiagramIR` serializes exactly as before.

### SVG data attributes

The SVG renderer (`to_svg.py`) tags what it draws with `data-*` attributes so
that tools reading the SVG (checks, viewers, the eval gates) do not have to
guess from geometry. The root `<svg>` carries `data-contract="N"`, the version
of this contract (`SVG_DATA_CONTRACT_VERSION`). Renaming or removing an
attribute, or changing what one means, bumps `N`; adding an attribute or a role
does not, so read what you need and ignore the rest. The TikZ renderer emits
none of this.

Values that name an object are **IR ids**, not script variable names. A pydsl
point that was never named in the IR has an id like `__pydsl_pt_3`; recover the
mapping from the run's variable manifest, not from the SVG.

Drawn objects (`Draw` and `DrawPoints`; `data-ir-id` is the id of the drawn object):

| Element | Attributes | Notes |
|---------|------------|-------|
| `polygon` | `data-ir-id`, `data-type` (`triangle` or `polygon`), `data-vertices` | `data-vertices` is a comma-separated list of point ids, in order |
| `polyline` | `data-ir-id`, `data-type="polyline"`, `data-vertices` | |
| `line` | `data-ir-id`, `data-type` (`segment`, `line` or `ray`), `data-endpoints` | `data-endpoints` is `a,b` (point ids) |
| `circle` | `data-ir-id`, `data-type="circle"`, `data-center` | `data-center` is omitted when the circle has no named center |
| `circle` (point) | `data-ir-id`, `data-type="point"` | one per drawn point |
| `ellipse` | `data-ir-id`, `data-type="ellipse"` | |
| `path` | `data-ir-id`, `data-type` (`arc` or `sector`) | |

Marks and fills, identified by `data-role`:

| `data-role` | Other attributes | Notes |
|-------------|------------------|-------|
| `fill` | `data-ir-id` | the filled object |
| `ordered-polygon` | (none) | see [Ordered polygons](#ordered-polygons) |
| `mark-right-angle` | `data-angle` | `a,o,b`: point ids, `o` the vertex |
| `mark-angle` | `data-angle`, optional `data-group` | `a,o,b` as above; `data-group` is the mark's group |
| `mark-segment` | `data-segment`, optional `data-group`, optional `data-ticks` | tick or slash marks on one segment; `data-ticks` is present only when the count was given explicitly |
| `mark-arc` | `data-arc`, optional `data-group`, optional `data-ticks` | tick marks on one arc or sector |
| `brace` | (none) | |

Labels (on a `<text>` element, or a `<g>` of glyph paths when the text needs
math layout; the same attributes either way):

| `data-role` | `data-for` | Notes |
|-------------|------------|-------|
| `label-point` | the point id | |
| `label-angle` | `a,o,b` | |
| `label-segment` | the segment, line, ray or arc id | |
| `label-along-arc` | the arc id | |
| `label-free-text` | (absent) | |
| `label-brace` | (absent) | |

Every label element also carries `data-label-text`, the text as authored
(before any math layout), and `data-bbox`, `x0,y0,x1,y1` in SVG pixels: the
renderer's estimate of the label's box, from the bundled font's glyph advances.
It is an estimate, not a measurement of the painted glyphs.

A label's position is the label element's own coordinates (`x`/`y` on a `<text>`).
For `data-role="label-segment"` that is the label's own placement, not the
segment's midpoint: compare it with the segment's `data-endpoints` coordinates
to see where on the segment the label sits.

With `debug_show_implicit=True` the renderer also emits an invisible
(`opacity="0"`) element for every object that a mark references but that was
never drawn on its own (a triangle side that carries a tick mark, say). These
carry `data-ir-id` and `data-implicit="true"`, plus the attributes of their
shape in the table above. They are absent by default.

`tests/test_svg_data_contract.py` pins the roles and attributes above.

### Pipeline warnings

A run collects a list of non-fatal `warnings` (on the result, and on a
pipeline error for the warnings gathered before it). Warnings never fail a
run; a strategy shows the previous attempt's warnings in its retry prompt.
Sources:

- renderer warnings (e.g. a draw of an undefined id, a `mark_arcs` /
  `label_along_arc` naming something that is not an arc or sector);
- failed `prefer`-level checks;
- `distance_equals` / `equal_length` / `ratio_equal` measuring a segment that
  joins two prism corners (a projection was measured; use
  `true_length_equals`);
- a prism on a canvas with unequal axis scales (the projection is skewed);
- a prism dimension label whose first number does not match the true length of the edge it labels: a `label_segment` on a prism edge, or a `length_label` / `width_label` / `height_label` field (substring `does not match its true length`; see [Label fields](#prism-label-fields));
- an unrecognized color string (see [Color forms](#color-forms));
- a right-angle mark on an angle that is not drawn at 90°, or an angle label whose text states a
  different value than the drawn angle, by more than a tolerance (1° by default):
  `Right-angle mark on ∠ABC, which is drawn at 72.5°, not 90°`; `Angle label "35°" is on ∠ABC,
  which is drawn at 41.3°`. Only a label that is exactly one angle value is read: `35°`, `35 deg`,
  `∠B = 60°`, `θ = 2π/3`, `π/3 rad`, `1.047 rad`. `x`, `?`, a bare `35`, a derivation such as
  `∠A = 180° − 40° − 40° = 100°` and any text with several numbers state no single value and are
  skipped. Arc marks (`mark_angle`, with or without a group) are never audited: a group is a
  rendering tag, and a figure may use it for something other than "these angles are equal", just
  as a textbook figure "not drawn to scale" may carry labels that differ from the drawing.
  What happens is set by `GeometryConfig.angle_check` (`GEOMETRY_ANGLE_CHECK`, or per call):
  `off` skips the audit, `warn` (the default) reports findings as warnings and never fails, and
  `retry` also fails the attempt for a finding above `angle_fail_tolerance_deg` (5° by default),
  so the strategy retries with it in the prompt; findings between `angle_tolerance_deg` and that
  stay warnings (`ir/angle_audit.py`, `AnglePolicy`);
- a segment, angle, free-text or along-arc label that shows a number the request does not state,
  which in practice is a computed answer written onto the figure: `Label "AC = 10" shows a number
  the request does not state. A figure shows what the request gives and names the unknown (x or ?);
  remove it unless the question asks for it`. The numbers in the request text are the givens; point
  names (`A1`), sub/superscripts and the unknown (`x`, `?`) are never read, a digit directly before π
  counts as a multiple of π when the request has no π, and a few numbers the request implies without
  writing them are allowed (90 for "right angle", "perpendicular", "square", "rectangle", "altitude" or
  "tangent"; 180 for "straight", "supplementary", "linear pair", "collinear", "semicircle" or "diameter";
  60 for "equilateral"). Numbers written as words are not read from the request. It is a heuristic and
  knows nothing about what the question asks, so it needs the request text and does not run without it.
  `GeometryConfig.answer_check` (`GEOMETRY_ANSWER_CHECK`, or per call): `off` skips it, `warn` (the
  default) reports it, `retry` also fails the attempt so the strategy retries with it in the prompt
  (`ir/answer_audit.py`). On a python_full edit the request is the edit request plus the labels the
  stored figure already shows;
- a `unit_cubes` prism whose id is never drawn (no gridlines).
- a `block_stack` cube set with a cube above an empty cell (not a height map);
- an authored `block_stack` when the canvas has unequal axis scales (the
  projection is skewed; drawn or not).
- two authored solids (prisms and/or block stacks) that are both drawn and
  whose screen bounding boxes overlap: `draw order is not depth order; solids
  '<a>' and '<b>' overlap on screen`. Solids are not depth-sorted against each
  other, so they paint in draw order. One warning per overlapping pair, `a`
  being the earlier-defined solid, pairs in definition order. A solid is
  "drawn" when a `draw` or `fill` render operation names its own id or any id
  it owns (its faces, edges, or a stack's column top faces), because a shaded
  prism is drawn through its face ids, never its own; labels and centroid
  targets do not count, and an undrawn solid never participates. A solid drawn
  through several of its ids still yields one warning per pair. A box is the axis-aligned box of the solid's projected corners
  (a stack's lattice); boxes that merely touch do not overlap (positive-area
  overlap only), and a lone or side-by-side solid never warns.

---

## Validation

After execution, the system checks:

1. **Construction validity**: Did every operation produce a result?
   (e.g. no parallel lines asked to intersect, no degenerate triangles)

2. **Geometric properties**: Configurable checks matching eval format:
   - `right_angle(A, B, C)`: angle at B is 90°
   - `parallel([A,B], [C,D])`: lines are parallel
   - `midpoint(M, A, B)`: M is the midpoint of AB (eval format; the IR check kind `midpoint` is gated and documented under "Measured checks" below)
   - `point_on_line(P, A, B)`: P lies on line AB
   - `point_on_circle(P, center, radius_point)`: P is on the circle
   - `equal_lengths([[A,B], [C,D]])`: segments have equal length
   - `equal_length` / `distance_equals` / `ratio_equal` (IR check kinds) measure segments and also circular and elliptical arcs and sectors, mixed freely. An arc's length is its curved length (the minor arc between its endpoints, or the major arc when `reflex` is set, whichever order start and end are given in; computed by `ir/curve_measures.py`'s `curve_length`); a sector's length is its curved edge only, not its two straight radii. A full circle or ellipse has no single length here: such an operand fails with a message naming its id: a circle is pointed at `radius_equals` / `equal_radius`, an ellipse (two radii, which `radius_equals` rejects) at `equal_radius`. Tolerances are all relative (see the tolerance contract below); elliptical lengths are computed numerically to about 1e-9, far inside the default tolerance.
   - `collinear(P, Q, R)`: points are collinear
   - `angle_bisector(D, A, B, C)`: AD bisects angle BAC
   - `perpendicular([A,B], [C,D])`: lines are perpendicular
   - `centroid(G, A, B, C)`: G is centroid of triangle ABC
   - `convex(P)`: polygon P's vertices form a convex shape
   - `ccw(P)`: polygon P's vertices are wound counter-clockwise (positive signed area)
   - `min_distance(A, B, min_dist)`: points A and B are at least min_dist apart
   - `congruent_triangles(T1, T2)`: triangles T1 and T2 are congruent (SSS: matching sorted side lengths, no required vertex correspondence)
   - `equal_radius([C1, C2, ...])`: all listed circles have the same radius — the circle-family counterpart of `equal_lengths` (requires at least two circles; "length" means nothing for a circle, so these stay separate check kinds)
   - `radius_equals(C, expected)`: circle C's radius equals `expected`, using the same relative-tolerance convention as `distance_equals` (`|actual - expected| < tol * max(actual, expected)`, no absolute floor)
   - `congruent_arcs([A1, A2, ...])`: the listed circular arcs/sectors are congruent — equal radius AND equal central-angle sweep (requires at least two). The sweep comparison is reflex-aware, so a minor arc and a reflex arc sharing the same two endpoints are never congruent; `tol` is relative for the radius term (a fraction of the radius, as for `radius_equals`) and absolute, in radians, for the sweep term. Elliptical arcs/sectors are congruent when their axes match (or are swapped) and one arc is a symmetry image of the other: a reflection across either axis or a half turn of the ellipse, possibly reversed. Equal span alone is not enough, because an ellipse's curvature varies along it. A circle and a genuine ellipse (two different radii) are never congruent; an elliptical arc with two equal radii counts as a circular arc.
   - `angle_value(A, O, B, expected_deg)`: the angle at O equals `expected_deg` degrees — complements `right_angle` (a fixed 90°) and `angle_equal` (two angles compared to each other, never to an absolute value). `tol` is in radians.
   - `circles_tangent(C1, C2)`: circles C1 and C2 are tangent to each other, externally (centers separated by the sum of the radii) or internally (by the difference). Distinct from `tangent`, whose `line` field is explicitly a line/segment/ray; two identical circles are not considered tangent.

   Each check kind above is also reachable from the Python builder surface as
   an `assert_*` function (`assert_equal_radius`, `assert_radius`,
   `assert_congruent_arcs`, `assert_angle_value`, `assert_circles_tangent` —
   see `geometry_diagrams/pydsl/asserts.py`).

   **IR check kinds.** The checks above are named in the eval format. The
   IR `Check` union (`geometry_diagrams/ir/ir.py`) uses the following kinds and
   fields; every check also takes `level` (`"must"`, default, or `"prefer"`: a
   failed `prefer` check only produces a warning), `tol` (optional, overrides the
   default) and `source` (optional provenance text). An angle is
   `{a, o, b}` (the angle at `o`).

   | Kind | Fields |
   |------|--------|
   | `distinct_points` | `a`, `b` |
   | `distinct_objects` | `a`, `b` |
   | `non_collinear` | `a`, `b`, `c` |
   | `collinear` | `points` (list) |
   | `contains`, `not_contains` | `p`, `obj` |
   | `parallel`, `not_parallel`, `perpendicular` | `l1`, `l2` |
   | `angle_equal` | `a1`, `a2` (angles) |
   | `right_angle` | `angle` |
   | `angle_value` | `angle`, `expected_deg` |
   | `similar_triangles` | `t1`, `t2`, optional `correspond` (list of `[t1_vertex, t2_vertex]`) |
   | `congruent_triangles` | `t1`, `t2` |
   | `ratio_equal` | `s1`, `s2`, `s3`, `s4` |
   | `equal_length` | `segs` (list) |
   | `distance_equals` | `seg`, `expected` |
   | `tangent` | `line`, `circle` |
   | `circles_tangent` | `c1`, `c2` |
   | `opposite_side`, `same_side` | `p`, `q`, `line_a`, `line_b` |
   | `centroid` | `g`, `a`, `b`, `c` |
   | `convex`, `ccw` | `polygon` |
   | `min_distance` | `a`, `b`, `min_dist` |
   | `equal_radius` | `circles` (list) |
   | `radius_equals` | `circle`, `expected` |
   | `congruent_arcs` | `arcs` (list) |
   | `volume_equals`, `cube_count_equals`, `true_length_equals` | see the solid sections |
   | `midpoint`, `proportional_lengths`, `between`, `length_multiple`, `angle_multiple`, `point_at`, `image_of` | see [Measured checks](#measured-checks-measured_checks-feature-group) |

   <a id="recipe-checks"></a>
   **Recipe checks.** The recipe DSL's top-level `checks` list takes its own,
   smaller set of kinds (tagged by `check`), lowered to the IR checks above:

   | `check` | Fields |
   |---------|--------|
   | `distance` | `points` `[A, B]`, `expected` (number) |
   | `parallel`, `perpendicular` | `seg1`, `seg2` (each `[P, Q]`) |
   | `angle_equals` | `points` `[a, vertex, b]`, `expected` (degrees) |
   | `collinear` | `points` (3 or more) |
   | `on_circle` | `point`, `circle` |
   | `tangent` | `obj1`, `obj2` |
   | `volume` | `prism`, `expected` (`solids` group) |
   | `true_length` | `points` `[corner, corner]`, `expected` (`solids` group) |
   | `cube_count` | `stack`, `expected` (integer; `solids` group) |

   `circle_tangent_at` additionally emits its own `circles_tangent` check.

3. **Annotation completeness**: All requested marks are present.

4. **Structural checks**: polygon counts, entity counts, etc.

Validation uses tolerance (default 5e-3, relative; a check's own `tol`
overrides it) for floating point comparisons.

   **Relative measure tolerances.** `equal_length`, `distance_equals`,
   `ratio_equal` and `radius_equals` compare purely relatively: the values
   agree when `|a - b| < tol * max(|a|, |b|)` (for `ratio_equal`, the two cross
   products `l1*l4` and `l2*l3`, i.e. lengths squared). `distance_equals` covers
   arc and sector operands by their curve length. The prism `volume_equals` and
   `true_length_equals` use the same shape with their near-exact default. There
   is no absolute floor, so the same figure at any uniform scale gets the same
   verdict. Behaviour change: earlier versions floored the scale at 1.0 for
   `distance_equals`, `ratio_equal`, `radius_equals` and the prism checks, so
   figures whose expected values are below 1 now get a stricter (truly
   relative) verdict; figures at or above 1 are unchanged. A zero expected (or
   measured) value has no scale, so the comparison is exact-only: a tiny
   nonzero value never matches an expected 0. Use a different check
   (e.g. `distinct_points`, `min_distance`) for a "zero length" claim.

   **Relative curve and tangency tolerances.** `contains` on a circle, ellipse,
   arc or sector accepts a point within `tol * radius` of the curve (the smaller
   semi-axis, for an ellipse, so a long thin ellipse keeps a meaningful tolerance); `not_contains` follows on its curved branches
   (its linear branch stays exact). `tangent` compares the center-to-line
   distance with the radius (the support distance, for an ellipse) relatively;
   `circles_tangent` compares the center distance with `r1 + r2` or `|r1 - r2|`
   within `tol * max(r1, r2, center distance)`; `centroid` compares within
   `tol * the triangle's longest side`; and `congruent_arcs` compares radii (and
   semi-axes) relatively, while sweeps and positions are angles in radians and
   keep an absolute `tol`. Compile-time `pick: on_object` on an arc is not
   affected: it keeps its own fixed tight tolerance (1e-9). Behaviour change:
   these checks were absolute distances, so figures above unit scale now get
   *looser* verdicts (a radius-10 circle tolerates 0.05 instead of 0.005) and
   sub-unit figures get stricter ones. Angle checks and `min_distance` stay
   absolute by design, and the `not_*` linear checks stay exact.

### Measured checks (`measured_checks` feature group)

`measured_checks` is an opt-in feature group (off by default; enable with
`GEOMETRY_FEATURES=measured_checks` or `GeometryConfig(features=...)`) for
check kinds that assert a numerically measured relation. A generated diagram
whose `checks` use a kind owned by a disabled group is rejected after parsing
by `require_features` (message: the kind, the group, how to enable), using the
rule table `CHECK_RULES` in `geometry_diagrams/features.py`. This is
generation-time only: stored IR with such a check always compiles, is checked
and renders with the group off. The structured strategy binds `DiagramIR` as its
output schema, so the kinds stay visible to that model; the post-parse
rejection is the gate (as for the other groups). No prompt text, recipe op or
pydsl `assert_*` exists for these kinds.

- `midpoint` (IR check, `{kind: "midpoint", m, a, b}`): point `m` lies within
  `tol * |ab|` of the midpoint of `a` and `b` (relative to the segment's own
  length, so the verdict is scale-free; default `tol` 5e-3). When `a` and `b`
  coincide there is no scale and `m` must equal them exactly. A failure states
  the expected and the measured coordinates. This is an assertion about
  existing points, unlike the `point_midpoint` definition (which constructs a
  point) and the eval-format `midpoint(M, A, B)` entry listed above.

- `proportional_lengths` (IR check, `{kind: "proportional_lengths", segs, values}`):
  the listed segments' lengths are proportional to `values` at any scale: for
  every i, `|len_i/len_0 - v_i/v_0| <= tol * (v_i/v_0)`. `segs` has two or more
  entries and `values` the same count, every value finite and > 0; violations
  are rejected at parse time (DiagramIR validation). Lengths are measured as by
  `equal_length` (arcs and sectors by their curved edge). A failure states the
  measured length ratios against the claimed value ratios; a zero-length first
  segment fails (no ratio to compare).
- `between` (IR check, `{kind: "between", p, a, b}`): point `p` lies strictly
  inside segment `ab`: within `tol * |ab|` of the segment and farther than
  `tol * |ab|` from each end (same `tol`, default 5e-3). Not the `between` pick
  rule (`{kind: "between", a, b}` in a definition's `pick` list, which selects
  among candidate points while constructing); the two live in different unions
  (`Check` versus the pick rules) and never collide. Coincident `a` and `b` have
  no segment, so the check fails (it cannot hold). A failure distinguishes "not
  on segment" (too far from the segment) from "at an end" (too close to `a` or
  `b`).
- `length_multiple` (IR check, `{kind: "length_multiple", s1, s2, factor}`):
  `|s1|` equals `factor` times `|s2|`, compared relative to the larger of the
  two magnitudes (`tol`, default 5e-3), so the verdict is scale-free. Lengths
  are measured as by `equal_length` (arcs and sectors by their curved edge).
  `factor` must be positive and finite (rejected at parse time). Unlike
  `ratio_equal`, it relates exactly two segments to a stated multiple.
- `angle_multiple` (IR check, `{kind: "angle_multiple", a1, a2, factor}`):
  angle `a1` equals `factor` times angle `a2`, each measured as `angle_equal`
  measures it (unsigned interior angle in radians). `tol` is absolute, in
  radians, applied to `|a1 - factor * a2|`. `factor` must be positive and
  finite. A central angle versus an inscribed angle on the same arc is
  `factor: 2`. A failure reports both angles in degrees.
- `point_at` (IR check, `{kind: "point_at", p, x, y}`): the compiled
  coordinates of point `p`, in construction units (independent of the canvas),
  equal `(x, y)`. `tol` (default 5e-3) is relative to
  `max(|x|, |y|, |p.x|, |p.y|)`. At the origin there is no scale: when the
  expected point and `p` are both exactly `(0, 0)` the check passes, and any
  difference there is exact-only (no tolerance applies when that maximum is 0;
  a point merely near the origin is compared against the other coordinate's
  magnitude, if any). `x` and `y` must be finite. Compiled coordinates carry
  small rounding, so expect agreement to about 1e-9, not bit equality.
- `image_of` (IR check, `{kind: "image_of", q, p, transform}`): point `q` is
  the image of point `p` under `transform`, a tagged union on `kind`:
  `translation` (`from_point`, `to_point`: shift by the vector between those
  two points), `dilation` (`center`, `factor`: any finite non-zero number,
  negatives allowed, the meaning of `point_dilate`'s `ratio`), `rotation`
  (`center`, `angle` in RADIANS, counter-clockwise positive, the meaning of
  `point_rotate`'s `angle`; note this differs from a "degrees" convention a
  downstream request may assume) and `reflection` (`across`: a point, for
  point symmetry, or a line, segment or ray, exactly the operands of
  `point_reflect`). The math is shared with the point definitions, so the check
  and the definitions cannot disagree. `tol` (default 5e-3) is relative to the
  distance from the transformation's anchor (the centre, the mirror line or
  point, or the translation vector's length) to `p`; when that distance is 0
  (e.g. `p` on the mirror) the comparison is exact-only. `factor` and `angle`
  must be finite (a zero `factor` or an unknown `kind` is rejected at parse
  time); a transform operand that is not the right object type fails the check
  with a message. A failure states where `q` is and where the image of `p`
  should be. This lets a redrawn figure be tested against a stated
  transformation. Gated by `measured_checks`.

Every `Check` union member is evaluated by a dedicated arm of `run_checks` and
handled by the pre-assert reference extractor (`direct_ids_referenced`); a
completeness test enumerates the union so a kind cannot be added to one and not
the other. Unknown kinds (stored by a newer version) still warn and pass.

On failure, error messages are suitable for feeding back to the LLM in a
retry loop if desired.

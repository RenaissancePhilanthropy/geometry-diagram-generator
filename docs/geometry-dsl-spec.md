# Geometry Diagram DSL — Design Specification

## Overview

A constructive DSL for generating geometry textbook diagrams. The LLM describes
*what* is in a diagram using named geometric constructions. The system computes
all coordinates deterministically via SymPy and renders via TikZ/tkz-euclide to SVG.

The LLM never reasons about coordinates, orientations, or numeric placement.
Every ambiguous operation is resolved by semantic selectors that read as natural
geometric language.

---

## Pipeline

```
Problem text
    │
    ▼
┌─────────────────────────────┐
│ 1. Recipe selection         │  Small model picks from catalog of
│    (small model, <500 tok)  │  recipe names + one-line descriptions.
└─────────────┬───────────────┘  Outputs: selected recipe IDs,
              │                  unmatched_concepts[], confidence.
              ▼
┌─────────────────────────────┐
│ 2. Prompt assembly          │  System prompt + DSL docs +
│    (deterministic)          │  2–3 fixed worked examples +
└─────────────┬───────────────┘  retrieved recipe YAML skills.
              │
              ▼
┌─────────────────────────────┐
│ 3. Construction generation  │  Main model reads problem + assembled
│    (main model, single call)│  context, outputs JSON construction
└─────────────┬───────────────┘  sequence + annotation block.
              │
              ▼
┌─────────────────────────────┐
│ 4. Execution + validation   │  SymPy resolves all operations.
│    (deterministic)          │  Checks geometric properties.
└─────────────┬───────────────┘  Flags degenerate/impossible constructions.
              │
              ▼
┌─────────────────────────────┐
│ 5. Rendering                │  Converts resolved geometry + annotations
│    (deterministic)          │  to TikZ → SVG (or other backend).
└─────────────────────────────┘
```

---

## Modes

### Abstract mode

Foundation objects are established by properties (angles, side lengths).
The system chooses a concrete coordinate embedding using layout conventions
(e.g. longest side horizontal, centroid roughly centered). The LLM never
sees coordinates.

### Grid mode

Foundation objects are placed at explicit coordinates. The renderer draws
axes, gridlines, and tick labels. Derived constructions work identically
to abstract mode — `midpoint`, `intersection`, etc. compute from whatever
coordinates exist.

### Mixed mode

Some points placed explicitly, some constructed. Renderer shows grid if any
foundation points use explicit coordinates.

The `mode` field is set per-diagram. After foundation, all operations are
mode-agnostic.

---

## Output Format

LLM output is JSON, parsed by Pydantic. Recipes (human-authored skill
examples in context) are YAML.

```json
{
  "mode": "abstract",
  "construction": [
    {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
     "spec": {"angle_B": 90, "side_AB": 3, "side_BC": 4}},
    {"op": "midpoint", "id": "M", "of": ["B", "C"]}
  ],
  "annotations": {
    "auto_mark_right_angles": true,
    "auto_label_points": true,
    "marks": [],
    "styles": []
  }
}
```

---

## Construction Operations

Every operation takes named inputs and produces named outputs.
No operation requires a solver — all results are computed analytically.
Operations execute sequentially; each step can reference any previously
created object by name.

### Foundation Operations

These establish the initial geometric world.

#### `triangle`
Create a triangle from a property specification.

| Field      | Type              | Description                            |
|------------|-------------------|----------------------------------------|
| `id`       | string            | Name for the triangle object           |
| `vertices` | [string, string, string] | Names for the three vertices    |
| `spec`     | object            | Properties (see below)                 |

Spec keys always use this triangle's own vertex IDs from `vertices` (e.g. for
`vertices: ["P","Q","R"]`, use `side_PQ`/`angle_P`, not fixed letters). Accepts
any sufficient combination of:
- `side_XY` for each pair of vertices X, Y — side length (either letter order
  accepted, e.g. `side_PQ` and `side_QP` name the same segment; give each edge
  only once)
- `angle_X` for each vertex X — angle measure in degrees
- `right_angle_at` — the vertex name with a right angle (shorthand for setting
  that angle to 90)

The system computes all unspecified values and chooses a realization.
Layout convention: base edge horizontal, triangle above the base.

#### `circle`
Create a circle.

| Field    | Type          | Description                              |
|----------|---------------|------------------------------------------|
| `id`     | string        | Name for the circle object               |
| `center` | string or expr | A named point or expression             |
| `radius` | number or expr | Radius value or expression              |
| `through`| string        | Alternative to radius: point on circle   |

Provide either `radius` or `through`, not both.

#### `polygon`
Create a polygon from existing vertices.

| Field      | Type      | Description                               |
|------------|-----------|-------------------------------------------|
| `id`       | string    | Name for the polygon object               |
| `vertices` | [string]  | Ordered list of vertex names (must exist) |

#### `regular_polygon`
Create a regular polygon.

| Field      | Type      | Description                               |
|------------|-----------|-------------------------------------------|
| `id`       | string    | Name for the polygon object               |
| `vertices` | [string]  | Names for the vertices                    |
| `center`   | string    | Center point name                         |
| `radius`   | number    | Circumradius                              |
| `start_angle` | number | Angle in degrees of first vertex from east (default: 90) |

#### `point` (grid mode)
Place a point at explicit coordinates.

| Field    | Type      | Description         |
|----------|-----------|---------------------|
| `id`     | string    | Point name          |
| `coords` | [number, number] | (x, y)      |

#### `point_external`
Place a point outside a circle at a relative position.

| Field           | Type      | Description                              |
|-----------------|-----------|------------------------------------------|
| `id`            | string    | Point name                               |
| `relative_to`   | string    | Circle ID                                |
| `direction`     | string    | "right", "left", "above", "below"        |
| `distance_ratio`| number    | Multiple of radius for distance from center |


### Line and Segment Operations

#### `line_through`
Infinite line through two existing points.

| Field    | Type              | Description             |
|----------|-------------------|-------------------------|
| `id`     | string            | Line name               |
| `points` | [string, string]  | Two point names         |

#### `segment`
Segment between two existing points.

| Field      | Type              | Description             |
|------------|-------------------|-------------------------|
| `id`       | string            | Segment name            |
| `endpoints`| [string, string]  | Two point names         |

#### `ray`
Ray from a point through another point.

| Field    | Type   | Description               |
|----------|--------|---------------------------|
| `id`     | string | Ray name                  |
| `from`   | string | Origin point              |
| `through`| string | Direction point           |


### Derived Construction Operations

These produce new objects from existing ones. Each is a single
deterministic computation.

#### `midpoint`
| Field | Type              | Description                 |
|-------|-------------------|-----------------------------|
| `id`  | string            | Name for the midpoint       |
| `of`  | [string, string]  | Two endpoint names          |

#### `intersection`
| Field      | Type     | Description                           |
|------------|----------|---------------------------------------|
| `id`       | string   | Name for intersection point           |
| `of`       | [string, string] | Two object IDs (lines, circles) |
| `selector` | Selector | Required when multiple results exist  |

Returns a point. For line-line: no selector needed (0 or 1 result).
For line-circle and circle-circle: selector required.

#### `perpendicular`
Line perpendicular to a given line, through a given point.

| Field    | Type   | Description                      |
|----------|--------|----------------------------------|
| `id`     | string | Name for the perpendicular line  |
| `to_line`| string or [string, string] | Line ID or two points defining it |
| `through`| string | Point the perpendicular passes through |

#### `parallel`
Line parallel to a given line, through a given point.

| Field    | Type   | Description                    |
|----------|--------|--------------------------------|
| `id`     | string | Name for the parallel line     |
| `to_line`| string or [string, string] | Line ID or two points |
| `through`| string | Point the parallel passes through |

#### `perpendicular_bisector`
| Field  | Type              | Description                    |
|--------|-------------------|--------------------------------|
| `id`   | string            | Name for the bisector line     |
| `of`   | [string, string]  | Two endpoint names             |

Also creates the midpoint (accessible as `{id}_mid` if needed).

#### `angle_bisector`
Bisects the interior angle at a vertex.

| Field          | Type   | Description                   |
|----------------|--------|-------------------------------|
| `id`           | string | Name for the bisector line/ray|
| `vertex`       | string | Vertex point                  |
| `ray1_toward`  | string | Point on one ray              |
| `ray2_toward`  | string | Point on the other ray        |

Always bisects the non-reflex angle.

#### `altitude`
Drop altitude from a vertex to the opposite side of a triangle.

| Field        | Type   | Description                     |
|--------------|--------|---------------------------------|
| `id`         | string | Name for the altitude line      |
| `triangle`   | string | Triangle ID                     |
| `from_vertex`| string | Vertex to drop from             |
| `foot`       | string | Name for the foot point         |

Produces both the line and the foot point.

#### `centroid`
| Field | Type   | Description              |
|-------|--------|--------------------------|
| `id`  | string | Name for the centroid    |
| `of`  | string | Triangle or polygon ID   |

#### `circumcircle`
| Field      | Type   | Description                       |
|------------|--------|-----------------------------------|
| `id`       | string | Name for the circle               |
| `of`       | string | Triangle ID                       |
| `center`   | string | Name for the circumcenter point   |

#### `incircle`
| Field      | Type   | Description                       |
|------------|--------|-----------------------------------|
| `id`       | string | Name for the circle               |
| `of`       | string | Triangle ID                       |
| `center`   | string | Name for the incenter point       |

#### `point_along`
Place a point at a distance along a line or ray from a given point.

| Field     | Type          | Description                         |
|-----------|---------------|-------------------------------------|
| `id`      | string        | Name for the new point              |
| `from`    | string        | Starting point                      |
| `on`      | string        | Line or ray ID                      |
| `distance`| number or expr| Distance from starting point        |
| `direction`| Selector     | Which direction along the line      |

#### `point_on_segment`
Place a point on a segment at a given ratio.

| Field   | Type          | Description                           |
|---------|---------------|---------------------------------------|
| `id`    | string        | Name for the new point                |
| `segment`| [string, string] | Endpoint names                   |
| `ratio` | number or expr| Ratio from first to second endpoint (0–1) |

#### `reflection`
Reflect a point across a line or through a point.

| Field  | Type   | Description                      |
|--------|--------|----------------------------------|
| `id`   | string | Name for reflected point         |
| `point`| string | Point to reflect                 |
| `over` | string | Line ID or point to reflect over |

#### `rotation`
Rotate a point around a center.

| Field    | Type          | Description                     |
|----------|---------------|---------------------------------|
| `id`     | string        | Name for the rotated point      |
| `point`  | string        | Point to rotate                 |
| `center` | string        | Center of rotation              |
| `angle`  | number or expr| Rotation in degrees, CCW positive|

#### `tangent_line`
Tangent to a circle at a point on the circle.

| Field    | Type   | Description                              |
|----------|--------|------------------------------------------|
| `id`     | string | Name for the tangent line                |
| `circle` | string | Circle ID                                |
| `at`     | string | Point on the circle (must be on circle)  |

#### `circle_tangent_at`
A new circle of a given radius, tangent to an existing circle at a point on
that circle's boundary. The IR-level definition is `ir.CircleTangentAt`; the
recipe DSL surface is `geometry_diagrams.recipe.dsl.CircleTangentAtOp`, and
the pydsl surface is `geometry_diagrams.pydsl.api.tangent_circle`.

| Field      | Type           | Description                                       |
|------------|----------------|---------------------------------------------------|
| `id`       | string         | Name for the new circle                           |
| `circle`   | string         | Reference circle ID (must be a genuine circle, not an ellipse) |
| `point`    | string         | Tangency point; must already lie on `circle`'s boundary |
| `radius`   | number or expr | Radius of the new circle (must be positive)       |
| `tangency` | string         | `"external"` (default) or `"internal"`            |

`tangency: "external"` sits the new circle outside the reference one, the two
touching from opposite sides; `"internal"` sits it on the same side — nested
inside the reference circle, or enclosing it when `radius` exceeds the
reference radius (both are valid; only a circle identical to the reference is
rejected). A `point` that is not on `circle`'s boundary is a compile-time
error, never silently reprojected.

The new circle's center is an OUTPUT, addressable as `<id>_center` by later
operations (e.g. a segment joining the two centers, or a label on the center)
— the same way `circumcircle`/`incircle` name their derived centers. From the
recipe DSL this op additionally emits an auto-generated `circles_tangent`
check on the two circles as a safety net.

#### `extend_segment`
Extend a segment beyond one of its endpoints.

| Field     | Type          | Description                          |
|-----------|---------------|--------------------------------------|
| `id`      | string        | Name for the new endpoint            |
| `segment` | [string, string] | Original segment endpoints        |
| `beyond`  | string        | Which endpoint to extend beyond      |
| `distance`| number or expr| Distance beyond the endpoint         |

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
group. Stored diagrams always compile and render. Supported on a tilted
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
ellipse x ellipse and circle x ellipse pairs with float radii, which SymPy
cannot, so those no longer fail; pairs with exact radii and no tilt keep the
exact SymPy result. Not yet supported, an error naming the ellipse: SVG
drawing on a canvas with an `aspect` other than 1. Labels are not yet nudged
away from a tilted outline.

### Solid Operations

Solids belong to the `solids` feature group (off by default for generation;
see `geometry_diagrams/features.py`). A stored diagram containing a solid
always compiles and renders, whatever the feature setting.

#### `rectangular_prism`
A right rectangular prism (box) drawn as a parallel projection. The
IR-level definition is `ir.RectangularPrism`.

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

Both are near-exact: `|actual - expected| <= tol * max(|expected|, 1)` with a
default `tol` of 1e-9 (an off-by-one volume fails); an explicit `tol` on the
check overrides it. Every other check keeps the default tolerance (5e-3).
`distance_equals`, `equal_length` and `ratio_equal` on a segment joining two
prism corners keep their 2D meaning (they measure the drawing) and add a
pipeline warning saying a projection was measured and naming
`true_length_equals`.

#### `block_stack`
An irregular stack of unit cubes drawn as a parallel projection: the
building-plan "how many cubes?" figure. The IR-level definition is
`ir.BlockStack` (compiled by `geometry_diagrams/ir/stack.py`). Like the prism
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

<!-- stack-example-result: heights -->
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

<!-- stack-example-result: arch -->
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

## Selectors

Selectors resolve ambiguity when an operation has multiple valid results.
Every selector uses named geometric objects as references — never absolute
coordinates or screen positions.

Selectors can be composed as a filter chain (array) when needed:
```json
"selector": [
  {"between": ["A", "B"]},
  {"nearest_to": "C"}
]
```
Each selector narrows the candidate set. For most operations a single
selector suffices.

### Proximity Selectors

| Selector               | Meaning                                |
|------------------------|----------------------------------------|
| `nearest_to: P`        | Closest to point P                     |
| `farthest_from: P`     | Farthest from point P                  |

Use when one solution is "closer" to a point the problem cares about.

### Side-of-Line Selectors

| Selector                                     | Meaning                              |
|----------------------------------------------|--------------------------------------|
| `same_side_as: {line: [A,B], point: C}`      | On the same side of line AB as C     |
| `opposite_side_of: {line: [A,B], point: C}`  | On the opposite side of line AB from C|
| `upper_of_line: [A,B]`                       | Left side walking A→B (fallback)     |
| `lower_of_line: [A,B]`                       | Right side walking A→B (fallback)    |

Prefer `same_side_as`/`opposite_side_of` whenever a reference point
exists. Use `upper_of_line`/`lower_of_line` only when no third point
is available yet. Convention: "upper" = left side of directed line A→B
(equivalently, the side reached by rotating A→B by +90°).

### Betweenness Selectors

| Selector                           | Meaning                          |
|------------------------------------|----------------------------------|
| `between: [A, B]`                  | Lies on the segment AB           |
| `beyond: {from: A, past: B}`      | On the far side of B from A      |

Use when intersection points are collinear with known points.

### Interior/Exterior Selectors

| Selector               | Meaning                                      |
|------------------------|----------------------------------------------|
| `interior_of: polygon` | Inside the polygon's interior                |
| `exterior_of: polygon` | Outside the polygon's interior               |

Use for constructions involving auxiliary circles or lines that cross
polygon boundaries.

### Parametric Selectors (use sparingly)

| Selector                                        | Meaning                         |
|-------------------------------------------------|---------------------------------|
| `clockwise_from: {on: circle, reference: P}`    | First point CW from P on circle |
| `counterclockwise_from: {on: circle, reference: P}` | First point CCW from P     |

Avoid in LLM-composed output. Acceptable in pre-verified recipes.

### Direction Selectors (for `point_along`)

| Selector         | Meaning                            |
|------------------|------------------------------------|
| `toward: P`      | In the direction of P              |
| `away_from: P`   | In the opposite direction from P   |

Side-of-line and interior/exterior selectors also work for direction
when combined with `point_along`.

---

## Expression Language

Numeric fields accept inline expressions. The grammar is deliberately
minimal — complex geometric computations belong in DSL operations, not
expressions.

### Values
```
42, 3.5                  literal numbers
pi                       constant (π)
length(A, B)             distance between two points
radius(c)                radius of a named circle
angle(A, B, C)           non-reflex angle at B in degrees
```

### Arithmetic
```
+  -  *  /               basic operators
sqrt(x)                  square root
```

### Trigonometry (degrees)
```
sin(x)  cos(x)  tan(x)
```

### Usage in operations
```json
{"op": "point_along", "id": "D", "from": "A", "on": "perp_A",
 "distance": "length(A, B)", "direction": {"toward": "B"}}

{"op": "circle", "id": "c2", "center": "O",
 "radius": "radius(c1) * 2"}

{"op": "rotation", "id": "P2", "point": "P1", "center": "O",
 "angle": 60}
```

Expressions are evaluated after all referenced objects exist. The system
raises an error on forward references.

---

## Annotations

Annotations are visual additions that don't affect geometry. The LLM
explicitly requests them in a separate block.

### Batch Flags

| Flag                     | Default | Effect when true                      |
|--------------------------|---------|---------------------------------------|
| `auto_mark_right_angles` | false   | Mark every 90° angle in construction  |
| `auto_label_points`      | true    | Label every named point               |

### Marks

#### `mark_angle`
Mark a single angle.

| Field         | Type   | Description                            |
|---------------|--------|----------------------------------------|
| `vertex`      | string | Vertex point                           |
| `ray1_toward` | string | Point on first ray                     |
| `ray2_toward` | string | Point on second ray                    |
| `label`       | string | Optional label (e.g. "α", "1", "60°") |
| `reflex`      | bool   | If true, mark the reflex angle (default false) |

Default: marks the non-reflex angle between the two rays.

#### `mark_right_angle`
Mark a right angle with the standard square symbol.

| Field         | Type   | Description              |
|---------------|--------|--------------------------|
| `vertex`      | string | Vertex point             |
| `ray1_toward` | string | Point on first ray       |
| `ray2_toward` | string | Point on second ray      |

#### `mark_angle_group`
Mark multiple angles as visually matching (same number of arcs, same label).

| Field    | Type      | Description                                |
|----------|-----------|--------------------------------------------|
| `angles` | array     | Each: {vertex, ray1_toward, ray2_toward}   |
| `arcs`   | integer   | Number of arc strokes (1, 2, or 3)         |
| `label`  | string    | Optional shared label                      |

#### `mark_equal_lengths`
Mark segments as equal with tick marks.

> **Note:** this section predates the current implementation and its
> `{segments: [[P,Q],...], ticks: n}` shape does not match any real schema
> today. The actual IR-level render op is `ir.MarkSegments` (see
> `geometry_diagrams/ir/ir.py`): it takes `segs` (a list of already-defined
> segment ids, not raw point pairs) plus either a `group` string (an
> equal-length group name; a "tickN" name or first-encounter order decides
> the count, capped at 6 by the renderers' mark-symbol palette) or an
> explicit `ticks: int` field with no upper bound. `ticks` is IR/renderer-only
> — the recipe DSL and pydsl surfaces don't expose it yet. `group` is a
> namespace shared with `ir.MarkArcs` below — a segment and an arc marked
> with the same group name resolve to the same tick count.

| Field      | Type    | Description                               |
|------------|---------|-------------------------------------------|
| `groups`   | array   | Each group: {segments: [[P,Q],...], ticks: n} |

Each group shares a tick count. Different groups get different counts.
```json
{"op": "mark_equal_lengths",
 "groups": [
   {"segments": [["A","B"], ["A","C"]], "ticks": 1},
   {"segments": [["B","C"]], "ticks": 2}
 ]}
```

#### `mark_parallel`
Mark lines as parallel with arrow marks.

| Field    | Type    | Description                                  |
|----------|---------|----------------------------------------------|
| `groups` | array   | Each group: {lines: [[P,Q],...], arrows: n}  |

Same grouping logic as equal lengths.

#### `mark_arcs`

Mark an arc (or a sector's curved edge) with tick marks across the curve, the
arc-space counterpart of `mark_equal_lengths`.

The IR-level render op is `ir.MarkArcs` (see `geometry_diagrams/ir/ir.py`),
with `arcs`, `group`, `ticks` fields as below. The recipe DSL surface
(`geometry_diagrams.recipe.dsl.MarkArcs`, `{"kind": "mark_arcs", ...}` in
`annotations.marks`) exposes `arcs` and `group` only — `ticks` (an explicit,
uncapped count) is IR/renderer-only, same as `mark_equal_lengths`. The
pydsl surface (`geometry_diagrams.pydsl.api.mark_equal`) dispatches to this
op automatically when passed a curved handle.

| Field   | Type          | Description                                    |
|---------|---------------|-------------------------------------------------|
| `arcs`  | array         | Already-defined `arc_center_start_end`, `sector_center_start_end` or elliptical variant ids |
| `group` | string        | Shared with `ir.MarkSegments`'s `group` namespace — see note above |
| `ticks` | integer       | Explicit tick count, no upper bound (IR/renderer-only) |

For a `sector_center_start_end`, ticks go on its curved edge only, never on
either of its two straight radii. Elliptical variants
(`elliptical_arc_center_start_end`, `elliptical_sector_center_start_end`,
axis-aligned) are supported in both renderers: the ticks straddle the curve at
its parametric midpoint, oriented along the ellipse's own normal there (not the
radial direction), and for several ticks are spaced evenly by arc length about
that midpoint — the same convention as a circular arc. Any other id (a segment,
a circle, an undefined or non-arc id) is skipped with a warning.

A shared `group` gives a segment and an arc the same tick *index*, not
necessarily the same *glyph*: indices 1–3 render identically on both (1/2/3
plain ticks), but a segment's mark-symbol palette diverges from index 4
onward into diagonal-slash forms ("s", "s|", "s||") that have no arc
equivalent — an arc always draws N plain radial ticks regardless.

### Labels

#### `label_segment`
Add a text label to a segment (e.g. side length name).

| Field     | Type   | Description                               |
|-----------|--------|-------------------------------------------|
| `segment` | [string, string] | Segment endpoints               |
| `text`    | string | Label text (e.g. "a", "5", "c²")         |
| `position`| string | "midpoint" (default), "near_start", "near_end" |

#### `label_line`
Add a text label to a line.

| Field  | Type   | Description                |
|--------|--------|----------------------------|
| `line` | string | Line ID                    |
| `text` | string | Label text                 |

#### `label_circle`
Add a text label to a circle.

| Field   | Type   | Description                |
|---------|--------|----------------------------|
| `circle`| string | Circle ID                  |
| `text`  | string | Label text                 |

#### `label_along_arc`

> **Note:** this op has no pydsl surface yet — it exists as the IR-level
> render op `ir.LabelAlongArc` (see `geometry_diagrams/ir/ir.py`) and, as of
> this DSL surface, as `geometry_diagrams.recipe.dsl.LabelAlongArc`
> (`{"kind": "label_along_arc", ...}` in `annotations.labels`), a close-to-
> pure field passthrough — the fields below are identical to `ir.LabelAlongArc`'s.

Text laid out along an arc (or a sector's curved edge), one rotated
glyph at a time — distinct from `label_segment`'s existing arc handling,
which places a single upright label near the arc's midpoint.

| Field   | Type                    | Description                          |
|---------|-------------------------|---------------------------------------|
| `arc`   | string                  | Already-defined `arc_center_start_end`, `sector_center_start_end` or elliptical variant id |
| `text`  | string                  | Label text                            |
| `side`  | "outside" \| "inside"   | Which radial side of the curve the glyphs sit on (default "outside") |
| `pos`   | number, 0–1             | Fraction along the arc's sweep the string is centered on (default 0.5, the midpoint) |
| `flip`  | bool \| null            | `null` (default) auto-orients glyphs upright regardless of which half of the circle the arc sits on; `true`/`false` forces the orientation |

For a `sector_center_start_end`, the text follows its curved edge only.
Elliptical variants are supported in both renderers: the glyph baseline is the
curve offset by the usual clearance along the ellipse's own normal, and each
glyph advance is measured as arc length along that offset curve (local tangent
for rotation), so uneven curvature never squeezes or stretches the spacing.
`pos` is a fraction of the parametric sweep; an `inside` clearance is capped at
the local radius of curvature at the anchor. Any other id is skipped with a
warning.

A `text` that can't be split into glyphs — anything the mathtext engine
owns (LaTeX commands, `$...$`, fractions, Greek letters) or anything
carrying a sub/superscript — degrades to a single unrotated label at the
arc anchor, plus a warning, rather than silently dropping the un-layoutable
part (e.g. flattening a subscript).

### Style

#### `style`
Apply visual styling to an object.

| Field    | Type   | Description                              |
|----------|--------|------------------------------------------|
| `target` | string | Object ID                                |
| `stroke` | string | "solid" (default), "dashed", "dotted"    |
| `fill`   | string | "none" (default), "light", "accent_light"|
| `weight` | string | "normal" (default), "thin", "thick"      |

### Draws and arrowheads

`annotations.draws` is a list of explicit draw directives, each targeting an
existing object (`obj`) or a vertex-pair shorthand (`endpoints`):

```json
{"obj": "ray1", "style": {"color": "blue", "->": true}}
```

`style` accepts either a named key into `annotations.styles`, a bare color
name, or an inline dict. Recognized style keys:

| Key       | Type   | Effect                                          |
|-----------|--------|--------------------------------------------------|
| `color`   | string | Stroke/fill color                                |
| `thick` / `thin` | bool | Stroke weight                             |
| `dashed` / `dotted` | bool | Dash pattern                           |
| `->`      | bool   | Arrowhead at the object's end point               |
| `<-`      | bool   | Arrowhead at the object's start point             |
| `<->`     | bool   | Arrowheads at both ends                           |

Arrowheads work on `segment` and `ray` objects (and any other line-like
draw). The arrowhead is always filled with the same color as the stroke —
a `ray` drawn with `{"color": "red", "->": true}` gets a red line and a red
arrowhead, not a black one, so line color remains a reliable cue on its own
(important for viewers who can't distinguish lines by position alone).

```json
{"op": "ray", "id": "r1", "from": "A", "through": "B"}
```
```json
{"obj": "r1", "style": {"color": "red", "->": true}}
```

---

## Recipe Format

Recipes are YAML files used as skill examples in the LLM's context.
They teach both construction procedures and DSL patterns. The LLM reads
them and writes adapted JSON — recipes are not black-box invocations.

```yaml
name: square_on_segment
description: >
  Construct a square on a given segment, on the exterior of a reference
  polygon. The segment becomes one side of the square.

example:
  # Given: points A and B forming a side, triangle T as reference
  - op: perpendicular
    id: perp_A
    to_line: [A, B]
    through: A
  - op: point_along
    id: D
    from: A
    on: perp_A
    distance: length(A, B)
    direction:
      opposite_side_of:
        line: [A, B]
        point: centroid(T)
  - op: perpendicular
    id: perp_B
    to_line: [A, B]
    through: B
  - op: point_along
    id: C
    from: B
    on: perp_B
    distance: length(A, B)
    direction:
      opposite_side_of:
        line: [A, B]
        point: centroid(T)
  - op: polygon
    id: sq_AB
    vertices: [A, B, C, D]

properties:
  - ABCD is a square with side length equal to AB
  - The square is on the opposite side of AB from the centroid of T
  - D is adjacent to A; C is adjacent to B
```

### Recipe catalog entry (for selection model)
```yaml
- id: square_on_segment
  name: Square on segment
  description: Build a square on a segment, exterior to a reference polygon
  tags: [square, segment, side-selection]

- id: equilateral_on_segment
  name: Equilateral triangle on segment
  description: Build an equilateral triangle on a segment, exterior to a reference polygon
  tags: [equilateral, segment, side-selection]
```

### Recipe selection output
```json
{
  "selected_recipes": ["square_on_segment"],
  "unmatched_concepts": [],
  "confidence": "high"
}
```

Confidence levels:
- `high`: all concepts matched, straightforward problem
- `medium`: most concepts matched, may need atomic primitives for some parts
- `low`: significant unmatched concepts, likely out of scope or needs fallback

---

## Grid Mode Details

### Canvas setup
```json
{"op": "canvas", "x_range": [-5, 8], "y_range": [-3, 6],
 "grid": true, "axes": true, "tick_interval": 1}
```

The system auto-computes range if not specified, with padding.

### Explicit point placement
```json
{"op": "point", "id": "A", "coords": [3, 4]}
```

After foundation points are placed, all derived operations work
identically to abstract mode.

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
two renderers may disagree on it). A render op's bare `style` that is not a
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
   - `midpoint(M, A, B)`: M is the midpoint of AB
   - `point_on_line(P, A, B)`: P lies on line AB
   - `point_on_circle(P, center, radius_point)`: P is on the circle
   - `equal_lengths([[A,B], [C,D]])`: segments have equal length
   - `equal_length` / `distance_equals` / `ratio_equal` (IR check kinds) measure segments and also circular and elliptical arcs and sectors, mixed freely. An arc's length is its curved length (the minor arc between its endpoints, or the major arc when `reflex` is set, whichever order start and end are given in; computed by `ir/curve_measures.py`'s `curve_length`); a sector's length is its curved edge only, not its two straight radii. A full circle or ellipse has no single length here: such an operand fails with a message naming its id: a circle is pointed at `radius_equals` / `equal_radius`, an ellipse (two radii, which `radius_equals` rejects) at `equal_radius`. Tolerances are unchanged (absolute for `equal_length`, relative for `distance_equals`); elliptical lengths are computed numerically to about 1e-9, far inside the default tolerance.
   - `collinear(P, Q, R)`: points are collinear
   - `angle_bisector(D, A, B, C)`: AD bisects angle BAC
   - `perpendicular([A,B], [C,D])`: lines are perpendicular
   - `centroid(G, A, B, C)`: G is centroid of triangle ABC
   - `convex(P)`: polygon P's vertices form a convex shape
   - `ccw(P)`: polygon P's vertices are wound counter-clockwise (positive signed area)
   - `min_distance(A, B, min_dist)`: points A and B are at least min_dist apart
   - `congruent_triangles(T1, T2)`: triangles T1 and T2 are congruent (SSS: matching sorted side lengths, no required vertex correspondence)
   - `equal_radius([C1, C2, ...])`: all listed circles have the same radius — the circle-family counterpart of `equal_lengths` (requires at least two circles; "length" means nothing for a circle, so these stay separate check kinds)
   - `radius_equals(C, expected)`: circle C's radius equals `expected`, using the same relative-tolerance convention as `distance_equals` (`|actual - expected| < tol * max(expected, 1.0)`)
   - `congruent_arcs([A1, A2, ...])`: the listed circular arcs/sectors are congruent — equal radius AND equal central-angle sweep (requires at least two). The sweep comparison is reflex-aware, so a minor arc and a reflex arc sharing the same two endpoints are never congruent; `tol` applies to the radius term in length units and to the sweep term in radians. Elliptical arcs/sectors are congruent when their axes match (or are swapped) and one arc is a symmetry image of the other: a reflection across either axis or a half turn of the ellipse, possibly reversed. Equal span alone is not enough, because an ellipse's curvature varies along it. A circle and a genuine ellipse (two different radii) are never congruent; an elliptical arc with two equal radii counts as a circular arc.
   - `angle_value(A, O, B, expected_deg)`: the angle at O equals `expected_deg` degrees — complements `right_angle` (a fixed 90°) and `angle_equal` (two angles compared to each other, never to an absolute value). `tol` is in radians.
   - `circles_tangent(C1, C2)`: circles C1 and C2 are tangent to each other, externally (centers separated by the sum of the radii) or internally (by the difference). Distinct from `tangent`, whose `line` field is explicitly a line/segment/ray; two identical circles are not considered tangent.

   Each check kind above is also reachable from the Python builder surface as
   an `assert_*` function (`assert_equal_radius`, `assert_radius`,
   `assert_congruent_arcs`, `assert_angle_value`, `assert_circles_tangent` —
   see `geometry_diagrams/pydsl/asserts.py`).

3. **Annotation completeness**: All requested marks are present.

4. **Structural checks**: polygon counts, entity counts, etc.

Validation uses tolerance (default 1e-6) for floating point comparisons.
On failure, error messages are suitable for feeding back to the LLM in a
retry loop if desired.

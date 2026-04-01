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

Spec accepts any sufficient combination of:
- `side_AB`, `side_BC`, `side_CA` — side lengths
- `angle_A`, `angle_B`, `angle_C` — angle measures in degrees
- `right_angle_at` — shorthand for setting one angle to 90

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

#### `extend_segment`
Extend a segment beyond one of its endpoints.

| Field     | Type          | Description                          |
|-----------|---------------|--------------------------------------|
| `id`      | string        | Name for the new endpoint            |
| `segment` | [string, string] | Original segment endpoints        |
| `beyond`  | string        | Which endpoint to extend beyond      |
| `distance`| number or expr| Distance beyond the endpoint         |

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

### Style

#### `style`
Apply visual styling to an object.

| Field    | Type   | Description                              |
|----------|--------|------------------------------------------|
| `target` | string | Object ID                                |
| `stroke` | string | "solid" (default), "dashed", "dotted"    |
| `fill`   | string | "none" (default), "light", "accent_light"|
| `weight` | string | "normal" (default), "thin", "thick"      |

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
   - `collinear(P, Q, R)`: points are collinear
   - `angle_bisector(D, A, B, C)`: AD bisects angle BAC
   - `perpendicular([A,B], [C,D])`: lines are perpendicular
   - `centroid(G, A, B, C)`: G is centroid of triangle ABC

3. **Annotation completeness**: All requested marks are present.

4. **Structural checks**: polygon counts, entity counts, etc.

Validation uses tolerance (default 1e-6) for floating point comparisons.
On failure, error messages are suitable for feeding back to the LLM in a
retry loop if desired.

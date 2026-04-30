---
name: geometry-recipe-maker
description: Use when creating a new geometry recipe YAML file for the geometry-tikz-demo project — covers construction design, available DSL ops, anti-patterns, and the render-verify-commit workflow
---

# Geometry Recipe Maker

## Overview

A recipe is a named, reusable geometry construction stored as a YAML file in `recipe/recipes/genexam/<name>.yaml`. It has a stable `setup` (anchor objects) and an `example.construction` (derived objects). New recipes always go in the `genexam` catalog.

## Workflow

1. **Design `setup`** — choose stable anchor objects (points, circles, triangles, rectangles)
2. **Design `construction`** — derived objects that build on the setup
3. **Write the YAML** (see structure below)
4. **Render**: `source .venv/bin/activate && python docs/render_recipe.py <name>`
5. **Review** `/tmp/<name>.svg` visually in a browser — Do NOT skip this step
6. **Iterate** — fix the YAML and re-render until the diagram is correct
7. **Commit** only after visual review passes

## Recipe YAML Structure

```yaml
name: <snake_case_name>
description: "<one-line description>"
tags: [keyword, ...]
context: "Given a <geometric scenario>."
setup:                       # stable anchor objects only
  - op: point
    id: O
    coords: [0, 0]
  - op: circle
    id: c
    center: O
    radius: 3
example:
  mode: abstract             # or grid
  construction:
    - op: rotation
      id: A
      point: {coords: [3, 0]}
      center: O
      angle: 0
  annotations:
    auto_draw_all: true
    auto_label_points: true
    marks: []                # optional
notes:
  - "Key constraint or gotcha."
```

## DSL Op Reference

Read `recipe/dsl.py` for available ops and their parameters. The op name in YAML is the `op:` field value; each op class in `dsl.py` shows required and optional fields.

Existing recipes in `recipe/recipes/` are the best source of working examples — search for a recipe that uses an op similar to what you need.

## Critical Anti-Patterns

**Circular dependency in `setup`.**
`setup` must contain only stable anchor objects. Never reference a `construction` point inside `setup` — the lowering pipeline resolves `setup` first.

**Eyeballed crossing-point coords.**
Any point where two paths cross must be found via `line_through (visible: false)` + `intersection`, then drawn with explicit `segment` ops:
```yaml
- op: line_through
  id: l1
  points: [A, B]
  visible: false
- op: intersection
  id: P
  of: [l1, l2]
- op: segment
  id: seg_AP
  endpoints: [A, P]     # segment, not the full line
```

**`mark_angle` with collinear points.**
If D is on the extension of CB past B, then C, B, D are collinear — angle CBD = 180°.
Use a non-collinear point: `mark_angle(a=A, vertex=B, b=D)`, NOT `a=C`.

**Circle-boundary points via `point_on_segment`.**
`point_on_segment` places a point on a *line segment*, not on a circle arc. Use `rotation` for circle-boundary points.

**`mark_parallel` wrong direction.**
`[A,B]` is parallel to `[D,C]` (same traversal direction), not `[C,D]` (antiparallel → wrong tick orientation).

**`polygon_from_angles_and_sides` vertex order.**
Vertices must be in consecutive perimeter order (A→B→C→D→A). A crossed order (e.g. A,B,D,C) produces a self-intersecting bowtie, not a polygon.

# Elliptical Arcs/Sectors + Open Polylines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add elliptical arc/sector primitives (polymorphic through the existing `arc()`/`sector()` functions) and an open-polyline primitive to the pydsl geometry pipeline, closing the two gaps identified in the Tier 2 domain-scoping pass.

**Architecture:** Two independent features sharing renderer files. Each follows the existing IR → `to_sympy.py` compile → `render_util.py` math → `to_tikz.py`/`to_svg.py` render → pydsl wrapper pipeline, additive-only alongside the existing circular `Arc`/`Sector`/`Polygon` code paths (never modifying them).

**Tech Stack:** Python, Pydantic (IR schema), SymPy (`sympy.geometry`), TikZ/`tkz-euclide`, raw SVG via `xml.etree.ElementTree`.

**Full spec:** `docs/superpowers/specs/2026-08-06-pydsl-elliptical-arcs-and-polylines-design.md` (already committed, Fable-reviewed). This plan's task steps use that spec's already-fixed code verbatim.

## Global Constraints

- Additive-only: do not modify existing `Arc`, `Sector`, `ArcCenterStartEnd`, `SectorCenterStartEnd`, `arc_params()`, or any existing circular-arc code path. New `EllipticalArc*` classes/functions live in parallel.
- `arc()`/`sector()`'s first parameter is renamed from `circle` to `shape` (verified safe: no external caller uses the `circle=` keyword form outside unrelated `TangentLineOp`/`LineTangent` kwargs).
- The elliptical-arc angle-recovery formula is `atan2((y-cy)/vradius, (x-cx)/hradius)` — NOT plain `atan2(y-cy, x-cx)`. This is the load-bearing correctness fix; the required test assertion is the exact worked example: `hradius=4, vradius=1`, point at `t=60°` is `(2.0, 0.8660)`; the correct formula recovers `60.0°`; plain `atan2` gives `23.413°` (~36.6° error); feeding the wrong angle back into the parametric form lands at `(3.671, 0.397)`, nowhere near the original point.
- `PolylineOpen`'s open-ness is a rendering-time-only property (no `-- cycle` in TikZ, native `<polyline>` in SVG, no wraparound in `drawn_segments`) — the compiled representation is a plain Python list of SymPy points, not a SymPy geometry object (SymPy has no open-multi-point-path type).
- `polyline()` rejects only **consecutive** coincident points (unlike `polygon()`, which also checks wraparound first↔last). `polyline(A, B, A)` is a valid, if visually degenerate (retraced), polyline.
- No changes to `Sector`'s own absence from `expand_bounds_for_geometry` — that's a pre-existing, out-of-scope gap; only the new `EllipticalArc` branch is added.
- Run `.venv/bin/python -m pytest tests/` after every task; all tests must pass before committing.

---

### Task 1: IR schema — elliptical arc/sector def statements

**Files:**
- Modify: `geometry_diagrams/ir/ir.py` (near `ArcCenterStartEnd`/`SectorCenterStartEnd`, lines ~315-350, and the `DefStmt` union at lines ~537-551)
- Test: `tests/test_ir.py` (or wherever `DefStmt` discriminated-union parsing is tested — search for `ArcCenterStartEnd` in `tests/` first; add alongside it)

**Interfaces:**
- Produces: `EllipticalArcCenterStartEnd(DefBase)` and `EllipticalSectorCenterStartEnd(DefBase)` classes, each with fields `center: PointId`, `hradius: Union[int, float, str]`, `vradius: Union[int, float, str]`, `start: PointId`, `end: PointId`, `reflex: bool = False`, and `kind: Literal["elliptical_arc_center_start_end"] = "..."` / `kind: Literal["elliptical_sector_center_start_end"] = "..."` respectively. Both added to the `DefStmt` discriminated union.

The existing `ArcCenterStartEnd`/`SectorCenterStartEnd` look like this (read-only reference, do not modify):

```python
class ArcCenterStartEnd(DefBase):
    kind: Literal["arc_center_start_end"] = "arc_center_start_end"
    center: PointId
    start: PointId
    end: PointId
    reflex: bool = False


class SectorCenterStartEnd(DefBase):
    kind: Literal["sector_center_start_end"] = "sector_center_start_end"
    center: PointId
    start: PointId
    end: PointId
    reflex: bool = False
```

- [ ] **Step 1: Write the failing test**

Add to the test file that already exercises `DefStmt`/`ArcCenterStartEnd` parsing (find it via `grep -rn "ArcCenterStartEnd" tests/`):

```python
def test_elliptical_arc_center_start_end_round_trips():
    from geometry_diagrams.ir.ir import EllipticalArcCenterStartEnd, DiagramIR

    stmt = EllipticalArcCenterStartEnd(
        id="ea1", center="c", hradius=4, vradius=1, start="s", end="e", reflex=False,
    )
    assert stmt.kind == "elliptical_arc_center_start_end"
    assert stmt.hradius == 4 and stmt.vradius == 1


def test_elliptical_sector_center_start_end_round_trips():
    from geometry_diagrams.ir.ir import EllipticalSectorCenterStartEnd

    stmt = EllipticalSectorCenterStartEnd(
        id="es1", center="c", hradius=4, vradius=1, start="s", end="e", reflex=True,
    )
    assert stmt.kind == "elliptical_sector_center_start_end"
    assert stmt.reflex is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ir.py -k elliptical -v` (adjust filename to wherever you added the test)
Expected: FAIL with `ImportError: cannot import name 'EllipticalArcCenterStartEnd'`

- [ ] **Step 3: Add the two new classes and register them in `DefStmt`**

Add directly after `SectorCenterStartEnd` in `geometry_diagrams/ir/ir.py`:

```python
class EllipticalArcCenterStartEnd(DefBase):
    """Elliptical arc: the boundary curve of an axis-aligned ellipse between
    start and end. Mirrors ArcCenterStartEnd but for a non-uniform-radius
    ellipse — hradius/vradius replace the single implicit radius."""
    kind: Literal["elliptical_arc_center_start_end"] = "elliptical_arc_center_start_end"
    center: PointId
    hradius: Union[int, float, str]
    vradius: Union[int, float, str]
    start: PointId
    end: PointId
    reflex: bool = False


class EllipticalSectorCenterStartEnd(DefBase):
    """Elliptical sector: the closed pie-slice region of an axis-aligned
    ellipse bounded by the two radii to start/end and the arc between them.
    Mirrors SectorCenterStartEnd."""
    kind: Literal["elliptical_sector_center_start_end"] = "elliptical_sector_center_start_end"
    center: PointId
    hradius: Union[int, float, str]
    vradius: Union[int, float, str]
    start: PointId
    end: PointId
    reflex: bool = False
```

Then update the `DefStmt` union (currently):

```python
DefStmt = Annotated[
    Union[
        PointFixed, PointFree, PointOn, PointMidpoint, PointFoot, PointBetween, PointRotate, PointReflect, PointDilate,
        PointTriangleCenter, PointIntersection, PointAlias,
        Segment, Ray,
        LineThrough, LineParallelThrough, LinePerpendicularThrough,
        LineAngleBisector, LineTangent,
        CircleCenterPoint, CircleCenterRadius, CircleThrough3,
        ArcCenterStartEnd,
        SectorCenterStartEnd,
        EllipseCenterAxes, EllipseBBox, EllipseFoci, EllipseCenterEccentricity,
        Triangle, Polygon, PolygonExterior, PolygonOnEdge,
    ],
    Field(discriminator="kind")
]
```

to (add the two new classes right after `SectorCenterStartEnd`):

```python
DefStmt = Annotated[
    Union[
        PointFixed, PointFree, PointOn, PointMidpoint, PointFoot, PointBetween, PointRotate, PointReflect, PointDilate,
        PointTriangleCenter, PointIntersection, PointAlias,
        Segment, Ray,
        LineThrough, LineParallelThrough, LinePerpendicularThrough,
        LineAngleBisector, LineTangent,
        CircleCenterPoint, CircleCenterRadius, CircleThrough3,
        ArcCenterStartEnd,
        SectorCenterStartEnd,
        EllipticalArcCenterStartEnd,
        EllipticalSectorCenterStartEnd,
        EllipseCenterAxes, EllipseBBox, EllipseFoci, EllipseCenterEccentricity,
        Triangle, Polygon, PolygonExterior, PolygonOnEdge,
    ],
    Field(discriminator="kind")
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ir.py -k elliptical -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass (no other file references `DefStmt`'s member list exhaustively; this is a pure addition)

```bash
git add geometry_diagrams/ir/ir.py tests/test_ir.py
git commit -m "feat: add EllipticalArcCenterStartEnd/EllipticalSectorCenterStartEnd IR classes"
```

---

### Task 2: to_sympy.py — compile elliptical arc/sector def statements

**Files:**
- Modify: `geometry_diagrams/ir/to_sympy.py` (near the existing `Arc`/`Sector` marker classes at the top of the file, and near the `ArcCenterStartEnd`/`SectorCenterStartEnd`/`EllipseCenterAxes` compile cases around lines 443-460)
- Test: `tests/test_to_sympy.py` (search `grep -rn "ArcCenterStartEnd\|compile_defs" tests/test_to_sympy.py` for the existing pattern to mirror)

**Interfaces:**
- Consumes: `EllipticalArcCenterStartEnd`/`EllipticalSectorCenterStartEnd` from Task 1.
- Produces: `EllipticalArc`/`EllipticalSector` marker classes (module-level in `to_sympy.py`, each with `__slots__ = ("center", "start", "end", "hradius", "vradius", "reflex")`) — Tasks 3-5 (`render_util.py`, `to_tikz.py`, `to_svg.py`) import and `isinstance()`-check these exact classes, so their names and slot names must match verbatim.

Existing marker classes to mirror (module-level, top of `to_sympy.py`):

```python
class Arc:
    __slots__ = ("center", "start", "end", "radius", "reflex")

    def __init__(self, center, start, end, radius, reflex):
        self.center = center
        self.start = start
        self.end = end
        self.radius = radius
        self.reflex = reflex

    def __repr__(self):
        return f"Arc(center={self.center}, start={self.start}, end={self.end}, radius={self.radius}, reflex={self.reflex})"


class Sector:
    __slots__ = ("center", "start", "end", "radius", "reflex")

    def __init__(self, center, start, end, radius, reflex):
        self.center = center
        self.start = start
        self.end = end
        self.radius = radius
        self.reflex = reflex

    def __repr__(self):
        return f"Sector(center={self.center}, start={self.start}, end={self.end}, radius={self.radius}, reflex={self.reflex})"
```

Existing `ArcCenterStartEnd`/`SectorCenterStartEnd` compile cases (read-only reference — do not modify):

```python
case ir.ArcCenterStartEnd(center=center_id, start=start_id, end=end_id, reflex=reflex):
    c, s, e = ref(center_id), ref(start_id), ref(end_id)
    r = c.distance(s)
    return Arc(center=c, start=s, end=e, radius=r, reflex=reflex)

case ir.SectorCenterStartEnd(center=center_id, start=start_id, end=end_id, reflex=reflex):
    c, s, e = ref(center_id), ref(start_id), ref(end_id)
    r = c.distance(s)
    return Sector(center=c, start=s, end=e, radius=r, reflex=reflex)
```

`EllipseCenterAxes`'s existing validation pattern to mirror exactly (read-only reference):

```python
case ir.EllipseCenterAxes(center=center_id, hradius=hradius, vradius=vradius):
    hr, vr = ev(hradius), ev(vradius)
    if float(hr.evalf()) <= 0 or float(vr.evalf()) <= 0:
        raise IRCompileError(did, f"ellipse_center_axes: hradius and vradius must be positive, got {hr}, {vr}")
    return spg.Ellipse(ref(center_id), hr, vr)
```

`ev()` is a nested closure already in scope inside `compile_defs` wherever the match-case body lives (`def ev(raw: int | float | str) -> sp.Basic:`); `did = stmt.id` is likewise already in scope. No new imports are needed for either.

- [ ] **Step 1: Write the failing test**

```python
def test_elliptical_arc_compiles_to_marker_with_positive_radii():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.to_sympy import compile_defs, EllipticalArc

    defs = [
        ir.PointFixed(id="c", x=0, y=0),
        ir.PointFixed(id="s", x=4, y=0),
        ir.PointFixed(id="e", x=0, y=1),
        ir.EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=4, vradius=1, start="s", end="e"),
    ]
    sym = compile_defs(defs)
    obj = sym["ea1"]
    assert isinstance(obj, EllipticalArc)
    assert float(obj.hradius) == 4.0
    assert float(obj.vradius) == 1.0


def test_elliptical_arc_rejects_non_positive_hradius():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.errors import IRCompileError

    defs = [
        ir.PointFixed(id="c", x=0, y=0),
        ir.PointFixed(id="s", x=4, y=0),
        ir.PointFixed(id="e", x=0, y=1),
        ir.EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=0, vradius=1, start="s", end="e"),
    ]
    with pytest.raises(IRCompileError, match="hradius and vradius must be positive"):
        compile_defs(defs)


def test_elliptical_sector_compiles_to_marker():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.to_sympy import compile_defs, EllipticalSector

    defs = [
        ir.PointFixed(id="c", x=0, y=0),
        ir.PointFixed(id="s", x=4, y=0),
        ir.PointFixed(id="e", x=0, y=1),
        ir.EllipticalSectorCenterStartEnd(id="es1", center="c", hradius=4, vradius=1, start="s", end="e", reflex=True),
    ]
    sym = compile_defs(defs)
    obj = sym["es1"]
    assert isinstance(obj, EllipticalSector)
    assert obj.reflex is True
```

(Add `import pytest` at the top of the test file if not already present. Check the existing `compile_defs` call signature in `tests/test_to_sympy.py` first — some existing tests may wrap `defs` in a `DiagramIR`/pass a `Canvas`; match whatever the existing `ArcCenterStartEnd` compile test does exactly.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_to_sympy.py -k elliptical -v`
Expected: FAIL with `ImportError: cannot import name 'EllipticalArc'`

- [ ] **Step 3: Add marker classes and compile cases**

Add directly after the existing `Sector` marker class in `to_sympy.py`:

```python
class EllipticalArc:
    __slots__ = ("center", "start", "end", "hradius", "vradius", "reflex")

    def __init__(self, center, start, end, hradius, vradius, reflex):
        self.center = center
        self.start = start
        self.end = end
        self.hradius = hradius
        self.vradius = vradius
        self.reflex = reflex

    def __repr__(self):
        return (
            f"EllipticalArc(center={self.center}, start={self.start}, end={self.end}, "
            f"hradius={self.hradius}, vradius={self.vradius}, reflex={self.reflex})"
        )


class EllipticalSector:
    __slots__ = ("center", "start", "end", "hradius", "vradius", "reflex")

    def __init__(self, center, start, end, hradius, vradius, reflex):
        self.center = center
        self.start = start
        self.end = end
        self.hradius = hradius
        self.vradius = vradius
        self.reflex = reflex

    def __repr__(self):
        return (
            f"EllipticalSector(center={self.center}, start={self.start}, end={self.end}, "
            f"hradius={self.hradius}, vradius={self.vradius}, reflex={self.reflex})"
        )
```

Add directly after the existing `SectorCenterStartEnd` compile case, in the `match stmt:` body inside `compile_defs`:

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

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_to_sympy.py -k elliptical -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/ir/to_sympy.py tests/test_to_sympy.py
git commit -m "feat: compile elliptical arc/sector def statements to EllipticalArc/EllipticalSector markers"
```

---

### Task 3: render_util.py — elliptical_arc_params() and bounds-expansion

**Files:**
- Modify: `geometry_diagrams/ir/render_util.py` (add `elliptical_arc_params()` near `arc_params()` at line ~168; add a branch to `expand_bounds_for_geometry()` at line ~208)
- Test: `tests/test_render_util.py`

**Interfaces:**
- Consumes: `EllipticalArc`/`EllipticalSector` from Task 2 (import from `.to_sympy`).
- Produces: `elliptical_arc_params(obj_id: str, sym: SymTable) -> tuple[float, float, float, float, float, float, float, float]` returning `(cx, cy, hr, vr, s_deg, e_deg, sx, sy)` — Tasks 4-5 (`to_tikz.py`, `to_svg.py`) call this exact function with this exact return-tuple shape and order.

This is the single most correctness-critical function in the whole feature — the load-bearing fix is using `atan2((y-cy)/vr, (x-cx)/hr)` instead of plain `atan2(y-cy, x-cx)` to recover the parametric angle `t` on a non-uniform ellipse (plain atan2 is only correct when `hr == vr`, i.e. a circle).

Existing `arc_params()` (read-only reference — copy its exact minor/reflex-swap and normalization logic verbatim, generalizing only the angle-recovery formula):

```python
def arc_params(obj_id: str, sym: SymTable) -> tuple[float, float, float, float, float, float, float]:
    """Return (cx, cy, r, start_deg, end_deg, sx, sy) for an Arc/Sector marker.

    start_deg/end_deg are normalized so end_deg > start_deg (sweep is always
    the positive-degree direction), honoring the marker's `reflex` flag to
    pick which of the two possible arcs (minor vs. major) to report.
    """
    obj = sym[obj_id]
    cx = sympy_to_float(obj.center.x)
    cy = sympy_to_float(obj.center.y)
    sx = sympy_to_float(obj.start.x)
    sy = sympy_to_float(obj.start.y)
    ex = sympy_to_float(obj.end.x)
    ey = sympy_to_float(obj.end.y)
    r = math.hypot(sx - cx, sy - cy)

    s_deg = math.degrees(math.atan2(sy - cy, sx - cx))
    e_deg = math.degrees(math.atan2(ey - cy, ex - cx))

    # Normalize into [0, 360) then figure out which sweep direction is the
    # "minor" (<=180°) one, and swap if the marker wants the reflex (major) arc.
    s_deg %= 360.0
    e_deg %= 360.0
    is_ccw_minor = (e_deg - s_deg) % 360.0 <= 180.0
    want_reflex = obj.reflex
    if is_ccw_minor == want_reflex:
        s_deg, e_deg = e_deg, s_deg
        sx, sy = ex, ey

    if e_deg <= s_deg:
        e_deg += 360.0

    return cx, cy, r, s_deg, e_deg, sx, sy
```

`expand_bounds_for_geometry()`'s existing structure (read-only reference — the `Arc` branch is the template; there is currently no `Sector` branch at all, which is a pre-existing gap this task does NOT fix):

```python
def expand_bounds_for_geometry(obj, bounds: list[float]) -> None:
    """Expand bounds in-place to include obj's extent, conservatively."""
    xmin, ymin, xmax, ymax = bounds
    if isinstance(obj, spg.Ellipse):  # also covers Circle (a degenerate Ellipse subtype)
        cx = sympy_to_float(obj.center.x)
        cy = sympy_to_float(obj.center.y)
        try:
            hr = sympy_to_float(obj.hradius)
            vr = sympy_to_float(obj.vradius)
        except (AttributeError, TypeError):
            hr = vr = sympy_to_float(obj.radius)
        bounds[0] = min(xmin, cx - hr)
        bounds[1] = min(ymin, cy - vr)
        bounds[2] = max(xmax, cx + hr)
        bounds[3] = max(ymax, cy + vr)
    elif isinstance(obj, Arc):
        cx = sympy_to_float(obj.center.x)
        cy = sympy_to_float(obj.center.y)
        r = sympy_to_float(obj.radius)
        # Conservatively use full enclosing circle
        bounds[0] = min(xmin, cx - r)
        bounds[1] = min(ymin, cy - r)
        bounds[2] = max(xmax, cx + r)
        bounds[3] = max(ymax, cy + r)
    # ... other branches for other geometry types ...
```

(Read the actual current file before editing — the snippet above reproduces the shape of the function; match indentation and any other branches present exactly rather than overwriting them.)

- [ ] **Step 1: Write the failing tests**

```python
def test_elliptical_arc_params_recovers_correct_angle_not_plain_atan2():
    """The exact Fable-verified worked example: hradius=4, vradius=1, t=60deg.

    Point on the ellipse at parametric angle t=60 degrees is
    (4*cos(60), 1*sin(60)) = (2.0, 0.8660...). The correct parametric-angle
    recovery formula atan2((y-cy)/vr, (x-cx)/hr) gives back 60.0 degrees.
    Plain atan2(y-cy, x-cx) gives 23.413 degrees -- a ~36.6 degree error --
    and feeding that wrong angle back into the parametric form
    (cx + hr*cos(t), cy + vr*sin(t)) lands at (3.671, 0.397), nowhere near
    the original point.
    """
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.render_util import elliptical_arc_params
    import math

    t = math.radians(60.0)
    hr, vr = 4.0, 1.0
    sx, sy = hr * math.cos(t), vr * math.sin(t)
    assert sx == pytest.approx(2.0, abs=1e-3)
    assert sy == pytest.approx(0.8660, abs=1e-3)

    defs = [
        ir.PointFixed(id="c", x=0, y=0),
        ir.PointFixed(id="s", x=sx, y=sy),
        ir.PointFixed(id="e", x=0, y=vr),  # t=90deg
        ir.EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=hr, vradius=vr, start="s", end="e"),
    ]
    sym = compile_defs(defs)
    cx, cy, hr_out, vr_out, s_deg, e_deg, sx_out, sy_out = elliptical_arc_params("ea1", sym)

    # Correct formula recovers the true start angle:
    assert s_deg == pytest.approx(60.0, abs=0.01)

    # Sanity: the WRONG plain-atan2 formula would have given ~23.413 degrees,
    # a completely different and incorrect angle -- assert the two disagree
    # by roughly the expected error margin, pinning the bug this fixes.
    wrong_deg = math.degrees(math.atan2(sy_out - cy, sx_out - cx)) % 360.0
    assert wrong_deg == pytest.approx(23.413, abs=0.01)
    assert abs(s_deg - wrong_deg) == pytest.approx(36.587, abs=0.01)


def test_expand_bounds_for_geometry_includes_elliptical_arc():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.render_util import expand_bounds_for_geometry

    defs = [
        ir.PointFixed(id="c", x=0, y=0),
        ir.PointFixed(id="s", x=4, y=0),
        ir.PointFixed(id="e", x=0, y=1),
        ir.EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=4, vradius=1, start="s", end="e"),
    ]
    sym = compile_defs(defs)
    bounds = [0.0, 0.0, 0.0, 0.0]
    expand_bounds_for_geometry(sym["ea1"], bounds)
    assert bounds == [-4.0, -1.0, 4.0, 1.0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_render_util.py -k elliptical -v`
Expected: FAIL with `ImportError: cannot import name 'elliptical_arc_params'`

- [ ] **Step 3: Implement `elliptical_arc_params()` and the bounds-expansion branch**

Add directly after `arc_params()` in `render_util.py` (import `EllipticalArc` alongside the existing `Arc`/`Sector` import at the top of the file if not already imported — check the current `from .to_sympy import ...` line):

```python
def elliptical_arc_params(obj_id: str, sym: SymTable) -> tuple[float, float, float, float, float, float, float, float]:
    """Return (cx, cy, hr, vr, start_deg, end_deg, sx, sy) for an
    EllipticalArc/EllipticalSector marker.

    Mirrors arc_params() exactly, except recovering the parametric angle t
    via atan2((y-cy)/vr, (x-cx)/hr) instead of plain atan2(y-cy, x-cx) --
    the plain formula is only correct when hr == vr (a circle); for a true
    ellipse it recovers the wrong angle, silently corrupting the rendered
    endpoint.
    """
    obj = sym[obj_id]
    cx = sympy_to_float(obj.center.x)
    cy = sympy_to_float(obj.center.y)
    hr = sympy_to_float(obj.hradius)
    vr = sympy_to_float(obj.vradius)
    sx = sympy_to_float(obj.start.x)
    sy = sympy_to_float(obj.start.y)
    ex = sympy_to_float(obj.end.x)
    ey = sympy_to_float(obj.end.y)

    s_deg = math.degrees(math.atan2((sy - cy) / vr, (sx - cx) / hr))
    e_deg = math.degrees(math.atan2((ey - cy) / vr, (ex - cx) / hr))

    s_deg %= 360.0
    e_deg %= 360.0
    is_ccw_minor = (e_deg - s_deg) % 360.0 <= 180.0
    want_reflex = obj.reflex
    if is_ccw_minor == want_reflex:
        s_deg, e_deg = e_deg, s_deg
        sx, sy = ex, ey

    if e_deg <= s_deg:
        e_deg += 360.0

    return cx, cy, hr, vr, s_deg, e_deg, sx, sy
```

Add a new branch to `expand_bounds_for_geometry()`, directly after the existing `Arc` branch:

```python
    elif isinstance(obj, EllipticalArc):
        cx = sympy_to_float(obj.center.x)
        cy = sympy_to_float(obj.center.y)
        hr = sympy_to_float(obj.hradius)
        vr = sympy_to_float(obj.vradius)
        # Conservatively use the full enclosing ellipse
        bounds[0] = min(xmin, cx - hr)
        bounds[1] = min(ymin, cy - vr)
        bounds[2] = max(xmax, cx + hr)
        bounds[3] = max(ymax, cy + vr)
```

(`EllipticalSector` is deliberately NOT added here — `Sector` itself has no branch in this function today, a pre-existing gap out of this plan's scope; matching that asymmetry, not fixing it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_render_util.py -k elliptical -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/ir/render_util.py tests/test_render_util.py
git commit -m "feat: add elliptical_arc_params() with correct parametric-angle recovery"
```

---

### Task 4: to_tikz.py — render elliptical arcs/sectors

**Files:**
- Modify: `geometry_diagrams/ir/to_tikz.py` (import line ~12; `_obj_to_tikz_path()` at lines ~160-191; `_emit_op()`'s `ir.Draw`/`ir.Fill` match-case body at lines ~211-334)
- Test: `tests/test_to_tikz.py`

**Interfaces:**
- Consumes: `EllipticalArc`/`EllipticalSector` (Task 2), `elliptical_arc_params()` (Task 3).

Update the import line (currently):

```python
from .to_sympy import Arc, Sector, SymTable
```

to:

```python
from .to_sympy import Arc, EllipticalArc, EllipticalSector, Sector, SymTable
```

and add `elliptical_arc_params` to the existing `from .render_util import (...)` block.

Existing TikZ `Sector` Draw/Fill branches and the `Ellipse` branch (read-only reference — TikZ already supports independent `x radius=`/`y radius=`, confirming no new drawing primitive is needed):

```python
# Draw, existing Ellipse branch:
elif isinstance(sym_obj, spg.Ellipse):
    cx, cy, a, b = ellipse_params(obj_id, sym)
    style_inner = sopts[1:-1] if sopts else ""  # strip surrounding []
    out.append(f"\\draw[{style_inner}] ({fmt_num(cx)},{fmt_num(cy)}) ellipse[x radius={fmt_num(a)},y radius={fmt_num(b)}]")

# Draw, existing Sector branch (raw \draw, NOT \tkzDraw*):
# (locate via `grep -n "isinstance(sym_obj, Sector)" geometry_diagrams/ir/to_tikz.py`
#  in the Draw case; mirrors the Fill-case Sector branch shown below but with
#  fill:none / no fill color)
```

`_obj_to_tikz_path()`'s existing `Sector` branch (read-only reference — the exact template for the new `EllipticalSector` branch):

```python
if isinstance(sym_obj, Sector):
    cx, cy, r, start_deg, end_deg, sx, sy = arc_params(obj_id, sym)
    return (
        f"({fmt_num(cx)},{fmt_num(cy)}) -- "
        f"({fmt_num(sx)},{fmt_num(sy)}) "
        f"arc[start angle={fmt_num(start_deg)},"
        f"end angle={fmt_num(end_deg)},radius={fmt_num(r)}] -- cycle"
    )
return None
```

- [ ] **Step 1: Write the failing tests**

```python
def test_to_tikz_renders_elliptical_arc_with_distinct_radii():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.ir import DiagramIR, Canvas
    from geometry_diagrams.ir.to_tikz import compile_to_tikz  # match actual entry point name; grep for it if different

    diagram = DiagramIR(
        canvas=Canvas(x_range=(-5, 5), y_range=(-5, 5)),
        defs=[
            ir.PointFixed(id="c", x=0, y=0),
            ir.PointFixed(id="s", x=4, y=0),
            ir.PointFixed(id="e", x=0, y=1),
            ir.EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=4, vradius=1, start="s", end="e"),
        ],
        render=[ir.Draw(obj="ea1")],
    )
    tikz = compile_to_tikz(diagram)
    assert "x radius=4" in tikz
    assert "y radius=1" in tikz


def test_to_tikz_renders_elliptical_sector_fill_with_holes_subpath():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.ir import DiagramIR, Canvas
    from geometry_diagrams.ir.to_tikz import compile_to_tikz

    diagram = DiagramIR(
        canvas=Canvas(x_range=(-5, 5), y_range=(-5, 5)),
        defs=[
            ir.PointFixed(id="c", x=0, y=0),
            ir.PointFixed(id="s", x=4, y=0),
            ir.PointFixed(id="e", x=0, y=1),
            ir.EllipticalSectorCenterStartEnd(id="es1", center="c", hradius=4, vradius=1, start="s", end="e"),
            ir.PointFixed(id="c2", x=0, y=0),
            ir.PointFixed(id="s2", x=2, y=0),
            ir.PointFixed(id="e2", x=0, y=0.5),
            ir.EllipticalSectorCenterStartEnd(id="es2", center="c2", hradius=2, vradius=0.5, start="s2", end="e2"),
        ],
        render=[ir.Fill(obj="es1", holes=["es2"])],
    )
    tikz = compile_to_tikz(diagram)
    assert "arc[start angle=" in tikz
    assert "even odd rule" in tikz or "evenodd" in tikz.lower()
```

(First check the actual public entry point name in `to_tikz.py` — search `grep -n "^def " geometry_diagrams/ir/to_tikz.py | head` — and adjust the import/call above to match; the existing tests in `tests/test_to_tikz.py` already show the correct call pattern for building a `DiagramIR` and rendering it. Mirror whatever fixture/helper pattern the file's existing Sector-Fill test already uses instead of hand-building `DiagramIR` if one exists.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_to_tikz.py -k elliptical -v`
Expected: FAIL (either `AttributeError` on the Draw/Fill dispatch falling through with no matching `elif`, or an assertion failure because `x radius=` never appears)

- [ ] **Step 3: Add the renderer branches**

In `_obj_to_tikz_path()`, add directly after the existing `Sector` branch, before `return None`:

```python
    if isinstance(sym_obj, EllipticalSector):
        cx, cy, hr, vr, start_deg, end_deg, sx, sy = elliptical_arc_params(obj_id, sym)
        return (
            f"({fmt_num(cx)},{fmt_num(cy)}) -- "
            f"({fmt_num(sx)},{fmt_num(sy)}) "
            f"arc[start angle={fmt_num(start_deg)},"
            f"end angle={fmt_num(end_deg)},x radius={fmt_num(hr)},y radius={fmt_num(vr)}] -- cycle"
        )
```

In `_emit_op()`'s `ir.Draw` case, add directly after the existing `Sector` `elif` branch (find it via `grep -n "isinstance(sym_obj, Sector)" geometry_diagrams/ir/to_tikz.py`, use its exact raw-`\draw`-string structure as the template, generalizing `radius=` to `x radius=`/`y radius=`):

```python
            elif isinstance(sym_obj, EllipticalArc):
                cx, cy, hr, vr, start_deg, end_deg, sx, sy = elliptical_arc_params(obj_id, sym)
                style_inner = sopts[1:-1] if sopts else ""
                out.append(
                    f"\\draw[{style_inner}] ({fmt_num(sx)},{fmt_num(sy)}) "
                    f"arc[start angle={fmt_num(start_deg)},end angle={fmt_num(end_deg)},"
                    f"x radius={fmt_num(hr)},y radius={fmt_num(vr)}]"
                )
            elif isinstance(sym_obj, EllipticalSector):
                cx, cy, hr, vr, start_deg, end_deg, sx, sy = elliptical_arc_params(obj_id, sym)
                style_inner = sopts[1:-1] if sopts else ""
                out.append(
                    f"\\draw[{style_inner}] ({fmt_num(cx)},{fmt_num(cy)}) -- "
                    f"({fmt_num(sx)},{fmt_num(sy)}) "
                    f"arc[start angle={fmt_num(start_deg)},end angle={fmt_num(end_deg)},"
                    f"x radius={fmt_num(hr)},y radius={fmt_num(vr)}] -- cycle"
                )
```

In `_emit_op()`'s `ir.Fill` case, add directly after the existing non-holes `Sector` `elif` branch (find via `grep -n "isinstance(sym_obj, Sector)" geometry_diagrams/ir/to_tikz.py` — the second match, inside the Fill case; use its exact `\fill[...]` structure as the template):

```python
            elif isinstance(sym_obj, EllipticalSector):
                cx, cy, hr, vr, start_deg, end_deg, sx, sy = elliptical_arc_params(obj_id, sym)
                out.append(
                    f"\\fill[{fill_opts}] ({fmt_num(cx)},{fmt_num(cy)}) -- "
                    f"({fmt_num(sx)},{fmt_num(sy)}) "
                    f"arc[start angle={fmt_num(start_deg)},end angle={fmt_num(end_deg)},"
                    f"x radius={fmt_num(hr)},y radius={fmt_num(vr)}] -- cycle"
                )
```

(`fill_opts`/the exact fill-options variable name must match whatever the existing `Sector` Fill branch already uses in this file — read that branch's exact code before writing this one; do not invent a new variable name.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_to_tikz.py -k elliptical -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/ir/to_tikz.py tests/test_to_tikz.py
git commit -m "feat: render elliptical arcs/sectors in to_tikz.py"
```

---

### Task 5: to_svg.py — render elliptical arcs/sectors

**Files:**
- Modify: `geometry_diagrams/ir/to_svg.py` (import line ~29; `ir.Draw`'s `Arc`/`Sector` branches at lines ~498-549; `ir.Fill`'s `Sector` branch at lines ~645+; `_obj_to_svg_subpath()`'s `Sector` branch at line ~1859)
- Test: `tests/test_to_svg.py`

**Interfaces:**
- Consumes: `EllipticalArc`/`EllipticalSector` (Task 2), `elliptical_arc_params()` (Task 3).

Update the import line (currently):

```python
from .to_sympy import Arc, Sector, SymTable
```

to:

```python
from .to_sympy import Arc, EllipticalArc, EllipticalSector, Sector, SymTable
```

and add `elliptical_arc_params` to the existing `from .render_util import (...)` block.

Existing `Draw`-case `Arc`/`Sector` branches (read-only reference, exact current code — the single-radius formula `ex_g = cx_g + r_g*cos(end_rad)` generalizes to `hr_g`/`vr_g` for the elliptical version):

```python
elif isinstance(sym_obj, Arc):
    cx_g, cy_g, r_g, start_deg, end_deg, sx_g, sy_g = arc_params(obj_id, sym)
    r_s = r_g * scale
    end_rad = math.radians(end_deg)
    ex_g = cx_g + r_g * math.cos(end_rad)
    ey_g = cy_g + r_g * math.sin(end_rad)
    sx_s, sy_s = gxy(sx_g, sy_g)
    ex_s, ey_s = gxy(ex_g, ey_g)
    sweep_deg = end_deg - start_deg
    large_arc = 1 if sweep_deg > 180.0 else 0
    sweep_flag = 0
    d = (
        f"M {sx_s:.2f} {sy_s:.2f} "
        f"A {r_s:.2f} {r_s:.2f} 0 {large_arc} {sweep_flag} "
        f"{ex_s:.2f} {ey_s:.2f}"
    )
    ET.SubElement(svg, "path", {
        "data-ir-id": obj_id, "data-type": "arc", "d": d, "fill": "none", **attrs,
    })

elif isinstance(sym_obj, Sector):
    cx_g, cy_g, r_g, start_deg, end_deg, sx_g, sy_g = arc_params(obj_id, sym)
    r_s = r_g * scale
    end_rad = math.radians(end_deg)
    ex_g = cx_g + r_g * math.cos(end_rad)
    ey_g = cy_g + r_g * math.sin(end_rad)
    cx_s, cy_s = gxy(cx_g, cy_g)
    sx_s, sy_s = gxy(sx_g, sy_g)
    ex_s, ey_s = gxy(ex_g, ey_g)
    sweep_deg = end_deg - start_deg
    large_arc = 1 if sweep_deg > 180.0 else 0
    d = (
        f"M {cx_s:.2f} {cy_s:.2f} "
        f"L {sx_s:.2f} {sy_s:.2f} "
        f"A {r_s:.2f} {r_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} "
        f"L {cx_s:.2f} {cy_s:.2f}"
    )
    ET.SubElement(svg, "path", {
        "data-ir-id": obj_id, "data-type": "sector", "d": d, "fill": "none", **attrs,
    })
```

Existing `Fill`-case `Sector` branch (read-only reference — note it ends with `Z` instead of the retrace-to-center `L` used by Draw):

```python
elif isinstance(sym_obj, Sector):
    cx_g, cy_g, r_g, start_deg, end_deg, sx_g, sy_g = arc_params(obj_id, sym)
    r_s = r_g * scale
    end_rad = math.radians(end_deg)
    ex_g = cx_g + r_g * math.cos(end_rad)
    ey_g = cy_g + r_g * math.sin(end_rad)
    cx_s, cy_s = gxy(cx_g, cy_g)
    sx_s, sy_s = gxy(sx_g, sy_g)
    ex_s, ey_s = gxy(ex_g, ey_g)
    sweep_deg = end_deg - start_deg
    large_arc = 1 if sweep_deg > 180.0 else 0
    d = (
        f"M {cx_s:.2f} {cy_s:.2f} "
        f"L {sx_s:.2f} {sy_s:.2f} "
        f"A {r_s:.2f} {r_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} Z"
    )
    ET.SubElement(svg, "path", {
        "data-ir-id": obj_id, "data-role": "fill", "d": d,
        "fill": fill_color, "fill-opacity": str(fill_opacity), "stroke": "none",
    })
```

Existing `_obj_to_svg_subpath()`'s `Sector` branch (read-only reference — used by the holes-compound-fill path):

```python
if isinstance(sym_obj, Sector):
    cx_g, cy_g, r_g, start_deg, end_deg, sx_g, sy_g = arc_params(obj_id, sym)
    r_s = r_g * scale
    end_rad = math.radians(end_deg)
    ex_g = cx_g + r_g * math.cos(end_rad)
    ey_g = cy_g + r_g * math.sin(end_rad)
    cx_s, cy_s = gxy(cx_g, cy_g)
    sx_s, sy_s = gxy(sx_g, sy_g)
    ex_s, ey_s = gxy(ex_g, ey_g)
    sweep_deg = end_deg - start_deg
    large_arc = 1 if sweep_deg > 180.0 else 0
    return (
        f"M {cx_s:.2f} {cy_s:.2f} "
        f"L {sx_s:.2f} {sy_s:.2f} "
        f"A {r_s:.2f} {r_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} Z"
    )
```

`_obj_to_svg_subpath` is called with `ellipse_params_fn` as a positional parameter already — it will need `elliptical_arc_params` threaded through similarly. Check its call sites (`grep -n "_obj_to_svg_subpath(" geometry_diagrams/ir/to_svg.py`) and add an `elliptical_arc_params_fn` parameter, updating both call sites (outer shape and each hole, inside the `ir.Fill` `holes` branch).

- [ ] **Step 1: Write the failing tests**

```python
def test_to_svg_renders_elliptical_arc_path_with_correct_endpoint():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.ir import DiagramIR, Canvas
    from geometry_diagrams.ir.to_svg import compile_to_svg  # match actual entry point name; grep to confirm

    diagram = DiagramIR(
        canvas=Canvas(x_range=(-5, 5), y_range=(-5, 5)),
        defs=[
            ir.PointFixed(id="c", x=0, y=0),
            ir.PointFixed(id="s", x=4, y=0),
            ir.PointFixed(id="e", x=0, y=1),
            ir.EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=4, vradius=1, start="s", end="e"),
        ],
        render=[ir.Draw(obj="ea1")],
    )
    svg = compile_to_svg(diagram)
    assert 'data-type="arc"' in svg
    # A elliptical rx/ry pair must appear in the path's A command, distinct from each other
    import re
    m = re.search(r'A ([\d.]+) ([\d.]+) 0', svg)
    assert m is not None
    rx, ry = float(m.group(1)), float(m.group(2))
    assert rx != ry


def test_to_svg_renders_elliptical_sector_fill():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.ir import DiagramIR, Canvas
    from geometry_diagrams.ir.to_svg import compile_to_svg

    diagram = DiagramIR(
        canvas=Canvas(x_range=(-5, 5), y_range=(-5, 5)),
        defs=[
            ir.PointFixed(id="c", x=0, y=0),
            ir.PointFixed(id="s", x=4, y=0),
            ir.PointFixed(id="e", x=0, y=1),
            ir.EllipticalSectorCenterStartEnd(id="es1", center="c", hradius=4, vradius=1, start="s", end="e"),
        ],
        render=[ir.Fill(obj="es1", style="red")],
    )
    svg = compile_to_svg(diagram)
    assert 'data-role="fill"' in svg
```

(Confirm the actual entry-point function name and `Canvas`/`DiagramIR` construction pattern from `tests/test_to_svg.py`'s existing tests before writing these — mirror whatever the file's existing `Sector` Draw/Fill tests already do.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_to_svg.py -k elliptical -v`
Expected: FAIL

- [ ] **Step 3: Add the renderer branches**

In `ir.Draw`'s match body, add directly after the existing `Sector` `elif`:

```python
            elif isinstance(sym_obj, EllipticalArc):
                cx_g, cy_g, hr_g, vr_g, start_deg, end_deg, sx_g, sy_g = elliptical_arc_params(obj_id, sym)
                hr_s = hr_g * scale
                vr_s = vr_g * scale
                end_rad = math.radians(end_deg)
                ex_g = cx_g + hr_g * math.cos(end_rad)
                ey_g = cy_g + vr_g * math.sin(end_rad)
                sx_s, sy_s = gxy(sx_g, sy_g)
                ex_s, ey_s = gxy(ex_g, ey_g)
                sweep_deg = end_deg - start_deg
                large_arc = 1 if sweep_deg > 180.0 else 0
                sweep_flag = 0
                d = (
                    f"M {sx_s:.2f} {sy_s:.2f} "
                    f"A {hr_s:.2f} {vr_s:.2f} 0 {large_arc} {sweep_flag} "
                    f"{ex_s:.2f} {ey_s:.2f}"
                )
                ET.SubElement(svg, "path", {
                    "data-ir-id": obj_id, "data-type": "arc", "d": d, "fill": "none", **attrs,
                })

            elif isinstance(sym_obj, EllipticalSector):
                cx_g, cy_g, hr_g, vr_g, start_deg, end_deg, sx_g, sy_g = elliptical_arc_params(obj_id, sym)
                hr_s = hr_g * scale
                vr_s = vr_g * scale
                end_rad = math.radians(end_deg)
                ex_g = cx_g + hr_g * math.cos(end_rad)
                ey_g = cy_g + vr_g * math.sin(end_rad)
                cx_s, cy_s = gxy(cx_g, cy_g)
                sx_s, sy_s = gxy(sx_g, sy_g)
                ex_s, ey_s = gxy(ex_g, ey_g)
                sweep_deg = end_deg - start_deg
                large_arc = 1 if sweep_deg > 180.0 else 0
                d = (
                    f"M {cx_s:.2f} {cy_s:.2f} "
                    f"L {sx_s:.2f} {sy_s:.2f} "
                    f"A {hr_s:.2f} {vr_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} "
                    f"L {cx_s:.2f} {cy_s:.2f}"
                )
                ET.SubElement(svg, "path", {
                    "data-ir-id": obj_id, "data-type": "sector", "d": d, "fill": "none", **attrs,
                })
```

In `ir.Fill`'s non-holes branches, add directly after the existing `Sector` `elif`:

```python
            elif isinstance(sym_obj, EllipticalSector):
                cx_g, cy_g, hr_g, vr_g, start_deg, end_deg, sx_g, sy_g = elliptical_arc_params(obj_id, sym)
                hr_s = hr_g * scale
                vr_s = vr_g * scale
                end_rad = math.radians(end_deg)
                ex_g = cx_g + hr_g * math.cos(end_rad)
                ey_g = cy_g + vr_g * math.sin(end_rad)
                cx_s, cy_s = gxy(cx_g, cy_g)
                sx_s, sy_s = gxy(sx_g, sy_g)
                ex_s, ey_s = gxy(ex_g, ey_g)
                sweep_deg = end_deg - start_deg
                large_arc = 1 if sweep_deg > 180.0 else 0
                d = (
                    f"M {cx_s:.2f} {cy_s:.2f} "
                    f"L {sx_s:.2f} {sy_s:.2f} "
                    f"A {hr_s:.2f} {vr_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} Z"
                )
                ET.SubElement(svg, "path", {
                    "data-ir-id": obj_id, "data-role": "fill", "d": d,
                    "fill": fill_color, "fill-opacity": str(fill_opacity), "stroke": "none",
                })
```

In `_obj_to_svg_subpath()`, add an `EllipticalSector` branch directly after the existing `Sector` branch:

```python
    if isinstance(sym_obj, EllipticalSector):
        cx_g, cy_g, hr_g, vr_g, start_deg, end_deg, sx_g, sy_g = elliptical_arc_params(obj_id, sym)
        hr_s = hr_g * scale
        vr_s = vr_g * scale
        end_rad = math.radians(end_deg)
        ex_g = cx_g + hr_g * math.cos(end_rad)
        ey_g = cy_g + vr_g * math.sin(end_rad)
        cx_s, cy_s = gxy(cx_g, cy_g)
        sx_s, sy_s = gxy(sx_g, sy_g)
        ex_s, ey_s = gxy(ex_g, ey_g)
        sweep_deg = end_deg - start_deg
        large_arc = 1 if sweep_deg > 180.0 else 0
        return (
            f"M {cx_s:.2f} {cy_s:.2f} "
            f"L {sx_s:.2f} {sy_s:.2f} "
            f"A {hr_s:.2f} {vr_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} Z"
        )
```

Since `_obj_to_svg_subpath()` is called with `sym` in scope (not module-level `elliptical_arc_params`'s signature `(obj_id, sym)`), no new parameter threading is actually needed if `elliptical_arc_params` is imported at module level in `to_svg.py` (same as `arc_params` already is) — call it directly rather than adding a new `_fn` parameter, matching how `arc_params`/`Sector` are already called directly in that function without being passed in.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_to_svg.py -k elliptical -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/ir/to_svg.py tests/test_to_svg.py
git commit -m "feat: render elliptical arcs/sectors in to_svg.py"
```

---

### Task 6: pydsl layer — polymorphic arc()/sector(), _validate_on_ellipse, point_on() docstring

**Files:**
- Modify: `geometry_diagrams/pydsl/api.py` (the existing `arc()`/`sector()` functions at lines ~304-331, `_validate_on_circle()` at line ~271, `point_on()` at line ~539)
- Test: `tests/test_pydsl_arcs_sectors.py`

**Interfaces:**
- Consumes: `EllipticalArcCenterStartEnd`/`EllipticalSectorCenterStartEnd` (Task 1), `Ellipse`/`Circle` handles (already exist in `handles.py`, unmodified — `Ellipse.hradius`/`Ellipse.vradius` properties already exist and may raise `NotImplementedError`, as seen in the existing bbox-form `ellipse()` implementation).
- Produces: `arc(shape: "Circle | Ellipse", start: Point, end: Point, reflex: bool = False) -> Arc` and `sector(shape, start, end, reflex=False) -> Sector` (renamed first parameter, both still return the SAME `Arc`/`Sector` handle types as before — no handle changes needed since `Arc`/`Sector` handles are just `{id: str}` and callers never branch on which kind of arc they hold), plus a private `_arc_or_sector(kind, shape, start, end, reflex) -> str` dispatcher and `_validate_on_ellipse(fn_name, ellipse, point, point_role) -> None`.

Current `arc()`/`sector()` (exact current code, to be replaced):

```python
def arc(circle: Circle, start: Point, end: Point, reflex: bool = False) -> Arc:
    """The circular arc between start and end (both must lie on circle —
    use point_on(circle, angle) to construct them; an off-circle point can
    silently shift the rendered arc away from circle). reflex=False (the
    default) draws whichever of the two arcs spans <=180°; reflex=True
    draws the other one."""
    from geometry_diagrams.ir.ir import ArcCenterStartEnd

    _validate_on_circle("arc", circle, start, "start")
    _validate_on_circle("arc", circle, end, "end")
    builder = get_builder()
    aid = builder._fresh_hidden_id("arc")
    builder._add(ArcCenterStartEnd(id=aid, center=circle.center.id, start=start.id, end=end.id, reflex=reflex))
    return Arc(id=aid)


def sector(circle: Circle, start: Point, end: Point, reflex: bool = False) -> Sector:
    """The closed pie-slice region bounded by the two radii to start and
    end and the arc between them. Same start/end contract as arc() — both
    must lie on circle; see arc()'s docstring."""
    from geometry_diagrams.ir.ir import SectorCenterStartEnd

    _validate_on_circle("sector", circle, start, "start")
    _validate_on_circle("sector", circle, end, "end")
    builder = get_builder()
    sid = builder._fresh_hidden_id("sector")
    builder._add(SectorCenterStartEnd(id=sid, center=circle.center.id, start=start.id, end=end.id, reflex=reflex))
    return Sector(id=sid)
```

Existing `_validate_on_circle()` (exact current code — unchanged, used as the template for `_validate_on_ellipse`):

```python
def _validate_on_circle(fn_name: str, circle: Circle, point: Point, point_role: str) -> None:
    """Raise if point is knowably NOT on circle. Skipped (no raise) whenever
    circle.center's coordinates, point's coordinates, or circle.radius can't
    currently be resolved to concrete numbers..."""
    cx, cy = circle.center.x, circle.center.y
    px, py = point.x, point.y
    if cx is None or cy is None or px is None or py is None:
        return
    try:
        radius = circle.radius
    except NotImplementedError:
        return
    if isinstance(radius, str):
        return
    actual = math.hypot(px - cx, py - cy)
    if abs(actual - radius) > max(radius * 1e-6, 1e-9):
        raise ValueError(
            f"{fn_name}(): {point_role} point {point.id!r} is not on the given "
            f"circle (distance {actual:.6g} from center, circle radius is "
            f"{radius:.6g}). Use point_on(circle, angle) to get a point "
            "guaranteed to lie on the circle."
        )
```

Existing `point_on()` docstring (exact current code — only the docstring changes in this task, no logic change):

```python
def point_on(obj, t: float) -> Point:
    """A point at parameter t along a line or segment (t=0/1 are the object's
    defining points; for a line, t outside [0, 1] extends past them in either
    direction), or at angle t (radians) on a circle — use this instead of
    hand-computing coordinates to place a point on an existing
    line/segment/circle, or to extend a line's visible extent. This is the
    correct way to build arc()/sector()'s start/end points, guaranteed to
    land exactly on the circle."""
    ...
```

`Ellipse` handle (already exists, unmodified, in `handles.py`):

```python
@dataclass(frozen=True)
class Ellipse:
    id: str
    center: Point
    _hradius_thunk: "object" = field(repr=False, compare=False)
    _vradius_thunk: "object" = field(repr=False, compare=False)

    @property
    def hradius(self) -> float:
        return self._hradius_thunk()

    @property
    def vradius(self) -> float:
        return self._vradius_thunk()
```

- [ ] **Step 1: Write the failing tests**

```python
def test_arc_accepts_ellipse_and_builds_elliptical_arc_def():
    from geometry_diagrams.pydsl.builder import Builder, set_builder
    from geometry_diagrams.pydsl.api import ellipse, point_on, arc

    b = Builder()
    set_builder(b)
    center = _fixed_point(b, 0, 0)  # use whatever this test file's existing helper for a literal point is named
    e = ellipse(center=center, hradius=4, vradius=1)
    s = point_on(e, 0.0)
    end = point_on(e, math.pi / 3)
    result = arc(e, s, end)
    defstmt = b._defs_by_id()[result.id]  # match whatever accessor this file's existing tests already use
    assert defstmt.kind == "elliptical_arc_center_start_end"
    assert defstmt.hradius == 4 and defstmt.vradius == 1


def test_sector_accepts_ellipse_and_builds_elliptical_sector_def():
    ...  # mirror the above for sector()


def test_arc_still_works_unchanged_for_circle():
    # non-regression: existing circle-based arc() behavior must be untouched
    ...


def test_validate_on_ellipse_rejects_off_ellipse_point():
    # mirrors the existing _validate_on_circle test pattern in this file --
    # find it via `grep -n "_validate_on_circle\|not on the given" tests/test_pydsl_arcs_sectors.py`
    ...


def test_arc_raises_clear_error_for_unresolvable_bbox_ellipse_radii():
    # ellipse(corner1=..., corner2=...) built from non-literal (derived) corners
    # -- hradius/vradius raise NotImplementedError; arc() must catch and re-raise
    # a clear arc()-specific ValueError, not let NotImplementedError propagate raw.
    ...
```

(Before writing these, read `tests/test_pydsl_arcs_sectors.py`'s existing tests in full to copy its exact helper names for building a literal point and inspecting the builder's recorded defs — do not invent new helper names.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_arcs_sectors.py -k "ellipse or Ellipse" -v`
Expected: FAIL (`arc()` currently has no `Ellipse` branch — `circle.center` access on an `Ellipse` happens to work since both handles have a `.center` field, but `circle.radius` does not exist on `Ellipse`, so it will `AttributeError`)

- [ ] **Step 3: Implement `_validate_on_ellipse`, `_arc_or_sector`, and rewire `arc()`/`sector()`**

Add directly after `_validate_on_circle()`:

```python
def _validate_on_ellipse(fn_name: str, ellipse: Ellipse, point: Point, point_role: str) -> None:
    """Raise if point is knowably NOT on ellipse. Mirrors _validate_on_circle's
    skip policy exactly, but checks the ellipse equation
    ((px-cx)/hr)**2 + ((py-cy)/vr)**2 == 1 within tolerance instead of a
    simple distance check."""
    cx, cy = ellipse.center.x, ellipse.center.y
    px, py = point.x, point.y
    if cx is None or cy is None or px is None or py is None:
        return
    try:
        hr, vr = ellipse.hradius, ellipse.vradius
    except NotImplementedError:
        return
    value = ((px - cx) / hr) ** 2 + ((py - cy) / vr) ** 2
    if abs(value - 1.0) > 1e-6:
        raise ValueError(
            f"{fn_name}(): {point_role} point {point.id!r} is not on the given "
            f"ellipse (({point_role} - center normalized) evaluates to {value:.6g}, "
            "expected 1.0). Use point_on(ellipse, angle) to get a point "
            "guaranteed to lie on the ellipse."
        )


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
```

Replace `arc()`/`sector()` with:

```python
def arc(shape: "Circle | Ellipse", start: Point, end: Point, reflex: bool = False) -> Arc:
    """The arc between start and end along the boundary of shape (a circle()
    or ellipse()) — both must lie on shape; use point_on(shape, t) to
    construct them (an off-boundary point can silently shift the rendered
    arc away from shape). reflex=False (the default) draws whichever of the
    two arcs spans <=180°; reflex=True draws the other one."""
    aid = _arc_or_sector("arc", shape, start, end, reflex)
    return Arc(id=aid)


def sector(shape: "Circle | Ellipse", start: Point, end: Point, reflex: bool = False) -> Sector:
    """The closed pie-slice region bounded by the two radii to start and end
    and the arc between them, on shape (a circle() or ellipse()). Same
    start/end contract as arc() — see its docstring."""
    sid = _arc_or_sector("sector", shape, start, end, reflex)
    return Sector(id=sid)
```

Update `point_on()`'s docstring only (logic unchanged):

```python
def point_on(obj, t: float) -> Point:
    """A point at parameter t along a line or segment (t=0/1 are the object's
    defining points; for a line, t outside [0, 1] extends past them in either
    direction), or at angle t (radians) on a circle or ellipse — use this
    instead of hand-computing coordinates to place a point on an existing
    line/segment/circle/ellipse, or to extend a line's visible extent. This
    is the correct way to build arc()/sector()'s start/end points, guaranteed
    to land exactly on the shape's boundary."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_arcs_sectors.py -v`
Expected: PASS, including all pre-existing circle-based tests (non-regression)

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/pydsl/api.py tests/test_pydsl_arcs_sectors.py
git commit -m "feat: arc()/sector() accept Ellipse polymorphically alongside Circle"
```

---

### Task 7: IR schema + to_sympy.py — open polyline def statement

**Files:**
- Modify: `geometry_diagrams/ir/ir.py` (near `Polygon` at line ~393; `DefStmt` union at line ~537-551)
- Modify: `geometry_diagrams/ir/to_sympy.py` (near the `Polygon` compile case at line ~524-532)
- Test: `tests/test_ir.py`, `tests/test_to_sympy.py`

**Interfaces:**
- Produces: `PolylineOpen(DefBase)` IR class with `kind: Literal["polyline_open"] = "polyline_open"` and `points: List[PointId]`, added to `DefStmt`. Compile case returning a plain Python `list` of SymPy `Point` objects (NOT a `spg.Polygon` or any SymPy geometry object — SymPy has no open-multi-point-path type).

Existing `Polygon` IR class and compile case (exact current code, read-only reference):

```python
class Polygon(DefBase):
    """Closed polygon with 3+ vertices (in order). Subsumes Triangle for drawing."""
    kind: Literal["polygon"] = "polygon"
    points: List[PointId]  # 3 or more, closed automatically
```

```python
case ir.Polygon(points=point_ids):
    pts = [ref(pid) for pid in point_ids]
    result = spg.Polygon(*pts)
    if not isinstance(result, spg.Polygon) or len(result.vertices) != len(pts):
        raise IRCompileError(
            did,
            f"polygon: vertices {point_ids!r} are collinear or coincident — degenerate polygon"
        )
    return result
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ir.py
def test_polyline_open_round_trips():
    from geometry_diagrams.ir.ir import PolylineOpen

    stmt = PolylineOpen(id="pl1", points=["a", "b", "c"])
    assert stmt.kind == "polyline_open"
    assert stmt.points == ["a", "b", "c"]


# tests/test_to_sympy.py
def test_polyline_open_compiles_to_plain_point_list():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.to_sympy import compile_defs
    import sympy.geometry as spg

    defs = [
        ir.PointFixed(id="a", x=0, y=0),
        ir.PointFixed(id="b", x=1, y=0),
        ir.PointFixed(id="c", x=1, y=1),
        ir.PolylineOpen(id="pl1", points=["a", "b", "c"]),
    ]
    sym = compile_defs(defs)
    result = sym["pl1"]
    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(p, spg.Point) for p in result)
    assert not isinstance(result, spg.Polygon)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ir.py tests/test_to_sympy.py -k polyline -v`
Expected: FAIL with `ImportError: cannot import name 'PolylineOpen'`

- [ ] **Step 3: Add the IR class, register it, add the compile case**

In `ir.py`, add directly after `Polygon` (before `PolygonExterior`):

```python
class PolylineOpen(DefBase):
    """Open (non-closed) chain of 3+ points, in order. Unlike Polygon, the
    last point does NOT connect back to the first — no closing edge is
    drawn. Used for tracing paths (e.g. locus construction) rather than
    filled regions."""
    kind: Literal["polyline_open"] = "polyline_open"
    points: List[PointId]  # 2 or more, NOT closed
```

Add `PolylineOpen` to the `DefStmt` union, directly after `Triangle, Polygon, PolygonExterior, PolygonOnEdge,`:

```python
        Triangle, Polygon, PolygonExterior, PolygonOnEdge, PolylineOpen,
```

In `to_sympy.py`, add directly after the `Polygon` compile case:

```python
        case ir.PolylineOpen(points=point_ids):
            return [ref(pid) for pid in point_ids]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ir.py tests/test_to_sympy.py -k polyline -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/ir/ir.py geometry_diagrams/ir/to_sympy.py tests/test_ir.py tests/test_to_sympy.py
git commit -m "feat: add PolylineOpen IR class compiling to a plain point list"
```

---

### Task 8: to_tikz.py + to_svg.py — render open polylines

**Files:**
- Modify: `geometry_diagrams/ir/to_tikz.py` (`_emit_op()`'s `ir.Draw`/`ir.Fill` handling of `Polygon`-typed `sym_obj`, near lines ~211-334)
- Modify: `geometry_diagrams/ir/to_svg.py` (`ir.Draw`'s Polygon branch at lines ~390-407, `ir.Fill`'s Polygon branch at ~603+)
- Test: `tests/test_to_tikz.py`, `tests/test_to_svg.py`

**Interfaces:**
- Consumes: `PolylineOpen` compiling to a plain `list[spg.Point]` (Task 7) — dispatch on `isinstance(sym_obj, list)`, since a compiled `PolylineOpen` is the only def type that compiles to a raw Python `list` rather than a SymPy object.

Both renderers currently dispatch on `isinstance(sym_obj, (spg.Triangle, spg.Polygon))` for closed shapes. A `PolylineOpen`'s compiled value (`list[spg.Point]`) will never match that check — it needs its own branch, checked via `isinstance(sym_obj, list)`.

Existing `to_svg.py` `Draw`-case Polygon branch (exact current code, read-only reference — the wraparound `(i + 1) % len(sv)` in the `drawn_segments` loop must NOT be replicated for the open polyline):

```python
if isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
    verts = poly_verts(obj_id, stmt_by_id)
    pts_str = " ".join(f"{pt(v)[0]:.2f},{pt(v)[1]:.2f}" for v in verts)
    geo_type = "triangle" if len(verts) == 3 else "polygon"
    ET.SubElement(svg, "polygon", {
        "data-ir-id": obj_id, "data-type": geo_type, "data-vertices": ",".join(verts),
        "points": pts_str, "fill": "none", **attrs,
    })
    if drawn_segments is not None:
        sv = [pt(v) for v in verts]
        for i in range(len(sv)):
            ax, ay = sv[i]
            bx, by = sv[(i + 1) % len(sv)]  # wraps last -> first: closed-shape-only behavior
            drawn_segments.append((ax, ay, bx, by))
```

`poly_verts(obj_id, stmt_by_id)` reads `stmt_by_id[obj_id].points` — this works identically for a `PolygonExterior`... actually check: `poly_verts` is keyed off the `DefStmt`'s own `points`/vertex-list field, and `PolylineOpen` also has a `.points` field of point ids, so `poly_verts` should work unmodified for it too (verify by reading `poly_verts()`'s exact implementation before relying on this — if it pattern-matches on `stmt.kind` rather than duck-typing `.points`, add a `PolylineOpen` case there too).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_to_svg.py
def test_to_svg_renders_open_polyline_as_native_polyline_element():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.ir import DiagramIR, Canvas
    from geometry_diagrams.ir.to_svg import compile_to_svg

    diagram = DiagramIR(
        canvas=Canvas(x_range=(-5, 5), y_range=(-5, 5)),
        defs=[
            ir.PointFixed(id="a", x=0, y=0),
            ir.PointFixed(id="b", x=1, y=0),
            ir.PointFixed(id="c", x=1, y=1),
            ir.PolylineOpen(id="pl1", points=["a", "b", "c"]),
        ],
        render=[ir.Draw(obj="pl1")],
    )
    svg = compile_to_svg(diagram)
    assert "<polyline" in svg
    assert "<polygon" not in svg
    assert "cycle" not in svg.lower()


# tests/test_to_tikz.py
def test_to_tikz_renders_open_polyline_without_closing_cycle():
    from geometry_diagrams.ir import ir
    from geometry_diagrams.ir.ir import DiagramIR, Canvas
    from geometry_diagrams.ir.to_tikz import compile_to_tikz

    diagram = DiagramIR(
        canvas=Canvas(x_range=(-5, 5), y_range=(-5, 5)),
        defs=[
            ir.PointFixed(id="a", x=0, y=0),
            ir.PointFixed(id="b", x=1, y=0),
            ir.PointFixed(id="c", x=1, y=1),
            ir.PolylineOpen(id="pl1", points=["a", "b", "c"]),
        ],
        render=[ir.Draw(obj="pl1")],
    )
    tikz = compile_to_tikz(diagram)
    assert "cycle" not in tikz
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_to_svg.py tests/test_to_tikz.py -k polyline -v`
Expected: FAIL (currently no branch matches a compiled `list`; the object silently falls through with no `elif` matching, so nothing gets drawn — the `<polyline` assertion fails)

- [ ] **Step 3: Add the renderer branches**

In `to_svg.py`'s `ir.Draw` case, add a new branch (checked BEFORE or independently of the `(spg.Triangle, spg.Polygon)` check — order doesn't matter since a `list` never matches that isinstance check):

```python
            elif isinstance(sym_obj, list):
                verts = poly_verts(obj_id, stmt_by_id)
                pts_str = " ".join(f"{pt(v)[0]:.2f},{pt(v)[1]:.2f}" for v in verts)
                ET.SubElement(svg, "polyline", {
                    "data-ir-id": obj_id,
                    "data-type": "polyline",
                    "data-vertices": ",".join(verts),
                    "points": pts_str,
                    "fill": "none",
                    **attrs,
                })
                if drawn_segments is not None:
                    sv = [pt(v) for v in verts]
                    for i in range(len(sv) - 1):  # NO wraparound: open path
                        ax, ay = sv[i]
                        bx, by = sv[i + 1]
                        drawn_segments.append((ax, ay, bx, by))
```

In `to_svg.py`'s `ir.Fill` case, add a branch that warns rather than silently no-ops for anything other than the `holes=[...]` path (which already handles unsupported types via `_obj_to_svg_subpath` returning `None`):

```python
            elif isinstance(sym_obj, list):
                _warn(warnings, f"Skipping Fill for '{obj_id}': an open polyline has no interior to fill")
```

In `to_tikz.py`'s `_emit_op()`, add to the `ir.Draw` case (mirroring `\tkzDrawPolygon` but drawing the vertex chain without `-- cycle` — TikZ has no direct polyline primitive via `tkz-euclide`, so build it as a raw `\draw` path, matching how `Sector`/`Ellipse` already fall back to raw `\draw` in this file):

```python
            elif isinstance(sym_obj, list):
                verts = _poly_verts(obj_id, stmt_by_id)
                style_inner = sopts[1:-1] if sopts else ""
                path = " -- ".join(f"({v})" for v in verts)  # tkz-euclide resolves point names directly
                out.append(f"\\draw[{style_inner}] {path}")
```

(Check `_poly_verts`'s exact return type here — if it returns coordinate tuples rather than point-name strings usable directly in a `\draw` path, use the same coordinate-formatting approach the existing `Sector`/`Ellipse` raw-`\draw` branches already use instead of point names — read those branches' exact code first and match their pattern rather than the point-name form shown above.)

Add to `_emit_op()`'s `ir.Fill` case, a no-op warning branch mirroring the SVG side:

```python
            elif isinstance(sym_obj, list):
                logger.warning(f"Skipping Fill for '{obj_id}': an open polyline has no interior to fill")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_to_svg.py tests/test_to_tikz.py -k polyline -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/ir/to_tikz.py geometry_diagrams/ir/to_svg.py tests/test_to_tikz.py tests/test_to_svg.py
git commit -m "feat: render open polylines in to_tikz.py and to_svg.py"
```

---

### Task 9: pydsl layer — polyline() function and Polyline handle

**Files:**
- Modify: `geometry_diagrams/pydsl/handles.py` (add `Polyline` near `Polygon` at line ~171)
- Modify: `geometry_diagrams/pydsl/api.py` (add `polyline()` near `polygon()` at line ~74)
- Modify: `geometry_diagrams/pydsl/__init__.py` (add `polyline`/`Polyline` to imports and `__all__`)
- Test: `tests/test_pydsl_polygon.py` (add alongside existing `polygon()` tests) or a new `tests/test_pydsl_polyline.py` if the existing file's scope is polygon-only — check first.

**Interfaces:**
- Consumes: `PolylineOpen` (Task 7).
- Produces: `Polyline(id: str, vertices: tuple[Point, ...])` handle (minimal, no `.side()`/`.angle_at()` methods — those are non-goals per the spec), `polyline(*points: Point) -> Polyline` function.

Existing `polygon()` (exact current code, read-only reference — the coincident-CONSECUTIVE-pair guard with wraparound check is the template to copy, MINUS the wraparound):

```python
def polygon(*vertices: Point) -> Polygon:
    """A polygon over 3 or more points, in perimeter order. The shape is
    closed automatically — the last point connects back to the first.
    Do not repeat the first point at the end; that produces a
    coincident-vertex error rather than a no-op."""
    if len(vertices) < 3:
        raise ValueError(f"polygon requires at least 3 vertices, got {len(vertices)}")
    n = len(vertices)
    for i in range(n):
        prev, cur = vertices[i - 1], vertices[i]  # i=0 wraps to last->first
        if prev.x is None or prev.y is None or cur.x is None or cur.y is None:
            continue
        if math.hypot(cur.x - prev.x, cur.y - prev.y) < 1e-9:
            raise ValueError(
                f"polygon() vertices {prev.id!r} and {cur.id!r} are coincident. "
                "polygon() already closes the shape automatically — do not repeat "
                "the first point as the last."
            )
    builder = get_builder()
    pid = builder._fresh_hidden_id("poly")
    builder._add(PolygonDef(id=pid, points=[v.id for v in vertices]))
    return Polygon(id=pid, vertices=tuple(vertices), _builder=builder)
```

`Polygon` handle (exact current code, read-only reference — `Polyline` is a stripped-down version with no `.side()`/`.angle_at()`):

```python
@dataclass(frozen=True)
class Polygon:
    id: str
    vertices: tuple[Point, ...]
    _builder: "object" = field(repr=False, compare=False)

    def side(self, v1: Point, v2: Point) -> "Segment": ...
    def angle_at(self, v: Point) -> "AngleRef": ...
```

- [ ] **Step 1: Write the failing tests**

```python
def test_polyline_requires_at_least_two_points():
    from geometry_diagrams.pydsl.api import polyline

    with pytest.raises(ValueError, match="at least 2"):
        polyline()  # or with 1 point, matching the exact chosen minimum in Step 3


def test_polyline_rejects_consecutive_coincident_points():
    # a, b, a with a==b coincident consecutively -- must raise
    ...


def test_polyline_allows_first_and_last_coincident_no_wraparound_check():
    # polyline(A, B, A) where A != B -- must NOT raise (unlike polygon())
    ...


def test_polyline_builds_polyline_open_def():
    ...  # verify the recorded def has kind "polyline_open" and correct point ids


def test_polyline_renders_through_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = """
p0 = point(0, 0)
p1 = point(1, 0)
p2 = point(1, 1)
pl = polyline(p0, p1, p2)
draw(pl)
"""
    result = run_script(script)
    assert result.svg is not None  # match whatever this file's existing sandbox tests assert on the result
```

(Read `tests/test_pydsl_polygon.py`'s existing coincident-vertex test and its existing sandbox test at the bottom of the file first, to copy its exact `run_script`/result-shape conventions.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pydsl_polygon.py -k polyline -v` (or the new file's path)
Expected: FAIL with `ImportError: cannot import name 'polyline'`

- [ ] **Step 3: Add the `Polyline` handle and `polyline()` function**

In `handles.py`, add directly after `Polygon`:

```python
@dataclass(frozen=True)
class Polyline:
    id: str
    vertices: tuple[Point, ...]
    _builder: "object" = field(repr=False, compare=False)
```

In `api.py`, add directly after `polygon()`:

```python
def polyline(*points: Point) -> Polyline:
    """An open chain of 2 or more points, drawn in order with NO closing
    edge back to the first point (unlike polygon()). Only CONSECUTIVE
    coincident points are rejected — the first and last points ARE allowed
    to coincide (e.g. a closed-looking traced path), since polyline()
    never adds a wraparound edge the way polygon() does."""
    if len(points) < 2:
        raise ValueError(f"polyline requires at least 2 points, got {len(points)}")
    for i in range(1, len(points)):
        prev, cur = points[i - 1], points[i]
        if prev.x is None or prev.y is None or cur.x is None or cur.y is None:
            continue
        if math.hypot(cur.x - prev.x, cur.y - prev.y) < 1e-9:
            raise ValueError(
                f"polyline() vertices {prev.id!r} and {cur.id!r} are coincident "
                "consecutive points."
            )
    from geometry_diagrams.ir.ir import PolylineOpen

    builder = get_builder()
    pid = builder._fresh_hidden_id("polyline")
    builder._add(PolylineOpen(id=pid, points=[p.id for p in points]))
    return Polyline(id=pid, vertices=tuple(points), _builder=builder)
```

Update `geometry_diagrams/pydsl/__init__.py`: add `polyline` to the `from geometry_diagrams.pydsl.api import (...)` line (alphabetical, next to `polygon`), add `Polyline` to the `from geometry_diagrams.pydsl.handles import (...)` line (alphabetical, next to `Point`), and add both `"polyline"` and `"Polyline"` to `__all__` in their respective alphabetical positions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pydsl_polygon.py -v` (or new file)
Expected: PASS

- [ ] **Step 5: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/pydsl/handles.py geometry_diagrams/pydsl/api.py geometry_diagrams/pydsl/__init__.py tests/test_pydsl_polygon.py
git commit -m "feat: add polyline() and Polyline handle for open point chains"
```

---

### Task 10: Docs + sandbox test for both features together

**Files:**
- Modify: `geometry_diagrams/strategies/instructions_python_full.py` (the LLM-facing instructions the `python_full` strategy uses)
- Modify: `tests/test_pydsl_arcs_sectors.py` and/or a new sandbox test file
- Test: sandbox-level test exercising `arc()`/`sector()` with an `Ellipse` and `polyline()` together

**Interfaces:**
- Consumes: everything from Tasks 1-9.

Existing instructions file's relevant section (exact current text, read-only reference — the new-shapes bullet where `ellipse()` is already documented, at line ~81):

```
- New shapes: `ray(a, b)` (a ray from a through and beyond b), `ellipse(center=c, hradius=..., vradius=...)`
  or `ellipse(corner1=c1, corner2=c2)` (opposite bounding-box corners), `regular_polygon(center, radius, n)`,
  and `rectangle(corner, width, height, rotation=0.0, pivot="center")` (pivot="corner" rotates around
  `corner` instead of the rectangle's own center). All angles (rotation, and walk()'s heading below)
  are radians, counter-clockwise from the +x axis — same convention as rotate_point().
```

- [ ] **Step 1: Add documentation for `arc()`/`sector()` accepting `Ellipse`, and for `polyline()`**

Add a new bullet directly after the `walk()`/`polygon()` example block (after the line ending `draw(tri)`):

```
- `arc(shape, start, end, reflex=False)` and `sector(shape, start, end, reflex=False)` work on EITHER a
  `circle()` or an `ellipse()` — use `point_on(shape, t)` to build start/end so they land exactly on the
  boundary (an off-boundary point silently shifts the rendered arc). For a circle, t is an angle in
  radians; the same point_on() call works for an ellipse's parametric angle too.
- `polyline(*points)` draws an OPEN chain of 2+ points with no closing edge — unlike `polygon()`, it does
  not connect the last point back to the first. Useful for tracing a path (e.g. sampling several
  positions of a point as it moves) rather than filling a region; `fill()` on a polyline is a no-op since
  it has no interior.
```

- [ ] **Step 2: Write and run the combined sandbox test**

```python
def test_elliptical_arc_and_polyline_work_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = """
c = point(0, 0)
e = ellipse(center=c, hradius=4, vradius=1)
s = point_on(e, 0.0)
end = point_on(e, math.pi / 3)
a = arc(e, s, end)
draw(a)

p0 = point(-3, -3)
p1 = point(-2, -3)
p2 = point(-2, -2)
pl = polyline(p0, p1, p2)
draw(pl)
"""
    result = run_script(script)
    assert result.svg is not None  # match this file's/the existing sandbox tests' exact assertion shape
```

Run: `.venv/bin/python -m pytest tests/test_pydsl_arcs_sectors.py -k real_sandbox -v` (or wherever this test lands)
Expected: PASS

- [ ] **Step 3: Run the full test suite and commit**

Run: `.venv/bin/python -m pytest tests/`
Expected: all pass

```bash
git add geometry_diagrams/strategies/instructions_python_full.py tests/test_pydsl_arcs_sectors.py
git commit -m "docs: document elliptical arc/sector and polyline support in python_full instructions; add sandbox test"
```

---

## After Implementation

Once all 10 tasks are complete and the final whole-branch review is clean, generate real LLM-generated example scripts exercising `arc()`/`sector()` with an `Ellipse` and `polyline()` (the user explicitly flagged skepticism about the `arc()`/`sector()`-accepts-`Ellipse` ergonomics and wants to see how a real LLM uses it), render them, and publish as an Artifact gallery for review — mirroring the process used for every prior cluster in this branch.

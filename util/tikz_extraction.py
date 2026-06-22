"""
Regex-based extraction of geometric objects from TikZ/tkz-euclide source code.

Parses point definitions, draw commands, marks, labels, and canvas features
from TikZ source strings. No coordinate computation is performed here.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Point name normalization (A' <-> Aprime)
# ---------------------------------------------------------------------------

def _prime_variants(name: str) -> set[str]:
    """Return the set of plausible TikZ point-name variants for *name*.

    Handles the many ways LLMs encode primes: A', Ap, A2, A_prime,
    Aprime, etc.  The returned set always includes the original name.
    """
    variants: set[str] = {name}

    # Detect how many primes are in the name and extract the base.
    # Try tick marks first: A', A'', A'''
    if name.endswith("'''"):
        base, n = name[:-3], 3
    elif name.endswith("''"):
        base, n = name[:-2], 2
    elif name.endswith("'"):
        base, n = name[:-1], 1
    # Spelled-out suffixes: Atripleprime, Aprimeprime, Aprime
    elif name.endswith("tripleprime"):
        base, n = name[: -len("tripleprime")], 3
    elif name.endswith("primeprime"):
        base, n = name[: -len("primeprime")], 2
    elif name.endswith("prime"):
        base, n = name[: -len("prime")], 1
    else:
        return variants

    tick = "'" * n
    spelled = {1: "prime", 2: "primeprime", 3: "tripleprime"}[n]
    p_suffix = "p" * n          # Ap, App, Appp
    pp_suffix = {1: "p", 2: "pp", 3: "ppp"}[n]

    variants.update([
        f"{base}{tick}",            # A'  A''  A'''
        f"{base}{spelled}",         # Aprime  Aprimeprime  Atripleprime
        f"{base}_{spelled}",        # A_prime  A_primeprime
        f"{base}{pp_suffix}",       # Ap  App  Appp
        f"{base}{n}",               # A1  A2  A3
        f"{base}d" * 1 if n == 1 else f"{base}{'d' * n}",  # Ad, Add, Addd (rare)
    ])
    return variants


def normalize_point_name(name: str) -> str:
    """Normalize prime variants to a canonical spelled-out form.

    Converts A', Ap, A2, A_prime, etc. to ``Aprime`` so callers can
    compare with a single ``==``.
    """
    if name.endswith("'''"):
        return name[:-3] + "tripleprime"
    if name.endswith("''"):
        return name[:-2] + "primeprime"
    if name.endswith("'"):
        return name[:-1] + "prime"
    return name


def point_names_match(expected: str, actual: str) -> bool:
    """Return True if *expected* and *actual* refer to the same point,
    accounting for the many prime-notation variants LLMs produce."""
    if expected == actual:
        return True
    return actual in _prime_variants(expected)

# ---------------------------------------------------------------------------
# Point extraction
# ---------------------------------------------------------------------------

# Point names may contain trailing primes: A, A', A''
_POINT_NAME = r"\w+'{0,3}"

_DEF_POINT_RE = re.compile(
    rf"\\tkzDefPoint\s*\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)\s*\{{({_POINT_NAME})\}}"
)
_COORDINATE_RE = re.compile(
    rf"\\coordinate\s*\(({_POINT_NAME})\)\s*at\s*\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)"
)


def extract_defined_points(tikz: str) -> dict[str, tuple[float, float]]:
    """Extract explicitly defined points from \\tkzDefPoint(x,y){Name} and \\coordinate(name) at (x,y) commands."""
    points: dict[str, tuple[float, float]] = {}
    for m in _DEF_POINT_RE.finditer(tikz):
        x, y, name = float(m.group(1)), float(m.group(2)), m.group(3)
        points[name] = (x, y)
    for m in _COORDINATE_RE.finditer(tikz):
        name, x, y = m.group(1), float(m.group(2)), float(m.group(3))
        points[name] = (x, y)
    return points


# ---------------------------------------------------------------------------
# Computed / derived point extraction
# ---------------------------------------------------------------------------

_GET_POINT_RE = re.compile(rf"\\tkzGetPoint\s*\{{({_POINT_NAME})\}}")
_MID_POINT_RE = re.compile(r"\\tkzDefMidPoint\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)")
_CIRCUM_CENTER_RE = re.compile(
    r"\\tkzCircumCenter\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_INTER_LL_RE = re.compile(
    r"\\tkzInterLL\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_ORTHO_CENTER_RE = re.compile(
    r"\\tkzOrthoCenter\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_CENTROID_RE = re.compile(
    r"\\tkzCentroid\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
# \tkzDefTriangleCenter[in](A,B,C) or [circum] or [ortho] etc.
_TRIANGLE_CENTER_RE = re.compile(
    r"\\tkzDefTriangleCenter\s*\[(\w+)\]\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
# \tkzDefPointBy[projection=onto A--B](C) — projection of last arg onto the line
_PROJECTION_RE = re.compile(
    r"\\tkzDefPointBy\s*\[projection=onto\s+(\w+)--(\w+)\]\s*\((\w+)\)"
)
# \tkzDefPointBy[symmetry=center A](B) — reflection of B across A
_SYMMETRY_CENTER_RE = re.compile(
    r"\\tkzDefPointBy\s*\[symmetry=center\s+(\w+)\]\s*\((\w+)\)"
)


def extract_computed_points(tikz: str) -> dict[str, dict[str, Any]]:
    """
    Extract derived points defined via computation commands.
    Returns a dict mapping point name -> {'type': ..., 'args': [...]}.
    These require known coordinates of their inputs to resolve to (x,y).
    """
    computed: dict[str, dict[str, Any]] = {}

    # Pair each computation command with the following \\tkzGetPoint
    # by scanning positionally through the source.
    tokens = list(re.finditer(
        r"(\\tkzDefMidPoint|\\tkzCircumCenter|\\tkzInterLL|\\tkzGetPoint"
        r"|\\tkzOrthoCenter|\\tkzCentroid|\\tkzDefTriangleCenter|\\tkzDefPointBy)\b",
        tikz,
    ))

    pending: dict[str, Any] | None = None
    for tok in tokens:
        cmd = tok.group(1)
        # Find the full command text starting at this token
        rest = tikz[tok.start():]

        if cmd == "\\tkzDefMidPoint":
            m = _MID_POINT_RE.match(rest)
            if m:
                pending = {"type": "midpoint", "args": [m.group(1), m.group(2)]}

        elif cmd == "\\tkzCircumCenter":
            m = _CIRCUM_CENTER_RE.match(rest)
            if m:
                pending = {
                    "type": "circumcenter",
                    "args": [m.group(1), m.group(2), m.group(3)],
                }

        elif cmd == "\\tkzInterLL":
            m = _INTER_LL_RE.match(rest)
            if m:
                pending = {
                    "type": "inter_ll",
                    "args": [m.group(1), m.group(2), m.group(3), m.group(4)],
                }

        elif cmd == "\\tkzOrthoCenter":
            m = _ORTHO_CENTER_RE.match(rest)
            if m:
                pending = {
                    "type": "orthocenter",
                    "args": [m.group(1), m.group(2), m.group(3)],
                }

        elif cmd == "\\tkzCentroid":
            m = _CENTROID_RE.match(rest)
            if m:
                pending = {
                    "type": "centroid",
                    "args": [m.group(1), m.group(2), m.group(3)],
                }

        elif cmd == "\\tkzDefTriangleCenter":
            m = _TRIANGLE_CENTER_RE.match(rest)
            if m:
                kind = m.group(1).lower()
                if kind in ("in", "circum", "ortho"):
                    type_map = {"in": "incenter", "circum": "circumcenter", "ortho": "orthocenter"}
                    pending = {
                        "type": type_map[kind],
                        "args": [m.group(2), m.group(3), m.group(4)],
                    }
                elif kind == "centroid":
                    pending = {
                        "type": "centroid",
                        "args": [m.group(2), m.group(3), m.group(4)],
                    }

        elif cmd == "\\tkzDefPointBy":
            m = _PROJECTION_RE.match(rest)
            if m:
                pending = {
                    "type": "projection",
                    "args": [m.group(3), m.group(1), m.group(2)],  # project point, line_a, line_b
                }
            else:
                m = _SYMMETRY_CENTER_RE.match(rest)
                if m:
                    pending = {
                        "type": "symmetry",
                        "args": [m.group(2), m.group(1)],  # point to reflect, center
                    }

        elif cmd == "\\tkzGetPoint":
            m = _GET_POINT_RE.match(rest)
            if m and pending is not None:
                computed[m.group(1)] = pending
                pending = None

    return computed


# ---------------------------------------------------------------------------
# Draw command extraction
# ---------------------------------------------------------------------------

_POLYGON_RE = re.compile(r"\\tkzDrawPolygon\s*\(([^)]+)\)")
_SEGMENT_RE = re.compile(r"\\tkzDrawSegment(?:\[[^\]]*\])?\s*\(([^)]+)\)")
_LINE_RE = re.compile(r"\\tkzDrawLine(?:\[[^\]]*\])?\s*\(([^)]+)\)")
_CIRCLE_RE = re.compile(r"\\tkzDrawCircle(?:\[[^\]]*\])?\s*\(([^)]+)\)")


def _split_args(s: str) -> list[str]:
    return [p.strip() for p in s.split(",") if p.strip()]


def extract_draw_commands(tikz: str) -> list[dict[str, Any]]:
    """Extract draw commands: polygon, segment, line, circle."""
    commands: list[dict[str, Any]] = []

    for m in _POLYGON_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        if len(pts) >= 2:
            edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
            commands.append({"type": "polygon", "points": pts, "edges": edges})

    for m in _SEGMENT_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        if len(pts) == 2:
            commands.append({"type": "segment", "from": pts[0], "to": pts[1]})

    for m in _LINE_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        if len(pts) == 2:
            commands.append({"type": "line", "through": pts})

    for m in _CIRCLE_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        if len(pts) == 2:
            commands.append({"type": "circle", "center": pts[0], "through": pts[1]})

    return commands


# ---------------------------------------------------------------------------
# Mark extraction
# ---------------------------------------------------------------------------

_RIGHT_ANGLE_RE = re.compile(
    rf"\\tkzMarkRightAngle(?:\[([^\]]*)\])?\s*\(\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*\)"
)
_ANGLE_MARK_RE = re.compile(
    rf"\\tkzMarkAngle(?:\[([^\]]*)\])?\s*\(\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*\)"
)
_SEGMENT_MARK_RE = re.compile(
    rf"\\tkzMarkSegment(?:\[([^\]]*)\])?\s*\(\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*\)"
)

# Match the mark symbol inside an option string, e.g. "mark=||" -> "||".
_TICK_SYMBOL_RE = re.compile(r"mark\s*=\s*([^,\]\s]+)")
# Match the tkz-euclide arc option, e.g. "arc=ll" -> "ll".
_ARC_OPTION_RE = re.compile(r"arc\s*=\s*(l+)")


def _segment_mark_info(opts: str | None) -> tuple[str, int, str]:
    """Return (mark_type, count, symbol) for a segment-mark option string.

    tkz-euclide encodes equal-length tick marks as ``mark=|`` (1), ``||`` (2),
    ``|||`` (3) and slash variants ``s``/``s|``/``s||``; parallel marks use
    ``mark=>``/``>>``/``>>>``. We split these into two kinds so a tick check
    never matches a parallel arrow: ``>``-family → ``parallel_mark``, everything
    else → ``segment_mark`` (a tick). ``count`` is the stroke multiplicity.
    """
    if not opts:
        return "segment_mark", 1, "|"
    m = _TICK_SYMBOL_RE.search(opts)
    if not m:
        return "segment_mark", 1, "|"
    symbol = m.group(1)
    if ">" in symbol:
        return "parallel_mark", max(symbol.count(">"), 1), symbol
    n = symbol.count("|")
    return "segment_mark", (n if n >= 1 else 1), symbol


def _arc_count(opts: str | None) -> int:
    """Return the arc stroke count for an angle-mark option string.

    tkz-euclide encodes arc multiplicity as ``arc=l`` (1), ``arc=ll`` (2),
    ``arc=lll`` (3). Absent → 1 (a single arc is the default).
    """
    if not opts:
        return 1
    m = _ARC_OPTION_RE.search(opts)
    return len(m.group(1)) if m else 1


def extract_marks(tikz: str) -> list[dict[str, Any]]:
    """Extract mark commands: right angles, angles, segment tick marks.

    Each mark dict carries the legacy ``from``/``to``/``vertex`` fields plus a
    ``count`` (stroke multiplicity) and ``symbol``. Segment marks are split by
    kind: ``>``-family parallel arrows → ``type="parallel_mark"``; ``|``/``s``
    -family ticks → ``type="segment_mark"`` — so a tick check never matches a
    parallel arrow. ``right_angle``/``angle`` marks carry an arc ``count``.
    """
    marks: list[dict[str, Any]] = []

    for m in _RIGHT_ANGLE_RE.finditer(tikz):
        marks.append({
            "type": "right_angle",
            "from": m.group(2),
            "vertex": m.group(3),
            "to": m.group(4),
            "count": 1,
        })

    for m in _ANGLE_MARK_RE.finditer(tikz):
        opts = m.group(1)
        marks.append({
            "type": "angle",
            "from": m.group(2),
            "vertex": m.group(3),
            "to": m.group(4),
            "count": _arc_count(opts),
        })

    for m in _SEGMENT_MARK_RE.finditer(tikz):
        opts = m.group(1)
        mtype, count, symbol = _segment_mark_info(opts)
        marks.append({
            "type": mtype,
            "from": m.group(2),
            "to": m.group(3),
            "count": count,
            "symbol": symbol,
        })

    return marks


# ---------------------------------------------------------------------------
# Label extraction
# ---------------------------------------------------------------------------

_LABEL_POINTS_RE = re.compile(
    r"\\tkzLabelPoints(?:\[[^\]]*\])?\s*\(([^)]+)\)"
)
_LABEL_POINT_RE = re.compile(
    rf"\\tkzLabelPoint(?:\[[^\]]*\])?\s*\(({_POINT_NAME})\)\s*\{{([^}}]+)\}}"
)
# Free-floating text labels placed via \node or a bare path-style `node` op,
# e.g. `\node at (5.5,2.3) {$m$};` or `\draw (A)--(B) node[midway] {$x$};`.
# These are how LLMs label lines, regions, and axes (vs. points, which use
# \tkzLabelPoint). Captures the text inside the first {...} group.
_NODE_LABEL_RE = re.compile(
    r"(?:\\node|(?<![\w\\])node)\b[^;{}]*?\{([^{}]*)\}"
)
# Segment/angle labels: the label text lives in braces; the parenthesized
# args are point ids (not the label). e.g. \tkzLabelAngle(A,B,C){$1$}.
_LABEL_SEGMENT_RE = re.compile(
    r"\\tkzLabelSegment(?:\[[^\]]*\])?\s*\([^)]*\)\s*\{([^}]+)\}"
)
_LABEL_ANGLE_RE = re.compile(
    r"\\tkzLabelAngle(?:\[[^\]]*\])?\s*\([^)]*\)\s*\{([^}]+)\}"
)
_MATH_SEG_RE = re.compile(r"\$([^$]+)\$")
_TKZ_GRID_RE = re.compile(r"\\tkzGrid\b")
_TKZ_AXES_RE = re.compile(r"\\tkzAxeXY\b")
_RAW_GRID_RE = re.compile(
    r"\\draw(?:\[[^\]]*\])?\s*\([^)]*\)\s*grid\s*\([^)]*\)"
)
_RAW_AXIS_DRAW_RE = re.compile(
    r"\\draw(?:\[[^\]]*->?[^\]]*\])?\s*"
    r"\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)\s*--\s*"
    r"\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)"
)


def label_text_tokens(inner: str) -> list[str]:
    """Extract label tokens from the text/brace content of a label.

    Prefers inline-math segments ($...$); falls back to the whole stripped
    content when there is no math delimiter. Empty tokens are dropped.

    Used for both free `\\node` text labels and the text of `\\tkzLabelPoint`
    (where the human-readable label often lives, distinct from the point id).
    """
    tokens: list[str] = []
    for m in _MATH_SEG_RE.finditer(inner):
        s = m.group(1).strip()
        if s:
            tokens.append(s)
    if not tokens:
        s = inner.strip().strip("$").strip()
        if s:
            tokens.append(s)
    return tokens


def extract_labels(tikz: str) -> list[dict[str, Any]]:
    """Extract label commands."""
    labels: list[dict[str, Any]] = []

    for m in _LABEL_POINTS_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        labels.append({"type": "label_points", "points": pts})

    for m in _LABEL_POINT_RE.finditer(tikz):
        labels.append({"type": "label_point", "point": m.group(1), "text": m.group(2)})

    for m in _NODE_LABEL_RE.finditer(tikz):
        for token in label_text_tokens(m.group(1)):
            labels.append({"type": "node_label", "text": token})

    for m in _LABEL_SEGMENT_RE.finditer(tikz):
        for token in label_text_tokens(m.group(1)):
            labels.append({"type": "segment_label", "text": token})

    for m in _LABEL_ANGLE_RE.finditer(tikz):
        for token in label_text_tokens(m.group(1)):
            labels.append({"type": "angle_label", "text": token})

    return labels


def collect_label_names(tikz: str) -> list[str]:
    """All candidate label names in *tikz*: point ids plus label text tokens.

    Unified source for label-presence checks (`validate_required_labels`,
    `label_present`). Covers `\\tkzLabelPoint[s]` (point id and text),
    `\\tkzLabelSegment`/`\\tkzLabelAngle` text, and free `\\node` text.
    """
    names: list[str] = []
    for label in extract_labels(tikz):
        t = label.get("type")
        if t == "label_points":
            names.extend(label["points"])
        elif t == "label_point":
            names.append(label["point"])
            names.extend(label_text_tokens(label["text"]))
        elif "text" in label:
            # node_label / segment_label / angle_label — text already tokenized.
            names.append(label["text"])
    return names


# ---------------------------------------------------------------------------
# Canvas extraction
# ---------------------------------------------------------------------------

def _raw_axes_present(tikz: str) -> bool:
    """Return True for common raw TikZ x/y axes through the origin."""
    has_horizontal = False
    has_vertical = False

    for match in _RAW_AXIS_DRAW_RE.finditer(tikz):
        x1, y1, x2, y2 = (float(match.group(i)) for i in range(1, 5))
        if abs(y1 - y2) <= 1e-9 and min(x1, x2) <= 0 <= max(x1, x2) and abs(y1) <= 1e-9:
            has_horizontal = True
        if abs(x1 - x2) <= 1e-9 and min(y1, y2) <= 0 <= max(y1, y2) and abs(x1) <= 1e-9:
            has_vertical = True
        if has_horizontal and has_vertical:
            return True

    return False


def extract_canvas_features(tikz: str) -> dict[str, bool]:
    """
    Extract visible canvas features from TikZ code.

    Currently detects:
      - grid via \\tkzGrid or a common raw-TikZ `grid` draw command
      - axes via \\tkzAxeXY or common raw-TikZ arrowed axes through the origin
    """
    return {
        "grid": bool(_TKZ_GRID_RE.search(tikz) or _RAW_GRID_RE.search(tikz)),
        "axes": bool(_TKZ_AXES_RE.search(tikz) or _raw_axes_present(tikz)),
    }

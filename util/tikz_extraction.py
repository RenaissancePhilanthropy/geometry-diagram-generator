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

# Literal-coordinate fast path: \tkzDefPoint(2.5,3){A}
_DEF_POINT_RE = re.compile(
    rf"\\tkzDefPoint\s*\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)\s*\{{({_POINT_NAME})\}}"
)
_COORDINATE_RE = re.compile(
    rf"\\coordinate\s*\(({_POINT_NAME})\)\s*at\s*\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)"
)

# Slow path for expression-style coords: \tkzDefPoint({...},{...}){B}
# We capture the (potentially nested-parenthesis) coordinate group as a raw
# string and evaluate it via a tiny pgfmath-compatible expression engine.
_DEF_POINT_HEAD_RE = re.compile(r"\\tkzDefPoint\s*\(")
_GET_NAME_AFTER_RE = re.compile(rf"\s*\{{({_POINT_NAME})\}}")

# \pgfmathsetmacro{\name}{expr} — register macro for substitution.
_PGF_SETMACRO_RE = re.compile(r"\\pgfmathsetmacro\s*\{\\(\w+)\}\s*\{([^}]+)\}")


def _read_balanced_parens(source: str, start: int) -> tuple[str, int] | None:
    r"""Read a parenthesized substring starting at ``source[start] == '('``.

    Returns (inner_text_without_outer_parens, index_after_closing_paren), or
    None if parens don't balance. Tracks depth across both ``(`` and ``{``
    so coordinate expressions like ``({\side*cos(-35)},{...})`` parse.
    """
    if start >= len(source) or source[start] != "(":
        return None
    depth = 1
    i = start + 1
    paren_depth = 1
    brace_depth = 0
    while i < len(source) and depth > 0:
        c = source[i]
        if c == "(":
            paren_depth += 1
            depth += 1
        elif c == ")":
            paren_depth -= 1
            depth -= 1
            if depth == 0:
                return source[start + 1 : i], i + 1
        elif c == "{":
            brace_depth += 1
            depth += 1
        elif c == "}":
            brace_depth -= 1
            depth -= 1
        i += 1
    return None


def _split_top_level_comma(s: str) -> list[str]:
    """Split *s* on commas that are not inside ``(``...``)`` or ``{``...``}``."""
    out: list[str] = []
    cur: list[str] = []
    depth = 0
    for c in s:
        if c in "({":
            depth += 1
        elif c in ")}":
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    out.append("".join(cur))
    return [p.strip() for p in out]


def _extract_pgfmath_macros(tikz: str) -> dict[str, float]:
    """Evaluate \\pgfmathsetmacro definitions in source order.

    Macros may reference earlier macros; unresolvable definitions are
    silently skipped (their value stays absent from the table).
    """
    table: dict[str, float] = {}
    for m in _PGF_SETMACRO_RE.finditer(tikz):
        name, expr = m.group(1), m.group(2)
        try:
            table[name] = _eval_pgf_expr(expr, table)
        except Exception:
            continue
    return table


def _eval_pgf_expr(expr: str, macros: dict[str, float]) -> float:
    """Evaluate a pgfmath-style scalar expression to a float.

    Supports:
      - decimal literals, unary minus
      - ``+ - * /`` and parentheses
      - ``cos(d)``, ``sin(d)``, ``tan(d)`` with d in degrees (pgfmath default)
      - ``sqrt(x)``, ``abs(x)``
      - ``\\macro`` references resolved via *macros*

    Raises ValueError on any unsupported construct.
    """
    import ast
    import math

    # Strip surrounding braces ({\side*cos(-35)} -> \side*cos(-35))
    s = expr.strip()
    while s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()

    # Substitute \macro references with their numeric values.
    def _sub(match: re.Match) -> str:
        name = match.group(1)
        if name not in macros:
            raise ValueError(f"undefined macro \\{name}")
        return repr(float(macros[name]))

    s = re.sub(r"\\(\w+)", _sub, s)

    # Parse with Python's ast and walk a restricted node set.
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"parse error: {exc}") from exc

    funcs = {
        "cos": lambda x: math.cos(math.radians(x)),
        "sin": lambda x: math.sin(math.radians(x)),
        "tan": lambda x: math.tan(math.radians(x)),
        "sqrt": math.sqrt,
        "abs": abs,
    }

    def _walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            v = _walk(node.operand)
            if isinstance(node.op, ast.USub):
                return -v
            if isinstance(node.op, ast.UAdd):
                return +v
            raise ValueError(f"unsupported unary op: {type(node.op).__name__}")
        if isinstance(node, ast.BinOp):
            l = _walk(node.left)
            r = _walk(node.right)
            if isinstance(node.op, ast.Add):
                return l + r
            if isinstance(node.op, ast.Sub):
                return l - r
            if isinstance(node.op, ast.Mult):
                return l * r
            if isinstance(node.op, ast.Div):
                return l / r
            if isinstance(node.op, ast.Pow):
                return l ** r
            raise ValueError(f"unsupported binary op: {type(node.op).__name__}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = funcs.get(node.func.id)
            if fn is None:
                raise ValueError(f"unsupported function: {node.func.id}")
            args = [_walk(a) for a in node.args]
            return float(fn(*args))
        raise ValueError(f"unsupported node: {type(node).__name__}")

    return _walk(tree)


def extract_defined_points(tikz: str) -> dict[str, tuple[float, float]]:
    """Extract explicitly defined points from \\tkzDefPoint(x,y){Name} and
    \\coordinate(name) at (x,y) commands. Handles literal-only coordinates
    on the fast path; falls back to a pgfmath-style expression evaluator
    for coordinates wrapped in ``{}`` or containing macro references.
    """
    points: dict[str, tuple[float, float]] = {}

    for m in _DEF_POINT_RE.finditer(tikz):
        x, y, name = float(m.group(1)), float(m.group(2)), m.group(3)
        points[name] = (x, y)

    for m in _COORDINATE_RE.finditer(tikz):
        name, x, y = m.group(1), float(m.group(2)), float(m.group(3))
        points[name] = (x, y)

    macros = _extract_pgfmath_macros(tikz)

    for head in _DEF_POINT_HEAD_RE.finditer(tikz):
        paren_open = head.end() - 1  # the '(' itself
        balanced = _read_balanced_parens(tikz, paren_open)
        if balanced is None:
            continue
        coord_text, after = balanced
        name_match = _GET_NAME_AFTER_RE.match(tikz, after)
        if not name_match:
            continue
        name = name_match.group(1)
        if name in points:
            continue  # literal extractor already got it
        parts = _split_top_level_comma(coord_text)
        if len(parts) != 2:
            continue
        try:
            x = _eval_pgf_expr(parts[0], macros)
            y = _eval_pgf_expr(parts[1], macros)
        except Exception:
            continue
        points[name] = (x, y)

    return points


# ---------------------------------------------------------------------------
# Computed / derived point extraction
# ---------------------------------------------------------------------------

_GET_POINT_RE = re.compile(rf"\\tkzGetPoint\s*\{{({_POINT_NAME})\}}")
# \tkzGetPoints{X}{Y} (plural) — names the two intersection points produced
# by \tkzInterCC or \tkzInterLC.
_GET_POINTS_RE = re.compile(
    rf"\\tkzGetPoints\s*\{{({_POINT_NAME})\}}\s*\{{({_POINT_NAME})\}}"
)
_MID_POINT_RE = re.compile(r"\\tkzDefMidPoint\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)")
_CIRCUM_CENTER_RE = re.compile(
    r"\\tkzCircumCenter\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_INTER_LL_RE = re.compile(
    r"\\tkzInterLL\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)"
)
# \tkzInterCC(O,A)(C,B) — circle through A centered at O, circle through B
# centered at C; the two intersection points are then named via
# \tkzGetPoints{P}{Q}.
_INTER_CC_RE = re.compile(
    r"\\tkzInterCC\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)"
)
# \tkzInterLC(A,B)(O,T) — line AB intersected with circle centered at O
# passing through T.
_INTER_LC_RE = re.compile(
    r"\\tkzInterLC\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)"
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
        r"(\\tkzDefMidPoint|\\tkzCircumCenter|\\tkzInterLL|\\tkzInterCC"
        r"|\\tkzInterLC|\\tkzGetPoints|\\tkzGetPoint"
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

        elif cmd == "\\tkzInterCC":
            m = _INTER_CC_RE.match(rest)
            if m:
                pending = {
                    "type": "inter_cc",
                    "args": [m.group(1), m.group(2), m.group(3), m.group(4)],
                }

        elif cmd == "\\tkzInterLC":
            m = _INTER_LC_RE.match(rest)
            if m:
                pending = {
                    "type": "inter_lc",
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

        elif cmd == "\\tkzGetPoints":
            m = _GET_POINTS_RE.match(rest)
            # \tkzGetPoints names two intersection candidates from the most
            # recent multi-solution computation (\tkzInterCC, \tkzInterLC).
            if m and pending is not None and pending.get("type") in {"inter_cc", "inter_lc"}:
                computed[m.group(1)] = {**pending, "which": 0}
                computed[m.group(2)] = {**pending, "which": 1}
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
    rf"\\tkzMarkRightAngle(?:\[[^\]]*\])?\s*\(\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*\)"
)
_ANGLE_MARK_RE = re.compile(
    rf"\\tkzMarkAngle(?:\[[^\]]*\])?\s*\(\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*\)"
)
_SEGMENT_MARK_RE = re.compile(
    rf"\\tkzMarkSegment(?:\[[^\]]*\])?\s*\(\s*({_POINT_NAME})\s*,\s*({_POINT_NAME})\s*\)"
)


def extract_marks(tikz: str) -> list[dict[str, Any]]:
    """Extract mark commands: right angles, angles, segment tick marks."""
    marks: list[dict[str, Any]] = []

    for m in _RIGHT_ANGLE_RE.finditer(tikz):
        marks.append({
            "type": "right_angle",
            "from": m.group(1),
            "vertex": m.group(2),
            "to": m.group(3),
        })

    for m in _ANGLE_MARK_RE.finditer(tikz):
        marks.append({
            "type": "angle",
            "from": m.group(1),
            "vertex": m.group(2),
            "to": m.group(3),
        })

    for m in _SEGMENT_MARK_RE.finditer(tikz):
        marks.append({"type": "segment_mark", "from": m.group(1), "to": m.group(2)})

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


def extract_labels(tikz: str) -> list[dict[str, Any]]:
    """Extract label commands."""
    labels: list[dict[str, Any]] = []

    for m in _LABEL_POINTS_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        labels.append({"type": "label_points", "points": pts})

    for m in _LABEL_POINT_RE.finditer(tikz):
        labels.append({"type": "label_point", "point": m.group(1), "text": m.group(2)})

    return labels


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

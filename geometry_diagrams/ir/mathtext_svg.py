"""Render LaTeX math strings to self-contained SVG path data using matplotlib's
built-in mathtext engine.

No LaTeX binary required. matplotlib is already a project dependency.

Public API
----------
MathGlyph
    Dataclass holding the SVG path ``d`` string and accurate bounding box.
render_math_to_svg(latex, font_size) -> MathGlyph | None
    Convert a LaTeX math string to an SVG path. Returns ``None`` on failure
    so callers can fall back gracefully to the existing ``<tspan>`` path.
label_needs_mathtext(text) -> bool
    Classifier that decides whether a label string should be rendered via
    mathtext (True) or the brand font ``<text>`` path (False).

Design notes
------------
* Paths are returned at the requested ``font_size`` in SVG pixels. matplotlib's
  ``TextToPath`` emits vertices at ``FONT_SCALE = 100`` units (dimensionless),
  so every coordinate is multiplied by ``font_size / 100`` and the y-axis is
  flipped (SVG has y-down; mathtext has y-up).
* ``mathtext.fontset`` defaults to ``'cm'`` (Computer Modern) which closely
  matches the LaTeX look.  Override with the ``MATHTEXT_FONTSET`` env var.
* The ``TextToPath`` instance is module-level (creation is non-trivial).
  Individual renders are memoised by ``(stripped_latex, font_size)`` so
  calling the same expression at the same size is free on repeat.
"""
from __future__ import annotations

import functools
import os
import re
from dataclasses import dataclass

import matplotlib as mpl
import matplotlib.font_manager as mfm
from matplotlib.textpath import TextToPath
from matplotlib.path import Path as MplPath

# ---------------------------------------------------------------------------
# matplotlib runtime config
# ---------------------------------------------------------------------------

# Use a non-interactive backend so the module works in any server context.
mpl.use("Agg")

# Let the user override the math fontset (default: cm = Computer Modern).
_FONTSET = os.environ.get("MATHTEXT_FONTSET", "cm")
mpl.rcParams["mathtext.fontset"] = _FONTSET

# Module-level TextToPath instance — reusable, creation is non-trivial.
_T2P = TextToPath()

# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MathGlyph:
    """Rendered math label as an SVG path with accurate bounding box.

    Attributes
    ----------
    d : str
        SVG path data string (commands M, L, Q, C, Z only; y-axis already
        flipped for SVG coordinates).
    width : float
        Horizontal extent in SVG pixels.
    height : float
        Vertical extent in SVG pixels.
    x_min : float
        Left edge of the bounding box in the path's local coordinate system
        (origin is the leftmost point of the baseline).
    y_min : float
        Top edge of the bounding box in SVG pixels (most negative y value in
        SVG space, i.e. the highest pixel row).
    """
    d: str
    width: float
    height: float
    x_min: float
    y_min: float


# ---------------------------------------------------------------------------
# Internal: path conversion
# ---------------------------------------------------------------------------

def _verts_codes_to_svg_d(verts: list, codes: list, scale: float) -> str:
    """Convert matplotlib path verts/codes to an SVG path d string.

    The y-axis is flipped (multiply by -1) to match SVG coordinate convention
    (y increases downward).  All coordinates are scaled by *scale*.

    Only the four code types produced by matplotlib's mathtext engine are
    handled: MOVETO, LINETO, CURVE3 (quadratic Bézier), CLOSEPOLY.
    """
    parts: list[str] = []
    i = 0
    n = len(codes)
    while i < n:
        c = int(codes[i])
        if c == MplPath.MOVETO:
            x, y = verts[i]
            parts.append(f"M{x * scale:.4f} {-y * scale:.4f}")
            i += 1
        elif c == MplPath.LINETO:
            x, y = verts[i]
            parts.append(f"L{x * scale:.4f} {-y * scale:.4f}")
            i += 1
        elif c == MplPath.CURVE3:
            # Quadratic Bézier: one control point + one endpoint
            if i + 1 >= n:
                i += 1
                continue
            x1, y1 = verts[i]
            x2, y2 = verts[i + 1]
            parts.append(
                f"Q{x1 * scale:.4f} {-y1 * scale:.4f} "
                f"{x2 * scale:.4f} {-y2 * scale:.4f}"
            )
            i += 2
        elif c == MplPath.CURVE4:
            # Cubic Bézier: two control points + one endpoint
            if i + 2 >= n:
                i += 1
                continue
            x1, y1 = verts[i]
            x2, y2 = verts[i + 1]
            x3, y3 = verts[i + 2]
            parts.append(
                f"C{x1 * scale:.4f} {-y1 * scale:.4f} "
                f"{x2 * scale:.4f} {-y2 * scale:.4f} "
                f"{x3 * scale:.4f} {-y3 * scale:.4f}"
            )
            i += 3
        elif c == MplPath.CLOSEPOLY:
            parts.append("Z")
            i += 1
        else:
            # STOP or unknown — skip
            i += 1
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public: render
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=512)
def render_math_to_svg(latex: str, font_size: float) -> MathGlyph | None:
    """Render *latex* to a self-contained SVG path at *font_size* pixels.

    Parameters
    ----------
    latex : str
        LaTeX math string, optionally wrapped in ``$...$``.  Plain text
        (no ``$`` and no ``\\`` commands) is also accepted and rendered in
        the math font.
    font_size : float
        Target glyph height in SVG pixels.

    Returns
    -------
    MathGlyph | None
        On success, a :class:`MathGlyph` with path data and accurate bbox.
        On failure (empty input, mathtext parse error), returns ``None`` so
        callers can fall back gracefully.
    """
    # --- normalise input ---
    # matplotlib's get_text_path requires $...$ delimiters even when ismath=True;
    # without them, \theta renders as the literal text "theta" with a radical prefix.
    stripped = latex.strip()
    if not stripped:
        return None

    # Ensure $...$ wrapping for the mathtext call.
    if stripped.startswith("$") and stripped.endswith("$") and len(stripped) > 2:
        mathtext_input = stripped
    else:
        mathtext_input = f"${stripped}$"

    # --- substitute commands unsupported by matplotlib mathtext ---
    # \square and \Box → unicode open square (□); matplotlib raises ParseFatalException.
    # \lvert / \rvert → plain | (AMS delimiter variant, not in matplotlib's parser).
    mathtext_input = (
        mathtext_input
        .replace(r"\square", "□")
        .replace(r"\Box", "□")
        .replace(r"\lvert", "|")
        .replace(r"\rvert", "|")
    )

    # --- render via matplotlib mathtext ---
    fp = mfm.FontProperties(size=font_size)
    try:
        verts, codes = _T2P.get_text_path(fp, mathtext_input, ismath=True)
    except Exception:
        return None

    if not verts or not codes:
        return None

    # --- convert to SVG path ---
    scale = font_size / _T2P.FONT_SCALE  # FONT_SCALE = 100
    d = _verts_codes_to_svg_d(verts, codes, scale)

    if not d:
        return None

    # --- compute bounding box in SVG pixel space ---
    # Vertices are still in mathtext space (y-up); after the flip they become y-down.
    xs = [v[0] * scale for v in verts]
    ys = [-v[1] * scale for v in verts]  # flipped for SVG
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    width = x_max - x_min
    height = y_max - y_min

    if width <= 0 or height <= 0:
        return None

    return MathGlyph(d=d, width=width, height=height, x_min=x_min, y_min=y_min)


# ---------------------------------------------------------------------------
# Public: routing classifier
# ---------------------------------------------------------------------------

# LaTeX commands that require the mathtext engine for correct rendering.
# Anything not in this list that also has no \command stays in the brand font.
_MATHTEXT_COMMANDS = frozenset({
    # Fractions / radicals
    "frac", "dfrac", "tfrac", "cfrac", "sqrt",
    # Vector / accent commands
    "vec", "hat", "bar", "dot", "ddot", "tilde",
    "widehat", "widetilde", "overrightarrow", "overleftarrow",
    "overline", "underline",
    # Large operators
    "sum", "int", "oint", "prod", "coprod", "bigcup", "bigcap",
    "bigoplus", "bigotimes", "lim", "max", "min", "sup", "inf",
    # Geometric symbols
    "angle", "measuredangle", "sphericalangle",
    "triangle", "square",
    # Greek letters (both cases)
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon",
    "zeta", "eta", "theta", "vartheta", "iota", "kappa",
    "lambda", "mu", "nu", "xi", "pi", "varpi", "rho", "varrho",
    "sigma", "varsigma", "tau", "upsilon", "phi", "varphi",
    "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi",
    "Sigma", "Upsilon", "Phi", "Psi", "Omega",
    # Arrows
    "rightarrow", "leftarrow", "Rightarrow", "Leftarrow",
    "leftrightarrow", "Leftrightarrow",
    "longrightarrow", "longleftarrow",
    # Relations / operators
    "cdot", "times", "div", "pm", "mp",
    "leq", "geq", "neq", "approx", "equiv", "sim", "cong",
    "subset", "supset", "in", "notin", "perp", "parallel",
    # Accents / decorators
    "acute", "grave", "check", "breve",
    # Misc math
    "infty", "partial", "nabla", "forall", "exists",
    "circ", "degree",
    "text", "mathrm", "mathbf", "mathit", "boldsymbol",
    # Delimiters that require real math
    "left", "right", "bigl", "bigr", "Bigl", "Bigr",
})

# Pattern to detect nested subscripts (x_{i_j}) — two or more _ or ^ within braces
_NESTED_SCRIPT_RE = re.compile(r"[_^]\{[^}]*[_^]")


def label_needs_mathtext(text: str) -> bool:
    """Return True if *text* requires the mathtext engine for correct rendering.

    Plain labels (Latin letters, digits, simple punctuation, single-level
    subscripts/superscripts in ASCII) stay in the brand font.  Anything with
    LaTeX commands, Greek, fractions, radicals, nested scripts, or geometry
    symbols routes to mathtext.

    Parameters
    ----------
    text : str
        Raw label string (with or without ``$...$`` delimiters).

    Returns
    -------
    bool
        ``True``  → render via :func:`render_math_to_svg`.
        ``False`` → render via the existing ``<text>``/``<tspan>`` path.
    """
    stripped = text.strip()

    # Empty → no content, let caller decide (treated as False)
    if not stripped:
        return False

    # If the whole string is wrapped in $...$, it's explicitly marked as math.
    if stripped.startswith("$") and stripped.endswith("$") and len(stripped) > 2:
        inner = stripped[1:-1].strip()
        # A bare single ASCII letter in $...$ (e.g. "$A$") could stay in brand
        # font for point names. But for consistency with LaTeX output (italic
        # serif), route to mathtext — this is the geometry convention.
        # Callers may override this decision for purely-plain-text contexts.
        return True

    # Any LaTeX command triggers mathtext
    commands = re.findall(r"\\([A-Za-z]+)", stripped)
    for cmd in commands:
        if cmd in _MATHTEXT_COMMANDS:
            return True
    # Unknown \commands also route to mathtext (better than leaking literal names)
    if commands:
        return True

    # Nested subscript/superscript (x_{i_j})
    if _NESTED_SCRIPT_RE.search(stripped):
        return True

    # Plain ASCII label with optional single-level _ or ^ (e.g. "P_1", "x^2")
    # These render fine in the brand font.
    return False

"""Check right-angle marks and angle labels against the angle that is actually drawn.

A `MarkRightAngles` square or a `LabelAngle` text such as "35°" is decoration: nothing else
ties it to the geometry, so a script can draw an oblique angle with a right-angle mark or
label a 41° angle "35°". `audit_angles` measures each marked angle from the compiled points
and reports the ones whose stated value is off by more than a tolerance (`TOLERANCE_DEG`, 1°,
unless the caller passes another). `AnglePolicy` says what the pipeline does with the findings.

Only a label that is exactly one angle value is read: "35°", "∠B = 60°", "θ = 2π/3",
"1.047 rad". Anything else ("x", "?", a bare "35", a derivation with several numbers, text
that merely contains a number) is left alone, because it either states no value or states
one for something other than the angle it sits on.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

import sympy.geometry as spg

from . import ir

# Degrees. Labels are rounded for display ("37°" for 36.87°), and a script's own points may
# be rounded too, so a whole degree is the smallest difference worth reporting.
TOLERANCE_DEG = 1.0
# With the "retry" mode, only a mismatch larger than this fails an attempt; anything between
# the two thresholds is still reported, as a warning. A figure drawn slightly off, or marked
# loosely, should not cost a retry, but a 40° label on a 90° angle should.
FAIL_TOLERANCE_DEG = 5.0

ANGLE_CHECK_MODES: tuple[str, ...] = ("off", "warn", "retry")

_NUMBER = r"\d+(?:\.\d+)?"
_NAME = r"(?:m\s*)?(?:angle\s+)?∠?\s*[^\W\d_][\w'′]{0,5}"
_PREFIX = re.compile(rf"^\s*{_NAME}\s*=\s*")
_DEGREES = re.compile(rf"^\(?\s*({_NUMBER})\s*(?:°|º|˚|deg(?:rees)?)\s*\)?$", re.IGNORECASE)
_PI_FORM = re.compile(
    rf"^\(?\s*(?:({_NUMBER})\s*\*?\s*)?(?:π|pi)(?:\s*/\s*({_NUMBER}))?\s*(?:rad(?:ians?)?)?\s*\)?$",
    re.IGNORECASE,
)
_RADIANS = re.compile(rf"^\(?\s*({_NUMBER})\s*rad(?:ians?)?\s*\)?$", re.IGNORECASE)


def parse_angle_text(text: str) -> float | None:
    """The angle in degrees that `text` states, or None if it is not exactly one angle value."""
    body = _PREFIX.sub("", text, count=1) if "=" in text else text
    if "=" in body:  # a chain such as "∠A = 180° − 40° − 40° = 100°" states no single value
        return None
    if m := _DEGREES.match(body):
        return float(m.group(1))
    if m := _PI_FORM.match(body):
        numerator = float(m.group(1)) if m.group(1) else 1.0
        denominator = float(m.group(2)) if m.group(2) else 1.0
        return None if denominator == 0 else math.degrees(math.pi * numerator / denominator)
    if m := _RADIANS.match(body):
        return math.degrees(float(m.group(1)))
    return None


@dataclass(frozen=True)
class AnglePolicy:
    """What the pipeline does with the audit.

    mode "off": do not audit. "warn": report every finding above `tolerance_deg` as a
    warning and never fail. "retry": the same, and a finding above `fail_tolerance_deg`
    also fails the attempt, so the strategy retries with it in the prompt.
    """
    mode: Literal["off", "warn", "retry"] = "warn"
    tolerance_deg: float = TOLERANCE_DEG
    fail_tolerance_deg: float = FAIL_TOLERANCE_DEG

    def __post_init__(self) -> None:
        if self.mode not in ANGLE_CHECK_MODES:
            raise ValueError(f"angle_check must be one of {', '.join(ANGLE_CHECK_MODES)}, got {self.mode!r}")
        for name in ("tolerance_deg", "fail_tolerance_deg"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"angle_{name} must be a finite number greater than 0, got {value!r}")
        if self.fail_tolerance_deg < self.tolerance_deg:
            raise ValueError(
                f"angle_fail_tolerance_deg ({self.fail_tolerance_deg}) must not be smaller than "
                f"angle_tolerance_deg ({self.tolerance_deg})"
            )


@dataclass(frozen=True)
class AngleFinding:
    """One mark or label whose stated angle differs from the drawn angle."""
    kind: Literal["right_angle_mark", "angle_label"]
    angle: tuple[str, str, str]  # point ids a, o, b: the angle at o from ray oa to ray ob
    stated_deg: float
    drawn_deg: float
    message: str

    @property
    def error_deg(self) -> float:
        """How far the stated value is from the drawn angle, in degrees."""
        return abs(self.drawn_deg - self.stated_deg)


def _drawn_angle(sym: dict, angle: ir.AnglePoints, reflex: bool = False) -> float | None:
    points = []
    for point_id in (angle.a, angle.o, angle.b):
        obj = sym.get(point_id)
        if not isinstance(obj, spg.Point):
            return None
        points.append((float(obj.x), float(obj.y)))
    (ax, ay), (ox, oy), (bx, by) = points
    v1, v2 = (ax - ox, ay - oy), (bx - ox, by - oy)
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < 1e-12 or n2 < 1e-12:
        return None
    cosine = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    degrees = math.degrees(math.acos(cosine))
    return 360.0 - degrees if reflex else degrees


def audit_angles(
    diagram: ir.DiagramIR, sym: dict[str, Any], tolerance_deg: float = TOLERANCE_DEG,
) -> list[AngleFinding]:
    """Findings for every right-angle mark and parseable angle label that disagrees with the
    compiled geometry by more than `tolerance_deg`, in render order. A mark or label whose
    points are not all compiled points is skipped, as is a degenerate angle. Arc marks
    (`MarkAngles`), whatever group they carry, are never read: a group is a rendering tag,
    and a figure may use it for something other than "these are equal"."""
    names = {op.p: op.text for op in diagram.render if isinstance(op, ir.LabelPoint) and op.text}

    def show(angle: ir.AnglePoints) -> str:
        return "∠" + "".join(names.get(p, p) if len(names.get(p, p)) == 1 else f"({names.get(p, p)})"
                             for p in (angle.a, angle.o, angle.b))

    findings: list[AngleFinding] = []
    for op in diagram.render:
        if isinstance(op, ir.MarkRightAngles):
            for angle in op.angles:
                drawn = _drawn_angle(sym, angle)
                if drawn is not None and abs(drawn - 90.0) > tolerance_deg:
                    findings.append(AngleFinding(
                        "right_angle_mark", (angle.a, angle.o, angle.b), 90.0, drawn,
                        f"Right-angle mark on {show(angle)}, which is drawn at {drawn:.1f}°, not 90°",
                    ))
        elif isinstance(op, ir.LabelAngle):
            stated = parse_angle_text(op.text)
            if stated is None:
                continue
            drawn = _drawn_angle(sym, op.angle, reflex=op.which == "reflex")
            if drawn is not None and abs(drawn - stated) > tolerance_deg:
                findings.append(AngleFinding(
                    "angle_label", (op.angle.a, op.angle.o, op.angle.b), stated, drawn,
                    f'Angle label "{op.text}" is on {show(op.angle)}, which is drawn at {drawn:.1f}°',
                ))
    return findings

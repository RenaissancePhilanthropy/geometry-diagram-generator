"""
Render-free auto-grade for the Phase-0 capability gate.

Takes a model's raw text completion and runs it through the project's real
pipeline as far as it can go:

    extract JSON  ->  RecipeDSL.model_validate  ->  lower_to_ir
                  ->  compile_defs              ->  run_checks (+ angle triples)

No Docker renderer is needed: a construction is "valid" if it compiles to SymPy
geometry and satisfies every ``must``-level check. This mirrors strategies/
structured.py::_run_ir_pipeline up to (but not including) the render step.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass

# allow `from recipe...` / `from ir...` when imported from anywhere in the repo
REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Pipeline stages, in order. A grade reports the furthest stage reached.
STAGES = ("parse", "validate", "lower", "compile", "check", "success")


@dataclass
class GradeResult:
    ok: bool                 # True iff the construction reached "success"
    stage: str               # furthest stage reached / where it failed (see STAGES)
    error: str | None = None  # failure message, if any
    n_ops: int | None = None  # number of construction ops, once parsed
    must_failures: int = 0    # count of failed must-level geometric checks

    @property
    def summary(self) -> str:
        if self.ok:
            return f"OK ({self.n_ops} ops)"
        tail = f": {self.error}" if self.error else ""
        return f"FAIL@{self.stage}{tail}"


def extract_recipe_json(text: str) -> dict | None:
    """Best-effort pull of the RecipeDSL JSON object out of a model completion.

    The local model emits free text — it may wrap the JSON in a ```json fence,
    precede it with reasoning, or (ideally) emit a bare object. Strategy:
      1. Prefer a fenced ```json ... ``` (or plain ``` ... ```) block.
      2. Otherwise scan for the first balanced-brace object that parses as JSON
         and contains a "construction" key.
    Returns the parsed dict, or None if nothing usable is found.
    """
    candidates: list[str] = []

    # 1) fenced code blocks
    fence = "```"
    idx = 0
    while True:
        start = text.find(fence, idx)
        if start == -1:
            break
        nl = text.find("\n", start)
        if nl == -1:
            break
        end = text.find(fence, nl + 1)
        if end == -1:
            break
        candidates.append(text[nl + 1 : end])
        idx = end + len(fence)

    # 2) balanced-brace scan over the whole text (catches un-fenced objects)
    candidates.extend(_balanced_objects(text))

    for blob in candidates:
        blob = blob.strip()
        if not blob:
            continue
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "construction" in obj:
            return obj
    return None


def _balanced_objects(text: str) -> list[str]:
    """Yield substrings that are balanced { ... } objects (string-aware)."""
    out: list[str] = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    out.append(text[start : i + 1])
    return out


def grade_completion(text: str) -> GradeResult:
    """Grade a single model completion through the render-free pipeline."""
    import pydantic

    from recipe.dsl import RecipeDSL
    from recipe.lower import lower_to_ir, LoweringError
    from ir.to_sympy import compile_defs
    from ir.errors import IRCompileError
    from ir.checks import run_checks, check_render_angles

    obj = extract_recipe_json(text)
    if obj is None:
        return GradeResult(ok=False, stage="parse", error="no RecipeDSL JSON found in output")

    try:
        dsl = RecipeDSL.model_validate(obj)
    except pydantic.ValidationError as e:
        return GradeResult(ok=False, stage="validate", error=_short(e))

    n_ops = len(dsl.construction)

    try:
        diagram_ir = lower_to_ir(dsl)
    except (LoweringError, pydantic.ValidationError) as e:
        return GradeResult(ok=False, stage="lower", error=_short(e), n_ops=n_ops)

    try:
        sym = compile_defs(diagram_ir)
    except IRCompileError as e:
        return GradeResult(ok=False, stage="compile", error=_short(e), n_ops=n_ops)

    results = run_checks(diagram_ir.checks, sym)
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    angle_errors = check_render_angles(diagram_ir, sym)

    if must_failures or angle_errors:
        msgs = [r.message for r in must_failures] + list(angle_errors)
        return GradeResult(
            ok=False,
            stage="check",
            error="; ".join(msgs[:3]),
            n_ops=n_ops,
            must_failures=len(must_failures),
        )

    return GradeResult(ok=True, stage="success", n_ops=n_ops)


def _short(exc: Exception, limit: int = 240) -> str:
    s = str(exc).replace("\n", " ").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"

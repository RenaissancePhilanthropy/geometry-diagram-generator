"""Self-reported, metadata-first confidence for the recipe strategy.

The generation model is asked to emit a structured self-assessment of its own
confidence BEFORE it commits to the construction. Two elicitation methods share
one schema (`EvaluationMetadata`):

- **soft** (structured field): `evaluation_metadata` is the FIRST field of the
  `RecipeGenerationOutput` wrapper around `RecipeDSL`. Schema field order makes
  the model emit the metadata before it can emit any construction op — a soft
  "metadata-before-construction" guarantee that preserves pydantic-ai's
  structured-output validation + auto-retry.
- **hard** (fenced prelude): a separate, independent `output_type=str` call emits
  a `[[INTERNAL_METADATA]] ... [[END_METADATA]]` fence containing the same JSON
  schema. Because the metadata is produced in a call with no construction tokens
  at all, this is the harder ordering guarantee. The prelude call is independent
  of the generation call (no shared context), so the hard score is not anchored
  to the soft score — the two are directly comparable per record.

`confidence_mode` selects which method(s) run:
- `none`      — no metadata (current behavior; control baseline)
- `structured`— soft only (1 generation call)
- `prelude`   — hard only (prelude call + plain `RecipeDSL` generation call)
- `both`      — hard + soft (prelude call + `RecipeGenerationOutput` generation
                call); records both scores for direct comparison

The metadata is a PROSPECTIVE PREDICTION (the model assesses before it builds),
not a retrospective review — that is the point of emitting it first, and it is
what distinguishes this from the post-hoc LLM judge / deterministic CoT analyzer
(which review an artifact the model already committed to and tend to rationalize
it). Forced self-report always fills scores even without basis; the three
independent dimensions let later analysis see which (if any) track actual
correctness. Recording is cheap; calibration/discrimination analysis is a later
pass (eval ground-truth labels: compile success, checks, judge).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from recipe.dsl import RecipeDSL

logger = logging.getLogger(__name__)

# Fence markers used by the hard (prelude) elicitation method.
FENCE_START = "[[INTERNAL_METADATA]]"
FENCE_END = "[[END_METADATA]]"


# ---------------------------------------------------------------------------
# Shared schema (used by both elicitation methods)
# ---------------------------------------------------------------------------

class DimensionScore(BaseModel):
    """One confidence dimension: a 0-100 score plus machine-readable flag tags."""
    model_config = ConfigDict(extra="ignore")

    confidence_score: int = Field(ge=0, le=100)
    flags: list[str] = Field(default_factory=list)


class EvaluationMetadata(BaseModel):
    """Self-reported confidence, emitted before the construction.

    Three INDEPENDENT dimensions (0 = no confidence, 100 = certain):
      - geometric_correctness: will the construction compile and satisfy the
        stated geometric properties / be internally consistent?
      - request_ambiguity:      is the request under-specified or ambiguous?
        (higher score = clearer request)
      - end_to_end:             overall, will the user receive a correct,
        legible diagram?
    Plus a contradiction flag for impossible/inconsistent request constraints.
    """
    model_config = ConfigDict(extra="ignore")

    geometric_correctness: DimensionScore
    request_ambiguity: DimensionScore
    end_to_end: DimensionScore
    contradictions_found: bool
    contradiction_detail: list[str] = Field(default_factory=list)


class RecipeGenerationOutput(BaseModel):
    """Wrapper used as `output_type` for the soft (structured) elicitation.

    `evaluation_metadata` is the FIRST field so the model emits it before the
    `recipe` construction (anti-anchoring via schema field order). `recipe`
    stays a structured `RecipeDSL` sub-object — no string-escaping — so
    pydantic-ai validation + auto-retry apply to both halves.
    """
    model_config = ConfigDict(extra="forbid")

    evaluation_metadata: EvaluationMetadata
    recipe: RecipeDSL


# ---------------------------------------------------------------------------
# Instruction text
# ---------------------------------------------------------------------------

# The output-format line that used to live in RECIPE_GENERATION_SYSTEM. It was
# extracted out so the generation system prompt carries only rules (no output
# format) — that way the SAME system prompt can be reused for the prelude without
# feeding it a confusing "output RecipeDSL" instruction (which caused the prelude
# to emit a construction instead of the metadata fence). The real generation
# call's output format is enforced by `output_type` + the user-message "## Output"
# section, so this line is redundant there. Kept as a constant so the pre-GEPA
# override arm (whose generation_system still embeds it) can be stripped at
# runtime via strip_generation_output_instruction().
GEN_OUTPUT_INSTRUCTION_LINE = (
    "Output ONLY valid JSON that parses as RecipeDSL — no markdown fences, no "
    "prose, no comments."
)


def strip_generation_output_instruction(system: str) -> str:
    """Remove the generation output-format line from a system prompt if present.

    The on-disk RECIPE_GENERATION_SYSTEM no longer carries it, but the pre-GEPA
    override arm's generation_system does; stripping at runtime keeps the prelude
    drift-free in both arms. Collapses the blank line left behind.
    """
    if not system:
        return system
    out = system.replace(GEN_OUTPUT_INSTRUCTION_LINE, "")
    # Collapse the doubled blank line the removal can leave.
    out = re.sub(r"\n\n\n+", "\n\n", out)
    return out


# Shared metadata schema + dimension descriptions, used by both the soft
# (structured, METADATA_INSTRUCTION) and hard (fenced, PRELUDE_OUTPUT_INSTRUCTION)
# elicitation instructions so the two stay in sync.
_METADATA_SCHEMA = """\
{
  "geometric_correctness": {"confidence_score": 0-100, "flags": [str, ...]},
  "request_ambiguity":      {"confidence_score": 0-100, "flags": [str, ...]},
  "end_to_end":             {"confidence_score": 0-100, "flags": [str, ...]},
  "contradictions_found": true|false,
  "contradiction_detail": [str, ...]
}"""

_METADATA_DIMENSIONS = """\
Dimensions (each INDEPENDENT, 0 = no confidence, 100 = certain):
- geometric_correctness: will the construction compile and satisfy the stated
  geometric properties / be internally consistent? Lower it if you anticipate
  resolution, intersection-disambiguation, or numerical-consistency problems.
- request_ambiguity: is the request under-specified or ambiguous (e.g. a
  position described only qualitatively, an undefined intersection branch)?
  Higher score = clearer request.
- end_to_end: overall, will the user receive a correct, legible diagram?
- contradictions_found: does the request contain impossible/contradictory
  constraints (e.g. a triangle both equilateral and right)? List them in
  contradiction_detail.
- flags: short, machine-readable tags naming the specific concern
  (e.g. "undefined-intersection-branch", "qualitative-placement",
  "possible-degeneracy"). Empty list if none."""

# Soft elicitation: prepended to the generation system prompt for structured/both
# modes. evaluation_metadata is the FIRST field of the structured output, emitted
# before the recipe construction (anti-anchoring via schema field order).
METADATA_INSTRUCTION = f"""\
## Self-Reported Confidence (emit FIRST, before the construction)

Your response's FIRST field is `evaluation_metadata` — a self-assessment you
MUST complete BEFORE you design or emit the construction. This is a prospective
prediction, not a review of an artifact you already produced. Be honest; low
scores are fine and useful.

`evaluation_metadata` schema:
{_METADATA_SCHEMA}

{_METADATA_DIMENSIONS}

Complete `evaluation_metadata` fully, THEN emit the `recipe` construction.
"""

# Hard elicitation: appended to the prelude USER message as its "## Output"
# section (the prelude's system prompt is the generation rules, output-stripped,
# so its input matches the real call as closely as possible — only the output
# format differs: the fence instead of a RecipeDSL construction).
PRELUDE_OUTPUT_INSTRUCTION = f"""\
## Output
Respond EXACTLY in this format and NOTHING else:
[[INTERNAL_METADATA]]
{{valid JSON matching the schema below}}
[[END_METADATA]]

Do NOT emit a RecipeDSL construction, TikZ code, or any JSON other than the
metadata block above. The DSL reference and examples above are context for your
assessment, NOT a request to construct. Output ONLY the fenced metadata block.

Schema:
{_METADATA_SCHEMA}

{_METADATA_DIMENSIONS}

Be honest; low scores are fine and useful. Emit ONLY the fenced JSON block.
"""


# ---------------------------------------------------------------------------
# Fence parser (hard / prelude elicitation)
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*)\n```\s*$", re.S)


def _strip_code_fence(text: str) -> str:
    """Strip a single surrounding ```json ... ``` markdown fence if present."""
    m = _CODE_FENCE_RE.match(text)
    return m.group(1).strip() if m else text.strip()


def _coerce_metadata(obj: Any) -> EvaluationMetadata | None:
    """Validate a parsed object as EvaluationMetadata, tolerating minor shape issues.

    Tolerates: missing optional list fields, `flags`/`contradiction_detail` given
    as None, and extra keys (stripped by the model_config). Returns None on
    unrecoverable shape mismatch.
    """
    try:
        return EvaluationMetadata.model_validate(obj)
    except ValidationError:
        return None


def parse_metadata_fence(text: str | None) -> EvaluationMetadata | None:
    """Parse the hard (fenced) metadata block out of a prelude call's text output.

    Looks for a `[[INTERNAL_METADATA]] ... [[END_METADATA]]` block. If absent,
    falls back to treating the whole text (minus any markdown code fence) as the
    JSON body, then to the first `{...}` substring. Repair attempts are
    best-effort; returns None when nothing parses to a valid EvaluationMetadata.
    Never raises.
    """
    if not text or not text.strip():
        return None

    body: str | None = None
    start = text.find(FENCE_START)
    end = text.rfind(FENCE_END)
    if start != -1 and end != -1 and end > start:
        body = text[start + len(FENCE_START):end].strip()

    if body is None:
        # No fence markers — try the whole text as the JSON body.
        body = text.strip()

    body = _strip_code_fence(body)

    # Attempt 1: direct parse + validate.
    try:
        return _coerce_metadata(json.loads(body))
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 2: extract the first balanced {...} substring and retry.
    m = re.search(r"\{.*\}", body, re.S)
    if m:
        try:
            return _coerce_metadata(json.loads(m.group(0)))
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning(
        "Prelude metadata fence did not parse to EvaluationMetadata. Raw head: %r",
        (text or "")[:200],
    )
    return None


def geo_correctness_score(meta: dict | None) -> int | None:
    """Convenience: pull the geometric_correctness confidence_score from a
    serialized EvaluationMetadata dict (or None). For flat eval-record fields."""
    if not isinstance(meta, dict):
        return None
    gc = meta.get("geometric_correctness")
    if not isinstance(gc, dict):
        return None
    score = gc.get("confidence_score")
    return int(score) if isinstance(score, (int, float)) else None
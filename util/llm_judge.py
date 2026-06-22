"""
LLM-as-judge evaluation for geometry diagram quality.

Provides two evaluation modes:
  - Mode 1 (judge_tikz_code): Reviews TikZ source code without rendering.
    Cheap (~$0.002/judgment with claude-sonnet-4-6). Default for eval runs.
  - Mode 2 (judge_rendered_diagram): Reviews the rendered SVG as a PNG image.
    More thorough but requires cairosvg and is ~3x more expensive.
    Enabled via --visual-judge flag in eval runner.
"""
from __future__ import annotations

import json
import re
import logfire  # used only by the commented-out instrumentation below
# from logfire import ConsoleOptions  # uncomment with the verbose console option below

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from strategies.base import DEFAULT_AGENT_MODEL, cache_model_settings

_CODE_REVIEW_SYSTEM = """\
You are an expert geometry teacher and TikZ/tkz-euclide code reviewer.

Given a user's geometry prompt and the generated TikZ code, evaluate the code
on these four dimensions (each 1-5):

1. geometric_accuracy: Do the coordinates and relationships correctly implement
   the described geometry? For example, if a right angle at B is requested, are
   the vectors BA and BC actually perpendicular based on the coordinates?

2. labeling: Are all requested points, lines, and angles labeled, and are the
   labels positioned sensibly (not overlapping, not off-diagram)?

3. completeness: Does the code address every part of the user's request?
   Missing elements (e.g., a requested circle that isn't drawn) reduce this score.

4. likely_renders: On a 1-5 scale — how confident are you this code will
   compile cleanly with LuaLaTeX + tkz-euclide? 5 = very likely, 1 = will fail.

Also give an overall score (1-5) and a one-sentence reasoning string.
"""

_VISUAL_REVIEW_SYSTEM = """\
You are an expert geometry teacher reviewing rendered geometry diagrams.

You will be shown a rendered geometry diagram (as an image) and the original
user prompt that generated it. Evaluate the diagram on four dimensions (1-5):

1. geometric_accuracy: Does the diagram correctly represent the described
   geometry? Are angles, lengths, and relationships visually correct?

2. labeling: Are all requested points, lines, and angles labeled? Are labels
   readable and positioned well?

3. completeness: Does the diagram address every part of the user's request?

4. visual_quality: Is the diagram clear, well-proportioned, and readable?
   Are elements too small, too large, or overlapping?

Be harsh but fair in your evaluation. Correctness should be most heavily weighted, but poor visual quality can also reduce the overall score.

Also give an overall score (1-5) and a one-sentence reasoning string.
"""


class _JudgeResult(BaseModel):
    geometric_accuracy: int
    labeling: int
    completeness: int
    likely_renders: int
    score: int
    reasoning: str


class _VisualJudgeResult(BaseModel):
    geometric_accuracy: int
    labeling: int
    completeness: int
    visual_quality: int
    score: int
    reasoning: str


_LABEL_TO_KEY = {
    "geometric accuracy": "geometric_accuracy",
    "labeling": "labeling",
    "completeness": "completeness",
    "visual quality": "visual_quality",
    "overall score": "score",
}

_SCORE_PATTERN = re.compile(
    r"(" + "|".join(re.escape(k) for k in _LABEL_TO_KEY) + r")\s*:\s*(\d+)",
    re.IGNORECASE,
)


def _parse_visual_response(text: str) -> dict:
    """Parse a free-text judge response into a structured scores dict.

    Extracts scores for geometric_accuracy, labeling, completeness,
    visual_quality, and overall score. Missing scores default to 3.
    All scores are clamped to [1, 5].
    """
    scores: dict[str, int] = {}
    for match in _SCORE_PATTERN.finditer(text):
        label = match.group(1).lower()
        key = _LABEL_TO_KEY[label]
        value = max(1, min(5, int(match.group(2))))
        scores[key] = value

    defaults = ["geometric_accuracy", "labeling", "completeness", "visual_quality", "score"]
    for key in defaults:
        scores.setdefault(key, 3)

    scores["reasoning"] = text
    return scores


async def judge_tikz_code(
    prompt: str,
    tikz_code: str,
    tkzelements_code: str | None = None,
    model: str = "openai:Qwen3.6-35B-A3B-Q8K.gguf",  #"ollama:gemma4:latest", # gemma4:31b-cloud",#qwen3-coder-next:cloud",#"openrouter:google/gemma-4-31b-it:free", #deepseek/deepseek-v4-flash:free",# "anthropic:claude-sonnet-4-6",
    enable_cache: bool = False,
) -> dict:
    """
    Ask an LLM to judge whether the TikZ code correctly implements the
    geometry prompt. No rendering required.

    Returns a dict with keys:
      score, geometric_accuracy, labeling, completeness, likely_renders, reasoning
    """

    # --- Logfire / pydantic-ai instrumentation (OFF by default) ---
    # Uncomment to troubleshoot agent runs. Two knobs matter:
    #   - send_to_logfire=False : no Logfire cloud export (no `logfire auth`
    #     token needed); spans still go to the local SQLite DB (`logfire view`).
    #     Cloud mode raises LogfireConfigError without a token and nulled every
    #     judge score in eval runs.
    #   - console=False : silence stdout. A verbose console
    #     (ConsoleOptions(min_log_level='trace', verbose=True, ...)) floods
    #     stdout with every pydantic-ai span once instrument_pydantic_ai() runs.
    #     Flip to `console=ConsoleOptions(...)` only when actively debugging.
    # In logfire 4.34+ `local=True` is NOT the offline knob — it returns a
    # non-global instance — so use `send_to_logfire=False`.
    # logfire.configure(send_to_logfire=False, console=False)
    # logfire.instrument_pydantic_ai()

    agent: Agent[None, _JudgeResult] = Agent(
        model,
        system_prompt=_CODE_REVIEW_SYSTEM,
        output_type=_JudgeResult,
        model_settings=cache_model_settings(enable_cache),
    )

    parts = [f"User prompt: {prompt}\n\nTikZ code:\n```\n{tikz_code}\n```"]
    if tkzelements_code:
        parts.append(f"\ntkz-elements Lua block:\n```\n{tkzelements_code}\n```")

    user_message = "\n".join(parts)

    result = await agent.run(user_message)

    data = result.output
    return {
        "score": data.score,
        "geometric_accuracy": data.geometric_accuracy,
        "labeling": data.labeling,
        "completeness": data.completeness,
        "likely_renders": data.likely_renders,
        "reasoning": data.reasoning,
    }


async def judge_rendered_diagram(
    prompt: str,
    svg: str,
    tikz_code: str | None = None,
    model: str = "openai:Qwen3.6-35B-A3B-Q8K.gguf",#"ollama:gemma4:31b-cloud", #"anthropic:claude-sonnet-4-6",
    enable_cache: bool = False,
) -> dict:
    """
    Ask a vision-capable LLM to judge the rendered diagram against the prompt.

    Converts SVG to PNG via cairosvg, then sends as a base64-encoded image.
    Requires cairosvg to be installed.

    Returns a dict with keys:
      score, geometric_accuracy, labeling, completeness, visual_quality, reasoning
    """
    try:
        import cairosvg
    except Exception as e:
        raise ImportError(
            "cairosvg and libcairo are required for visual judging."
        ) from e

    png_data = cairosvg.svg2png(bytestring=svg.encode("utf-8"), background_color="white")

    if not isinstance(png_data, bytes) or len(png_data) == 0:
        raise ValueError("Failed to convert SVG to PNG for visual judging.")

    from pydantic_ai.messages import BinaryContent

    agent: Agent[None, _VisualJudgeResult] = Agent(
        model,
        system_prompt=_VISUAL_REVIEW_SYSTEM,
        output_type=_VisualJudgeResult,
        model_settings=cache_model_settings(enable_cache),
    )

    user_content: list = [
        BinaryContent(data=png_data, media_type="image/png"),
        f"User prompt: {prompt}",
    ]
    if tikz_code:
        user_content.append(f"\nTikZ source (for reference):\n```\n{tikz_code}\n```")

    result = await agent.run(user_content)
    data = result.output
    return {
        "score": data.score,
        "geometric_accuracy": data.geometric_accuracy,
        "labeling": data.labeling,
        "completeness": data.completeness,
        "visual_quality": data.visual_quality,
        "reasoning": data.reasoning,
    }


# ---------------------------------------------------------------------------
# Mode 3: CoT-analysis (confidence judge)
# ---------------------------------------------------------------------------

_COT_ANALYSIS_SYSTEM = """\
You are an expert evaluator analyzing a geometry-diagram model's chain-of-thought
to judge how reliable its answer is.

You are given:
- the user's geometry prompt,
- the RecipeDSL the model produced (its answer),
- the model's chain-of-thought (CoT) emitted while producing that answer.

Your job is NOT to re-grade the geometry itself, but to assess the PROCESS: how
much should we trust this answer given how the model reasoned?

Fill every field:
- confidence (1-5): how reliable the answer is, given the CoT. High = coherent
  CoT that matches the prompt and DSL, explicit verification, few unresolved
  guesses. Low = hedging, arbitrary assumptions, self-contradictions, or CoT
  that doesn't match the produced DSL.
- confidence_reasoning: one short sentence.
- signals.hedging: count of uncertainty markers ('maybe', 'I think', 'not
  sure', 'perhaps').
- signals.explicit_assumptions: count of arbitrary/unjustified choices the
  model flagged (e.g. 'pick reasonable values 3, 4').
- signals.self_corrections: count of backtracks or revised decisions
  ('Wait, ...', reconsidering a prior choice).
- signals.verification_steps: count of times the model checked its own work
  (raises trust).
- signals.cot_answer_mismatch: true if the CoT reasoning contradicts the
  produced RecipeDSL.
- signals.cot_prompt_mismatch: true if the CoT misreads or ignores part of
  the prompt.
- signals.reasoning_depth (1-5): how thoroughly the CoT explores the problem
  (1 = superficial, 5 = exhaustive).

Be precise with counts. Default both mismatch flags to false unless clearly
present.
"""


class CotSignals(BaseModel):
    hedging: int = Field(ge=0, description="Count of uncertainty markers ('maybe', 'I think', 'not sure', 'perhaps').")
    explicit_assumptions: int = Field(ge=0, description="Count of arbitrary/unjustified choices the model flagged (e.g. 'pick reasonable values 3, 4').")
    self_corrections: int = Field(ge=0, description="Count of backtracks or revised decisions ('Wait, ...').")
    verification_steps: int = Field(ge=0, description="Count of times the model checked its own work (raises trust).")
    cot_answer_mismatch: bool = Field(description="True if the CoT contradicts the produced RecipeDSL.")
    cot_prompt_mismatch: bool = Field(description="True if the CoT misreads or ignores part of the prompt.")
    reasoning_depth: int = Field(ge=1, le=5, description="How thoroughly the CoT explores the problem (1=superficial, 5=exhaustive).")


class CotAnalysisResult(BaseModel):
    confidence: int = Field(ge=1, le=5, description="Overall reliability of the answer given the CoT, 1-5.")
    confidence_reasoning: str = Field(description="One short sentence explaining the confidence score.")
    signals: CotSignals


async def analyze_cot_llm(
    prompt: str,
    dsl_json: dict,
    cot: str,
    model: str = DEFAULT_AGENT_MODEL,
    enable_cache: bool = False,
) -> dict:
    """
    Ask an LLM to evaluate the model's chain-of-thought and estimate how
    reliable the produced answer is. Text-only (no rendering required).

    NOTE: this is the ORIGINAL LLM CoT judge, retained as `analyze_cot_llm`
    for comparison. It undercounts uncertainty markers in long CoTs and
    returned a near-constant confidence=5, so the default `analyze_cot` is
    now the deterministic text analyzer in `util/cot_analyzer.py`. This LLM
    version is not called by the eval harness by default.

    Returns a dict with keys:
      score (1-5 confidence), reasoning (one-sentence), signals (dict of the
      seven CoT signals).
    """
    agent: Agent[None, CotAnalysisResult] = Agent(
        model,
        system_prompt=_COT_ANALYSIS_SYSTEM,
        output_type=CotAnalysisResult,
        model_settings=cache_model_settings(enable_cache),
    )

    user_message = (
        f"User prompt:\n{prompt}\n\n"
        f"Produced RecipeDSL:\n```json\n{json.dumps(dsl_json, indent=2)}\n```\n\n"
        f"Chain-of-thought:\n{cot}"
    )

    result = await agent.run(user_message)
    data = result.output
    return {
        "score": data.confidence,
        "reasoning": data.confidence_reasoning,
        "signals": data.signals.model_dump(),
    }

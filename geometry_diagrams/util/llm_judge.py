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

import base64
import re

from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage

from geometry_diagrams.strategies.llm import get_chat_model

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
    model: str = "anthropic:claude-sonnet-4-6",
    enable_cache: bool = False,
) -> dict:
    """
    Ask an LLM to judge whether the TikZ code correctly implements the
    geometry prompt. No rendering required.

    Returns a dict with keys:
      score, geometric_accuracy, labeling, completeness, likely_renders, reasoning
    """
    llm = get_chat_model(model).with_structured_output(_JudgeResult)

    parts = [f"User prompt: {prompt}\n\nTikZ code:\n```\n{tikz_code}\n```"]
    if tkzelements_code:
        parts.append(f"\ntkz-elements Lua block:\n```\n{tkzelements_code}\n```")

    messages = [
        SystemMessage(content=_CODE_REVIEW_SYSTEM),
        HumanMessage(content="\n".join(parts)),
    ]
    data: _JudgeResult = await llm.ainvoke(messages)

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
    model: str = "anthropic:claude-sonnet-4-6",
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

    b64_image = base64.b64encode(png_data).decode("utf-8")

    llm = get_chat_model(model).with_structured_output(_VisualJudgeResult)

    text_parts: list = [f"User prompt: {prompt}"]
    if tikz_code:
        text_parts.append(f"\nTikZ source (for reference):\n```\n{tikz_code}\n```")

    human_content: list = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
        },
        {"type": "text", "text": "\n".join(text_parts)},
    ]

    messages = [
        SystemMessage(content=_VISUAL_REVIEW_SYSTEM),
        HumanMessage(content=human_content),
    ]
    data: _VisualJudgeResult = await llm.ainvoke(messages)

    return {
        "score": data.score,
        "geometric_accuracy": data.geometric_accuracy,
        "labeling": data.labeling,
        "completeness": data.completeness,
        "visual_quality": data.visual_quality,
        "reasoning": data.reasoning,
    }

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

from pydantic import BaseModel
from pydantic_ai import Agent

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


async def judge_tikz_code(
    prompt: str,
    tikz_code: str,
    tkzelements_code: str | None = None,
    model: str = "anthropic:claude-sonnet-4-6",
) -> dict:
    """
    Ask an LLM to judge whether the TikZ code correctly implements the
    geometry prompt. No rendering required.

    Returns a dict with keys:
      score, geometric_accuracy, labeling, completeness, likely_renders, reasoning
    """
    agent: Agent[None, _JudgeResult] = Agent(
        model,
        system_prompt=_CODE_REVIEW_SYSTEM,
        output_type=_JudgeResult,
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
    model: str = "anthropic:claude-sonnet-4-6",
) -> dict:
    """
    Ask a vision-capable LLM to judge the rendered diagram against the prompt.

    Converts SVG to PNG via cairosvg, then sends as a base64-encoded image.
    Requires cairosvg to be installed.

    Returns a dict with keys:
      score, geometric_accuracy, labeling, completeness, visual_quality, reasoning
    """
    try:
        import base64
        import cairosvg
    except ImportError as e:
        raise ImportError(
            "cairosvg is required for visual judging. "
            "Install it with: pip install cairosvg"
        ) from e

    png_data = cairosvg.svg2png(bytestring=svg.encode("utf-8"))

    if not isinstance(png_data, bytes) or len(png_data) == 0:
        raise ValueError("Failed to convert SVG to PNG for visual judging.")

    png_b64 = base64.standard_b64encode(png_data).decode("ascii")

    from pydantic_ai.messages import ImageUrl
    from anthropic import Anthropic

    client = Anthropic()

    user_content: list = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": png_b64,
            },
        },
        {
            "type": "text",
            "text": f"User prompt: {prompt}",
        },
    ]
    if tikz_code:
        user_content.append({
            "type": "text",
            "text": f"\nTikZ source (for reference):\n```\n{tikz_code}\n```",
        })

    # Use the Anthropic client directly for vision (pydantic-ai image support)
    response = client.messages.create(
        model=model.replace("anthropic:", ""),
        system=_VISUAL_REVIEW_SYSTEM,
        max_tokens=512,
        messages=[{"role": "user", "content": user_content}],
    )

    # Parse structured response from free-form last text (best-effort)
    text = response.content[-1].text if response.content else ""
    return _parse_visual_response(text)


def _parse_visual_response(text: str) -> dict:
    """Parse a visual judge response, extracting scores from free-form text."""
    import re

    def _extract_score(pattern: str) -> int | None:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return max(1, min(5, int(m.group(1))))
            except ValueError:
                return None
        return None

    return {
        "score": _extract_score(r"overall[^:]*:\s*(\d)") or _extract_score(r"score[^:]*:\s*(\d)") or 3,
        "geometric_accuracy": _extract_score(r"geometric[^:]*:\s*(\d)") or 3,
        "labeling": _extract_score(r"labeling[^:]*:\s*(\d)") or 3,
        "completeness": _extract_score(r"completeness[^:]*:\s*(\d)") or 3,
        "visual_quality": _extract_score(r"visual[^:]*:\s*(\d)") or 3,
        "reasoning": text[:300].strip(),
    }

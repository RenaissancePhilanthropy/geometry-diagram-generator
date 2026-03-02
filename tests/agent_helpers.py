"""
Shared helpers for tests that need to inspect pydantic-ai agent message history.
These are the same extraction utilities used in evals/run.py.
"""
from __future__ import annotations

import json


def extract_tool_return(messages, tool_name: str) -> str | None:
    """Return content of the last successful ToolReturnPart for tool_name."""
    from pydantic_ai.messages import ModelRequest, ToolReturnPart

    for msg in reversed(messages):
        if not isinstance(msg, ModelRequest):
            continue
        for part in reversed(msg.parts):
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name:
                content = part.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    return "".join(
                        c if isinstance(c, str) else getattr(c, "text", "")
                        for c in content
                    )
    return None


def extract_tool_call_args(messages, tool_name: str) -> dict | None:
    """Return args dict of the last ToolCallPart for tool_name."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    for msg in reversed(messages):
        if not isinstance(msg, ModelResponse):
            continue
        for part in reversed(msg.parts):
            if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                args = part.args
                if isinstance(args, dict):
                    return args
                if isinstance(args, str):
                    try:
                        return json.loads(args)
                    except json.JSONDecodeError:
                        return None
    return None


def count_tool_calls(messages, tool_name: str) -> int:
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    count = 0
    for msg in messages:
        if not isinstance(msg, ModelResponse):
            continue
        for part in msg.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                count += 1
    return count


def extract_svg_from_run(result) -> str | None:
    """Extract SVG from the render_diagram tool return in an agent RunResult."""
    tool_return = extract_tool_return(result.all_messages(), "render_diagram")
    if tool_return is None:
        return None
    try:
        return json.loads(tool_return).get("svg")
    except (json.JSONDecodeError, TypeError):
        return None


def extract_tikz_from_run(result) -> str | None:
    """Extract TikZ source code from the render_diagram tool call args."""
    args = extract_tool_call_args(result.all_messages(), "render_diagram")
    return args.get("tikz") if args else None

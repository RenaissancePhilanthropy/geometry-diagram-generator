"""
Shared helpers for tests that need to inspect LangChain agent message history.
"""
from __future__ import annotations

import json

from util.message_helpers import (
    count_tool_calls,
    extract_tool_call_args,
    extract_tool_return,
)

__all__ = [
    "count_tool_calls",
    "extract_tool_call_args",
    "extract_tool_return",
    "extract_svg_from_messages",
    "extract_tikz_from_messages",
]


def extract_svg_from_messages(messages) -> str | None:
    """Extract SVG from the render_diagram tool return in a message list."""
    tool_return = extract_tool_return(messages, "render_diagram")
    if tool_return is None:
        return None
    try:
        return json.loads(tool_return).get("svg")
    except (json.JSONDecodeError, TypeError):
        return None


def extract_tikz_from_messages(messages) -> str | None:
    """Extract TikZ source code from the render_diagram tool call args."""
    args = extract_tool_call_args(messages, "render_diagram")
    return args.get("tikz") if args else None

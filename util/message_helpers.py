"""
Shared helpers for extracting data from pydantic-ai agent message histories.

Used by both tests (tests/agent_helpers.py) and the eval runner (evals/run.py).
"""
from __future__ import annotations

import json


def extract_tool_return(messages, tool_name: str) -> str | None:
    """Return the content of the last successful ToolReturnPart for tool_name."""
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
    """Return the args dict of the last ToolCallPart for tool_name."""
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
    """Count all ToolCallPart instances for tool_name across all messages."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    count = 0
    for msg in messages:
        if not isinstance(msg, ModelResponse):
            continue
        for part in msg.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                count += 1
    return count

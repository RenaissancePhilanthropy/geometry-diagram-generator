"""
Shared helpers for extracting data from LangChain agent message histories.

Used by both tests and the eval runner (evals/run.py).
"""
from __future__ import annotations

import json


def extract_tool_return(messages, tool_name: str) -> str | None:
    """Return the content of the last successful tool return for tool_name."""
    from langchain_core.messages import ToolMessage

    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == tool_name:
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    c if isinstance(c, str) else getattr(c, "text", "")
                    for c in content
                )
    return None


def extract_tool_call_args(messages, tool_name: str) -> dict | None:
    """Return the args dict of the last tool call for tool_name."""
    from langchain_core.messages import AIMessage

    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        for tc in reversed(msg.tool_calls) if msg.tool_calls else []:
            if tc["name"] == tool_name:
                args = tc.get("args", {})
                if isinstance(args, dict):
                    return args
                if isinstance(args, str):
                    try:
                        return json.loads(args)
                    except json.JSONDecodeError:
                        return None
    return None


def count_tool_calls(messages, tool_name: str) -> int:
    """Count all tool call instances for tool_name across all messages."""
    from langchain_core.messages import AIMessage

    count = 0
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        for tc in msg.tool_calls or []:
            if tc["name"] == tool_name:
                count += 1
    return count

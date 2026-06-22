"""Compatibility fix for Ollama's rejection of `content: null` in assistant messages.

Ollama's OpenAI-compatible API rejects assistant messages where `content` is `null`
(even when there are no tool calls), returning:
    400 invalid message content type: <nil>

This differs from OpenAI's API, which accepts `content: null`.

Root cause: pydantic-ai's OpenAIChatModel maps a ModelResponse with no text
parts to `{"role": "assistant", "content": null}`, which Ollama rejects.

Upstream issue: https://github.com/pydantic/pydantic-ai/issues/5206
Upstream PR (tool-calls-only case, does NOT fix the empty-response case):
    https://github.com/pydantic/pydantic-ai/pull/5218

This module monkey-patches `_into_message_param` to use `content: ""` (empty
string) instead of `content: null` when there are no text parts. This is
compatible with both OpenAI and Ollama.

Apply the fix by importing this module before creating any Agents::

    import util.ollama_compat  # noqa: F401  — applies Ollama compat fix
"""

from pydantic_ai.models.openai import OpenAIChatModel

_original_into_message_param = OpenAIChatModel._MapModelResponseContext._into_message_param


def _patched_into_message_param(self):
    """Replace `content: null` with `content: ""` in assistant messages.

    Ollama rejects `content: null` (mapped from `content: None` in Python).
    Using an empty string is accepted by both OpenAI and Ollama.
    """
    result = _original_into_message_param(self)
    if result.get("content") is None:
        result["content"] = ""
    return result


OpenAIChatModel._MapModelResponseContext._into_message_param = _patched_into_message_param
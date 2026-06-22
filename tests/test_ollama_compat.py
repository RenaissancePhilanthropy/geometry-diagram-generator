"""Tests for the Ollama compatibility monkey-patch (util/ollama_compat.py).

Verifies that content=None in assistant messages is replaced with content=""
to prevent Ollama from rejecting requests with 'invalid message content type: <nil>'.

Upstream issue: https://github.com/pydantic/pydantic-ai/issues/5206
"""

import pytest

from pydantic_ai.models.openai import OpenAIChatModel


class TestOllamaCompatPatch:
    """Verify the monkey-patch on _MapModelResponseContext._into_message_param."""

    def test_patch_is_applied(self):
        """The monkey-patch should be applied on import."""
        import util.ollama_compat  # noqa: F401

        method = OpenAIChatModel._MapModelResponseContext._into_message_param
        assert method.__name__ == "_patched_into_message_param"

    def test_content_none_replaced_with_empty_string(self):
        """When _into_message_param returns content=None, the patch should replace it with ''."""
        import util.ollama_compat  # noqa: F401

        # We can't easily construct a _MapModelResponseContext directly, so we test
        # the patch function's behavior by checking that it converts None to "".
        # Create a mock context that would produce content=None
        # (i.e., no texts, no tool_calls, no thinking)
        ctx = OpenAIChatModel._MapModelResponseContext.__new__(
            OpenAIChatModel._MapModelResponseContext
        )
        ctx.texts = []
        ctx.tool_calls = []
        ctx.thinkings = {}

        result = ctx._into_message_param()
        # Without the patch, content would be None
        # With the patch, content should be ""
        assert result.get("content") == "", f"Expected content='', got {result.get('content')!r}"
        assert result["role"] == "assistant"

    def test_content_with_tool_calls_is_empty_string(self):
        """When tool_calls exist but no text, content should still be '' (not None)."""
        import util.ollama_compat  # noqa: F401

        ctx = OpenAIChatModel._MapModelResponseContext.__new__(
            OpenAIChatModel._MapModelResponseContext
        )
        ctx.texts = []
        ctx.tool_calls = [
            {
                "type": "function",
                "function": {"name": "test", "arguments": "{}"},
                "id": "call_123",
            }
        ]
        ctx.thinkings = {}

        result = ctx._into_message_param()
        # Without the patch, content would be None (with tool_calls present)
        # With the patch, content should be ""
        assert result.get("content") == "", f"Expected content='', got {result.get('content')!r}"
        assert "tool_calls" in result

    def test_content_with_text_preserved(self):
        """When texts exist, content should be the joined text (not affected by patch)."""
        import util.ollama_compat  # noqa: F401

        ctx = OpenAIChatModel._MapModelResponseContext.__new__(
            OpenAIChatModel._MapModelResponseContext
        )
        ctx.texts = ["Hello"]
        ctx.tool_calls = []
        ctx.thinkings = {}

        result = ctx._into_message_param()
        assert result["content"] == "Hello"
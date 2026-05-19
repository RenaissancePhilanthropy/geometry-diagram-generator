"""LangChain model factory — maps pydantic-ai-style model IDs to LangChain chat models."""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage


def get_chat_model(model_id: str, enable_cache: bool = False, **kwargs) -> BaseChatModel:
    """Return a LangChain chat model for the given model ID.

    Supports pydantic-ai-style prefixes:
    - "anthropic:MODEL" -> ChatAnthropic
    - "openai:MODEL" / "openai-responses:MODEL" -> ChatOpenAI
    - "google:MODEL" / "gemini:MODEL" -> ChatGoogleGenerativeAI
    """
    if model_id.startswith("anthropic:"):
        from langchain_anthropic import ChatAnthropic
        model_name = model_id.removeprefix("anthropic:")
        if enable_cache:
            # Enable Anthropic prompt caching beta
            headers = dict(kwargs.pop("extra_headers", {}))
            headers.setdefault("anthropic-beta", "prompt-caching-2024-07-31")
            kwargs["extra_headers"] = headers
        return ChatAnthropic(model=model_name, **kwargs)
    elif model_id.startswith("openai:") or model_id.startswith("openai-responses:"):
        from langchain_openai import ChatOpenAI
        model_name = model_id.split(":", 1)[1]
        return ChatOpenAI(model=model_name, **kwargs)
    elif model_id.startswith("google:") or model_id.startswith("gemini:"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        model_name = model_id.split(":", 1)[1]
        return ChatGoogleGenerativeAI(model=model_name, **kwargs)
    else:
        # Fallback: try as a bare model name with Anthropic
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_id, **kwargs)


def make_system_message(content: str, enable_cache: bool = False) -> SystemMessage:
    """Create a SystemMessage, optionally marked for Anthropic prompt caching."""
    if enable_cache:
        return SystemMessage(content=[{
            "type": "text",
            "text": content,
            "cache_control": {"type": "ephemeral"},
        }])
    return SystemMessage(content=content)


def is_gemini_model(model_id: str) -> bool:
    """Return True if the model is a Google/Gemini model."""
    return model_id.startswith("google:") or model_id.startswith("gemini:")


def extract_usage(response: AIMessage) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a LangChain AIMessage response."""
    meta = response.response_metadata.get("usage", {})
    # Anthropic uses input_tokens/output_tokens; OpenAI uses prompt_tokens/completion_tokens
    input_tokens = meta.get("input_tokens", meta.get("prompt_tokens", 0))
    output_tokens = meta.get("output_tokens", meta.get("completion_tokens", 0))
    return input_tokens, output_tokens

"""LangChain model factory — maps pydantic-ai-style model IDs to LangChain chat models."""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage

TINKER_BASE_URL = "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1"
BASETEN_BASE_URL = "https://inference.baseten.co/v1"
MANTLE_BASE_URL_TEMPLATE = "https://bedrock-mantle.{region}.api.aws/v1"

# Every entry with backend "openai" is served by ChatOpenAI — the only difference
# between providers is base_url/api_key/default kwargs. To add a *known* provider,
# add an entry here. To add an ad-hoc one with no code change at all, set
# "{PREFIX}_BASE_URL" (and optionally "{PREFIX}_API_KEY") in the environment — see
# _generic_openai_provider below.
_KNOWN_PROVIDERS: dict[str, dict] = {
    "anthropic": {"backend": "anthropic"},
    "openai": {"backend": "openai"},
    "openai-responses": {"backend": "openai"},
    "google": {"backend": "google"},
    "gemini": {"backend": "google"},
    "tinker": {
        "backend": "openai",
        "base_url": TINKER_BASE_URL,
        "api_key_env": "THINKING_MACHINES_API_KEY",
        # Inkling spends a large fraction of its output budget on reasoning
        # tokens before writing the answer; the OpenAI-compatible default of
        # 4096 truncates mid-answer on anything but trivial prompts.
        "default_kwargs": {"max_tokens": 16000},
    },
    "baseten": {
        "backend": "openai",
        "base_url": BASETEN_BASE_URL,
        "api_key_env": "BASETEN_API_KEY",
        "default_kwargs": {"max_tokens": 16000},
    },
    "mantle": {
        "backend": "openai",
        "base_url": MANTLE_BASE_URL_TEMPLATE,  # "{region}" resolved at call time
        "api_key_env": "AWS_BEARER_TOKEN_BEDROCK",
    },
}


def _generic_openai_provider(prefix: str) -> dict | None:
    """Env-var convention for OpenAI-compatible providers not in _KNOWN_PROVIDERS.

    Setting "{PREFIX}_BASE_URL" makes "{prefix}:MODEL" route to ChatOpenAI at that
    base_url, e.g. FIREWORKS_BASE_URL=https://api.fireworks.ai/inference/v1 lets
    "fireworks:llama-4-maverick" work with no change to this file. "{PREFIX}_API_KEY"
    is optional (some self-hosted endpoints don't require one).
    """
    env_prefix = prefix.upper().replace("-", "_")
    base_url = os.environ.get(f"{env_prefix}_BASE_URL")
    if not base_url:
        return None
    provider = {"backend": "openai", "base_url": base_url}
    api_key_env = f"{env_prefix}_API_KEY"
    if api_key_env in os.environ:
        provider["api_key_env"] = api_key_env
    return provider


def _resolve_provider(model_id: str) -> dict | None:
    prefix, sep, _ = model_id.partition(":")
    if not sep:
        return None
    return _KNOWN_PROVIDERS.get(prefix) or _generic_openai_provider(prefix)


def get_chat_model(model_id: str, enable_cache: bool = False, **kwargs) -> BaseChatModel:
    """Return a LangChain chat model for the given model ID.

    Supports pydantic-ai-style prefixes: "anthropic:MODEL", "openai:MODEL" /
    "openai-responses:MODEL", "google:MODEL" / "gemini:MODEL", plus any OpenAI-compatible
    provider registered in _KNOWN_PROVIDERS (tinker, baseten, mantle) or declared purely via
    "{PREFIX}_BASE_URL" / "{PREFIX}_API_KEY" env vars (see _generic_openai_provider).
    An unrecognized or bare (no ":") model_id falls back to a literal Anthropic model name.
    """
    provider = _resolve_provider(model_id)
    if provider is None:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_id, **kwargs)

    model_name = model_id.split(":", 1)[1]
    backend = provider["backend"]

    if backend == "anthropic":
        from langchain_anthropic import ChatAnthropic
        if enable_cache:
            # Enable Anthropic prompt caching beta via model_kwargs to avoid
            # LangChain warning about extra_headers being a non-standard parameter.
            model_kwargs = dict(kwargs.pop("model_kwargs", {}))
            extra_headers = dict(kwargs.pop("extra_headers", model_kwargs.pop("extra_headers", {})))
            extra_headers.setdefault("anthropic-beta", "prompt-caching-2024-07-31")
            model_kwargs["extra_headers"] = extra_headers
            kwargs["model_kwargs"] = model_kwargs
        return ChatAnthropic(model=model_name, **kwargs)

    if backend == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_name, **kwargs)

    # backend == "openai": every OpenAI-compatible provider funnels through ChatOpenAI.
    from langchain_openai import ChatOpenAI
    base_url = provider.get("base_url")
    if base_url:
        if "{region}" in base_url:
            base_url = base_url.format(region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        kwargs.setdefault("base_url", base_url)
    api_key_env = provider.get("api_key_env")
    if api_key_env:
        kwargs.setdefault("api_key", os.environ[api_key_env])
    for key, value in provider.get("default_kwargs", {}).items():
        kwargs.setdefault(key, value)
    return ChatOpenAI(model=model_name, **kwargs)


def make_system_message(content: str, enable_cache: bool = False) -> SystemMessage:
    """Create a SystemMessage, optionally marked for Anthropic prompt caching.

    Anthropic rejects cache_control on empty text blocks, so empty/falsy
    content falls back to an uncached message rather than 400ing.
    """
    if enable_cache and content:
        return SystemMessage(content=[{
            "type": "text",
            "text": content,
            "cache_control": {"type": "ephemeral"},
        }])
    return SystemMessage(content=content)


def is_gemini_model(model_id: str) -> bool:
    """Return True if the model is a Google/Gemini model."""
    provider = _resolve_provider(model_id)
    return provider is not None and provider["backend"] == "google"


def is_openai_model(model_id: str) -> bool:
    """Return True if the model uses the OpenAI-compatible chat completions API."""
    provider = _resolve_provider(model_id)
    return provider is not None and provider["backend"] == "openai"


def extract_usage(response: AIMessage) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a LangChain AIMessage response."""
    usage = response.usage_metadata or {}
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)

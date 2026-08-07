"""LangChain model factory — maps pydantic-ai-style model IDs to LangChain chat models."""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage

TINKER_BASE_URL = "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1"
BASETEN_BASE_URL = "https://inference.baseten.co/v1"
MANTLE_BASE_URL_TEMPLATE = "https://bedrock-mantle.{region}.api.aws/v1"
# Bedrock Mantle exposes two separate proxy routes that are NOT interchangeable
# per model — confirmed empirically (2026-08-06): nvidia.nemotron-super-3-120b
# only works on the plain /v1 route above (any region); google.gemma-4-31b only
# works on this /openai/v1 route, and only in us-east-2 (us-east-1 503s on this
# route consistently). Both routes 400 with "isn't supported on this route" for
# a model that belongs on the other one — there is no single route/region that
# serves both, so this needs its own provider prefix rather than being folded
# into "mantle" below.
MANTLE_OPENAI_BASE_URL_TEMPLATE = "https://bedrock-mantle.{region}.api.aws/openai/v1"

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
        # No blanket default_kwargs here (unlike tinker/baseten above, which
        # are each effectively one specific model) — mantle/mantle-oa serve
        # many different models, and a provider-wide max_tokens bump that
        # helps one model can break another. Confirmed (2026-08-07): setting
        # max_tokens=16000 blanket-wide to help gpt-oss-20b/glm-4.7-flash's
        # hidden reasoning channel (see _MODEL_SPECIFIC_KWARGS below)
        # regressed google.gemma-4-31b from 84% to 57% pass rate — 3/4 manual
        # trials at max_tokens=16000 returned a degenerate {"script":":"}
        # tool call under forced tool_choice, vs. 2/2 clean at max_tokens=2000.
        # Per-model overrides only, via _MODEL_SPECIFIC_KWARGS.
    },
    "mantle-oa": {
        "backend": "openai",
        "base_url": MANTLE_OPENAI_BASE_URL_TEMPLATE,  # "{region}" resolved at call time
        "api_key_env": "AWS_BEARER_TOKEN_BEDROCK",
    },
}


# Extra default kwargs for a provider reachable only via the generic env-var
# fallback below, when it needs one small tweak but doesn't warrant a full
# _KNOWN_PROVIDERS entry (which would mean hardcoding its base_url, losing the
# "just set {PREFIX}_BASE_URL" convention that lets people repoint it).
_GENERIC_DEFAULT_KWARGS: dict[str, dict] = {
    # OpenRouter only reports real per-request cost (response_metadata
    # ["token_usage"]["cost"], see extract_cost()) when a request opts in via
    # this field. Other providers ignore unknown body params, so sending it
    # unconditionally for "openrouter:..." models is safe.
    "openrouter": {"extra_body": {"usage": {"include": True}}},
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
    if prefix in _GENERIC_DEFAULT_KWARGS:
        provider["default_kwargs"] = _GENERIC_DEFAULT_KWARGS[prefix]
    return provider


# Extra body fields for one specific misbehaving model (keyed on the full
# "{provider}:{model}" id), as opposed to _GENERIC_DEFAULT_KWARGS above (a whole
# provider prefix). Merged into (not replacing) whatever extra_body the provider
# already sets, so e.g. openrouter's usage-include opt-in survives alongside this.
_MODEL_SPECIFIC_EXTRA_BODY: dict[str, dict] = {
    # qwen3.7-flash runs in "thinking mode" by default on OpenRouter/Alibaba, which
    # rejects a forced tool_choice (what with_structured_output(method=
    # "function_calling") sends) with "tool_choice parameter does not support
    # being set to required or object in thinking mode". Confirmed empirically
    # (2026-08-06) that disabling reasoning resolves it cleanly.
    "openrouter:qwen/qwen3.7-flash": {"reasoning": {"enabled": False}},
    # deepseek-v4-flash-0731 hit a 52% scenario-timeout rate (180s hard cap) in a
    # 2026-08-06 curriculum run despite a 99% pass rate on the scenarios that DID
    # complete — a pure latency problem, not a capability one. OpenRouter's
    # per-endpoint stats for this model (checked 2026-08-06) show its default
    # routing can land on providers with p90 latency up to 9x worse than the
    # fastest ones: BaseTen (p50 350ms, p90 820ms, 100% uptime) and CoreWeave
    # (p50 533ms, p90 1880ms, 99.9% uptime) vs. e.g. Fireworks (p90 7162ms,
    # 92.7% uptime). allow_fallbacks stays true so a brief outage on both
    # preferred providers doesn't hard-fail the request.
    "openrouter:deepseek/deepseek-v4-flash-0731": {
        "provider": {"order": ["BaseTen", "CoreWeave"], "allow_fallbacks": True},
    },
}


# Top-level kwargs (not nested under extra_body) for one specific model,
# keyed the same way as _MODEL_SPECIFIC_EXTRA_BODY above. Use this instead of
# a provider's blanket default_kwargs when the override only helps some
# models served by that provider and actively hurts others (mantle/mantle-oa
# serve many unrelated models — see the "mantle" entry's comment above).
_MODEL_SPECIFIC_KWARGS: dict[str, dict] = {
    # Both spend part of their output budget on a hidden reasoning channel
    # before the actual answer (gpt-oss-20b's "reasoning" field; glm-4.7-flash
    # truncating mid-JSON with "length limit was reached" on ~10% of
    # curriculum-eval scenario-runs, 2026-08-06) — the OpenAI-compatible
    # default of 4096 isn't enough headroom for that.
    "mantle:openai.gpt-oss-20b": {"max_tokens": 16000},
    "mantle:zai.glm-4.7-flash": {"max_tokens": 16000},
}


def _resolve_provider(model_id: str) -> dict | None:
    prefix, sep, _ = model_id.partition(":")
    if not sep:
        return None
    return _KNOWN_PROVIDERS.get(prefix) or _generic_openai_provider(prefix)


def get_chat_model(model_id: str, enable_cache: bool = False, **kwargs) -> BaseChatModel:
    """Return a LangChain chat model for the given model ID.

    Supports pydantic-ai-style prefixes: "anthropic:MODEL", "openai:MODEL" /
    "openai-responses:MODEL", "google:MODEL" / "gemini:MODEL", plus any OpenAI-compatible
    provider registered in _KNOWN_PROVIDERS (tinker, baseten, mantle, mantle-oa) or declared purely via
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
    for key, value in _MODEL_SPECIFIC_KWARGS.get(model_id, {}).items():
        kwargs.setdefault(key, value)
    model_extra_body = _MODEL_SPECIFIC_EXTRA_BODY.get(model_id)
    if model_extra_body:
        merged_extra_body = dict(kwargs.get("extra_body") or {})
        merged_extra_body.update(model_extra_body)
        kwargs["extra_body"] = merged_extra_body
    return ChatOpenAI(model=model_name, **kwargs)


def make_system_message(content: str, enable_cache: bool = False, model_id: str = "") -> SystemMessage:
    """Create a SystemMessage, optionally marked for Anthropic prompt caching.

    Anthropic rejects cache_control on empty text blocks, so empty/falsy
    content falls back to an uncached message rather than 400ing.

    The cache_control content-block form is an Anthropic-specific extension.
    enable_cache is only honored when model_id resolves to an Anthropic model
    (or model_id is omitted, for any caller not yet updated to pass it) —
    confirmed (2026-08-06) that sending it to a non-Anthropic OpenAI-compatible
    provider is at best a silently-ignored no-op (most providers tolerate the
    unknown field) and at worst a hard rejection: Fireworks.ai strictly
    validates message content as a plain string and 400s on the
    content-block-list form ("Input should be a valid string, field:
    'messages[0].content.str'"), failing every single attempt identically.
    """
    if enable_cache and content and (not model_id or is_anthropic_model(model_id)):
        return SystemMessage(content=[{
            "type": "text",
            "text": content,
            "cache_control": {"type": "ephemeral"},
        }])
    return SystemMessage(content=content)


# Models whose provider rejects BOTH with_structured_output methods
# python_full.py's pipeline supports — forced tool_choice ("function_calling")
# and json_mode response_format both hard-reject with a deterministic
# API-level error, confirmed (2026-08-06) for
# vercel:meta/muse-spark-1.2-contributor: forced tool_choice -> "only 'auto'
# is supported for tool_choice"; response_format:{"type":"json_object"} ->
# "Invalid input" (param: "response_format"). For these, _generate_script_node
# skips with_structured_output entirely and relies on plain-text generation +
# markdown-fence/salvage extraction as the ONLY generation path, not a
# fallback used only on parse failure.
_RAW_TEXT_ONLY_MODELS: set[str] = {
    "vercel:meta/muse-spark-1.2-contributor",
}


def requires_raw_text_generation(model_id: str) -> bool:
    """Return True if this model's provider rejects both structured-output
    methods this pipeline supports, requiring a plain-text-only generation
    path (see _RAW_TEXT_ONLY_MODELS)."""
    return model_id in _RAW_TEXT_ONLY_MODELS


# Models that need with_structured_output's method explicitly forced to
# "function_calling" rather than left to LangChain's auto-detection.
# openrouter:qwen/qwen3.7-flash is the one confirmed case (2026-08-06):
# unforced, LangChain picked json_mode for it (a model it doesn't recognize
# as tool-calling-capable), which the underlying provider (Alibaba) then
# rejected outright, failing every single attempt identically.
#
# IMPORTANT: do NOT force this for every model by default — confirmed
# (2026-08-07) that doing so regressed mantle-oa:google.gemma-4-31b from 84%
# to 57% pass rate. Direct comparison, 10 trials each, real system prompt:
# unforced (auto-detect) → 9/10 clean, 0 degenerate; forced function_calling
# → 4/10 returned a degenerate {"script":":"} tool call. Forcing destabilizes
# gemma-4-31b's tool-calling; only qwen3.7-flash is confirmed to need it.
_FORCED_FUNCTION_CALLING_MODELS: set[str] = {
    "openrouter:qwen/qwen3.7-flash",
}


def requires_forced_function_calling(model_id: str) -> bool:
    """Return True if with_structured_output's method must be forced to
    "function_calling" for this model rather than left to auto-detection
    (see _FORCED_FUNCTION_CALLING_MODELS)."""
    return model_id in _FORCED_FUNCTION_CALLING_MODELS


def is_anthropic_model(model_id: str) -> bool:
    """Return True if the model uses the Anthropic backend."""
    provider = _resolve_provider(model_id)
    return provider is not None and provider["backend"] == "anthropic"


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


def extract_cost(response: AIMessage) -> "float | None":
    """Extract real per-request cost (USD) from an AIMessage, if the provider
    reported one. Currently only OpenRouter does (via the extra_body opt-in
    in _GENERIC_DEFAULT_KWARGS, surfaced as response_metadata["token_usage"]
    ["cost"]) — other providers (e.g. Bedrock) return None since they don't
    report cost at the API level at all."""
    token_usage = response.response_metadata.get("token_usage") or {}
    cost = token_usage.get("cost")
    return float(cost) if cost is not None else None

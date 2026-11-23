"""LangChain model factory — maps pydantic-ai-style model IDs to LangChain chat models."""
from __future__ import annotations

from contextlib import contextmanager
import functools
from contextvars import ContextVar
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

# NOTE (2026-08-07): mantle-oa:google.gemma-4-31b's serving route corrupts
# stray label-text characters (degree/pi/superscript symbols) into raw
# non-printable control bytes (0x01-0x03, 0x0f, 0x1a, 0x1b, 0x1d, ...) with
# no backslash or escape sequence involved on the model's own output side —
# confirmed via a 28-scenario replay of curriculum-eval failures, where 26/28
# produced these bytes on mantle-oa. The identical 28 scenarios run against
# openrouter:google/gemma-4-31b-it (2 repeats each) came back 56/56 clean —
# zero corruption. Root cause on Bedrock's side is unconfirmed (plausibly a
# quantization/decoding artifact specific to that serving stack; OpenRouter's
# upstream endpoints for this model span fp4/fp8/bf16 so it isn't simply
# "any quantization causes this" either). Until Bedrock's route is
# understood or fixed, prefer "openrouter:google/gemma-4-31b-it" over
# "mantle-oa:google.gemma-4-31b" for this model. The pydsl label-text
# sanitizer (geometry_diagrams/pydsl/handles.py's _sanitize_label_text)
# stays in place regardless, as defense-in-depth against whichever host is
# in use.


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


# Shared value for the three "sort by throughput instead of pinning specific
# OpenRouter upstream provider names" fixes below — same object, not three
# separately-typed-out literals, so they can't quietly drift apart.
_SORT_BY_THROUGHPUT_EXTRA_BODY: dict = {"provider": {"sort": "throughput"}}

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
    # openrouter:nvidia/nemotron-3.5-lightning runs in "thinking mode" by
    # default and never terminates the reasoning channel before hitting
    # the length limit — confirmed empirically (2026-08-11): a trivial
    # one-line-script request spent 21200+ completion tokens (2099 of
    # them logged as reasoning_tokens on one attempt, 0 on a retry that
    # still hit the same limit) and never produced a parseable structured
    # response. Disabling reasoning resolves it cleanly (15 completion
    # tokens, parses immediately) — same fix and same failure shape as
    # qwen3.7-flash above.
    "openrouter:nvidia/nemotron-3.5-lightning": {"reasoning": {"enabled": False}},
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
    # openrouter:google/gemma-4-31b-it hit 103/402 (26%) scenario timeouts
    # (180s hard cap) in a 2026-08-07 curriculum run, despite otherwise
    # being the cleanest route for this model (0 byte-corruption failures,
    # vs. 50 on mantle-oa — see the mantle-oa note above). Per-endpoint
    # stats show an enormous throughput spread across this model's ~18
    # OpenRouter upstream providers: Cerebras at 176 tok/s p50 / 564 p90
    # vs. most others in the 10-50 tok/s range (some 10-15x slower), plus
    # multi-second p90 latency on several. Rather than pin specific
    # provider names (which drift out of date as performance changes),
    # use OpenRouter's "sort": "throughput" to always route to whichever
    # upstream provider currently has the best throughput for this model.
    "openrouter:google/gemma-4-31b-it": _SORT_BY_THROUGHPUT_EXTRA_BODY,
    # openrouter:qwen/qwen3.6-27b hit an 18/39 (46%) scenario-timeout rate
    # on a curriculum re-run (2026-08-08), even running alone with no
    # concurrent contention. Per-endpoint stats show a real latency spread
    # across this model's 9 OpenRouter upstream providers: CoreWeave at
    # p50 383ms / p90 856ms vs. SiliconFlow at p50 2070ms / p90 5501ms
    # (~5.4x/~6.4x worse) — plus a smaller but real throughput spread
    # (26-63 tok/s). Same fix as gemma-4-31b-it above: sort by throughput
    # rather than pin specific providers.
    "openrouter:qwen/qwen3.6-27b": _SORT_BY_THROUGHPUT_EXTRA_BODY,
    # openrouter:qwen/qwen3.6-35b-a3b hit a 25/78 (32%) scenario-timeout
    # rate on a clean, uncontended curriculum re-run (2026-08-08).
    # Per-endpoint stats show a 7x throughput spread (19-138 tok/s) and
    # 5.5x latency spread (p50 299ms CoreWeave to 1631ms SiliconFlow)
    # across 9 upstream providers. Same fix as gemma-4-31b-it/qwen3.6-27b.
    "openrouter:qwen/qwen3.6-35b-a3b": _SORT_BY_THROUGHPUT_EXTRA_BODY,
    # NOTE: openrouter:kwaipilot/kat-coder-air-v2.5 was checked for the same
    # issue (21/67 = 31% timeout rate, 2026-08-08) but has only ONE upstream
    # provider on OpenRouter (StreamLake, p50 2276ms / p90 9576ms) — no
    # alternative route exists to sort/pin toward. Its slowness is inherent
    # to its only host; provider routing cannot fix it.
}


# Top-level kwargs (not nested under extra_body) for one specific model,
# keyed the same way as _MODEL_SPECIFIC_EXTRA_BODY above. Use this instead of
# a provider's blanket default_kwargs when the override only helps some
# models served by that provider and actively hurts others (mantle/mantle-oa
# serve many unrelated models — see the "mantle" entry's comment above).
_MODEL_SPECIFIC_KWARGS: dict[str, dict] = {
    # langchain-anthropic (1.4.6) has no entry for these, so ChatAnthropic falls back to
    # max_tokens=4096, which can truncate a python_full script mid-way (the 4.x models get
    # 64000 from the same table). 16000 is the headroom the other entries here use.
    "anthropic:claude-sonnet-5-5": {"max_tokens": 16000},
    "anthropic:claude-opus-5-5": {"max_tokens": 16000},
    "anthropic:claude-fable-5-1": {"max_tokens": 16000},
    # Both spend part of their output budget on a hidden reasoning channel
    # before the actual answer (gpt-oss-20b's "reasoning" field; glm-4.7-flash
    # truncating mid-JSON with "length limit was reached" on ~10% of
    # curriculum-eval scenario-runs, 2026-08-06) — the OpenAI-compatible
    # default of 4096 isn't enough headroom for that.
    "mantle:openai.gpt-oss-20b": {"max_tokens": 16000},
    "mantle:zai.glm-4.7-flash": {"max_tokens": 16000},
    # reasoning_effort="low" was confirmed (2026-08-07) to match "high" on pass
    # rate (43/45 both) at roughly half the latency, but the API has since
    # started rejecting function tools combined with ANY reasoning_effort on
    # /v1/chat/completions ("Function tools with reasoning_effort are not
    # supported for gpt-5.6-luna ... set reasoning_effort to 'none'."), which
    # 400'd RecipeStrategy's forced tool call. "none" is now a hard requirement
    # here, same as gpt-6-luna below.
    "openai:gpt-5.6-luna": {"reasoning_effort": "none"},
    # Hard requirement, not a latency tuning like gpt-5.6-luna above: gpt-6-luna's
    # default reasoning_effort rejects forced tool calls on /v1/chat/completions
    # outright — "Function tools with reasoning_effort are not supported for
    # gpt-6-luna in /v1/chat/completions. To use function tools, use /v1/responses
    # or set reasoning_effort to 'none'." (confirmed 2026-09-24: RecipeStrategy's
    # forced-tool-choice DSL generation 400'd on all 3 retry attempts without this).
    # With reasoning_effort="none", 3/3 quick trials succeeded on the first
    # attempt (~4.5-4.7s each) — no comparison yet against routing through
    # "openai-responses:gpt-6-luna" instead, which the error message names as
    # the other way to keep function tools with reasoning enabled.
    "openai:gpt-6-luna": {"reasoning_effort": "none"},
}


def _resolve_provider(model_id: str) -> dict | None:
    prefix, sep, _ = model_id.partition(":")
    if not sep:
        return None
    return _KNOWN_PROVIDERS.get(prefix) or _generic_openai_provider(prefix)


# Environment variables the LangChain SDKs read their credentials from, per
# provider prefix. Used only to explain a construction failure: anthropic is
# absent because ChatAnthropic constructs without a key (the failure only
# shows at request time).
_SDK_KEY_ENV: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "openai-responses": ("OPENAI_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}
_API_KEY_KWARGS = ("api_key", "openai_api_key", "google_api_key")


def _missing_key_error(env_var: str, model_id: str) -> RuntimeError:
    provider = model_id.partition(":")[0]
    return RuntimeError(
        f"Missing API key: environment variable {env_var} is not set "
        f"(required for the {provider!r} provider, model {model_id!r})"
    )


def _construct(factory, model_id: str, kwargs: dict) -> BaseChatModel:
    """Build a chat model; when that fails and the provider's API key env var is
    unset (and no key was passed), raise a RuntimeError naming the variable
    instead of the SDK's own credential error."""
    try:
        return factory()
    except Exception as exc:
        env_vars = _SDK_KEY_ENV.get(model_id.partition(":")[0], ())
        if (
            env_vars
            and not any(os.environ.get(v) for v in env_vars)
            and not any(kwargs.get(k) for k in _API_KEY_KWARGS)
        ):
            raise _missing_key_error(" or ".join(env_vars), model_id) from exc
        raise


def _import_provider(module: str, attr: str, extra: str):
    """Import an optional provider class, naming the extra to install if absent."""
    import importlib

    try:
        return getattr(importlib.import_module(module), attr)
    except ImportError as e:
        raise ImportError(
            f"{module} is not installed; install it with `pip install 'geometry-diagrams[{extra}]'` "
            f"(or `uv sync --extra {extra}`) to use this model provider."
        ) from e


_AMBIENT_MODEL_OPTIONS: ContextVar["dict | None"] = ContextVar("geometry_model_options", default=None)


@contextmanager
def model_options_context(options: "dict | None"):
    """Make `options` (chat-model constructor kwargs such as temperature, timeout or
    max_tokens) the defaults of every get_chat_model call made inside the block, in this
    task and the ones it starts. GeometryConfig.model_options is applied this way, so the
    strategies need not thread it through each call site. An explicit kwarg to
    get_chat_model still wins, and these win over register_model_options defaults."""
    token = _AMBIENT_MODEL_OPTIONS.set(dict(options) if options else None)
    try:
        yield
    finally:
        _AMBIENT_MODEL_OPTIONS.reset(token)


def register_model_options(
    model_id: str, *, kwargs: "dict | None" = None, extra_body: "dict | None" = None,
) -> None:
    """Add default chat-model options for one model, keyed "provider:model" like every id here.

    kwargs are constructor kwargs for the model class (e.g. {"max_tokens": 8000},
    {"temperature": 0}); extra_body is merged into the request body and is only for
    OpenAI-compatible providers, including OpenRouter (e.g. {"provider": {"zdr": True}} to
    pin zero data retention). Merged over any built-in entry for the model, later calls
    over earlier ones, and below GeometryConfig.model_options and explicit get_chat_model
    kwargs. Process-wide: call it once at startup."""
    provider_name, sep, _ = model_id.partition(":")
    if not sep:
        raise ValueError(f"model_id must be 'provider:model', got {model_id!r}")
    if extra_body:
        provider = _resolve_provider(model_id)
        if provider is None or provider["backend"] != "openai":
            raise ValueError(
                f"extra_body is only for OpenAI-compatible providers, and {provider_name!r} is not a known "
                f"one (set {provider_name.upper().replace('-', '_')}_BASE_URL to declare it)"
            )
        merged = dict(_MODEL_SPECIFIC_EXTRA_BODY.get(model_id, {}))
        merged.update(extra_body)
        _MODEL_SPECIFIC_EXTRA_BODY[model_id] = merged
    if kwargs:
        _MODEL_SPECIFIC_KWARGS[model_id] = {**_MODEL_SPECIFIC_KWARGS.get(model_id, {}), **kwargs}


def registered_model_options(model_id: str) -> dict:
    """The built-in and registered options for a model id: {"kwargs": {...}, "extra_body": {...}}."""
    return {
        "kwargs": dict(_MODEL_SPECIFIC_KWARGS.get(model_id, {})),
        "extra_body": dict(_MODEL_SPECIFIC_EXTRA_BODY.get(model_id, {})),
    }


def _apply_model_options(model_id: str, kwargs: dict, provider_defaults: "dict | None" = None) -> None:
    """Fill `kwargs` in place: explicit values stay, then GeometryConfig.model_options, then
    the registered per-model defaults. extra_body is merged key by key in the same order,
    over the provider's own default extra_body (e.g. OpenRouter's usage opt-in)."""
    ambient = _AMBIENT_MODEL_OPTIONS.get() or {}
    registered = _MODEL_SPECIFIC_KWARGS.get(model_id, {})
    for source in (ambient, registered):
        for key, value in source.items():
            if key != "extra_body":
                kwargs.setdefault(key, value)
    bodies = [
        (provider_defaults or {}).get("extra_body"), _MODEL_SPECIFIC_EXTRA_BODY.get(model_id),
        ambient.get("extra_body"), kwargs.get("extra_body"),
    ]
    if any(bodies):
        merged: dict = {}
        for body in bodies:  # later wins
            merged.update(body or {})
        kwargs["extra_body"] = merged


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
        _apply_model_options(f"anthropic:{model_id}", kwargs)
        return ChatAnthropic(model=model_id, **kwargs)

    model_name = model_id.split(":", 1)[1]
    backend = provider["backend"]

    if backend == "anthropic":
        from langchain_anthropic import ChatAnthropic
        _apply_model_options(model_id, kwargs)
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
        _apply_model_options(model_id, kwargs)
        ChatGoogleGenerativeAI = _import_provider(
            "langchain_google_genai", "ChatGoogleGenerativeAI", "google",
        )
        return _construct(lambda: ChatGoogleGenerativeAI(model=model_name, **kwargs), model_id, kwargs)

    # backend == "openai": every OpenAI-compatible provider funnels through ChatOpenAI.
    ChatOpenAI = _import_provider("langchain_openai", "ChatOpenAI", "openai")
    base_url = provider.get("base_url")
    if base_url:
        if "{region}" in base_url:
            base_url = base_url.format(region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        kwargs.setdefault("base_url", base_url)
    api_key_env = provider.get("api_key_env")
    if api_key_env:
        key = os.environ.get(api_key_env)
        if key:
            kwargs.setdefault("api_key", key)
        elif not kwargs.get("api_key"):
            raise _missing_key_error(api_key_env, model_id)
    _apply_model_options(model_id, kwargs, provider.get("default_kwargs"))
    for key, value in provider.get("default_kwargs", {}).items():
        kwargs.setdefault(key, value)
    if _is_real_openai(model_id, provider, kwargs):
        ChatOpenAI = _direct_openai_class()
    return _construct(lambda: ChatOpenAI(model=model_name, **kwargs), model_id, kwargs)


def _is_real_openai(model_id: str, provider: dict, kwargs: dict) -> bool:
    """True when the OpenAI backend talks to api.openai.com itself: the plain
    `openai:`/`openai-responses:` prefixes with no base URL from the provider
    entry, the kwargs, or the two env vars langchain-openai and the openai SDK
    read. Every other OpenAI-compatible host (baseten, tinker, mantle, vercel,
    a {PREFIX}_BASE_URL provider, OPENAI_BASE_URL pointing elsewhere) is False."""
    return (
        model_id.split(":", 1)[0] in ("openai", "openai-responses")
        and not provider.get("base_url")
        and not kwargs.get("base_url") and not kwargs.get("openai_api_base")
        and not os.environ.get("OPENAI_API_BASE") and not os.environ.get("OPENAI_BASE_URL")
    )


def _direct_openai_class():
    """The ChatOpenAI subclass for api.openai.com (see _build_direct_openai_class)."""
    from langchain_openai import ChatOpenAI
    return _build_direct_openai_class(ChatOpenAI)


@functools.cache
def _build_direct_openai_class(ChatOpenAI):
    """A ChatOpenAI that marks every response it gets from api.openai.com with
    response_metadata["openai_direct"] = True. ChatOpenAI reports model_provider
    "openai" for every OpenAI-compatible host, so without this mark a response
    cannot be priced as OpenAI's. The mark is a bool under its own key, not a new
    model_provider value: content_blocks picks its translator from model_provider,
    and merge_dicts concatenates equal strings when streamed chunks are summed
    but merges equal bools cleanly. The four _generate/_stream hooks are the
    documented override points; the Responses API path goes through them too
    (it does not go through _create_chat_result). Built lazily, keyed on the base
    class, because langchain-openai is an optional dependency."""

    def mark(message) -> None:
        message.response_metadata["openai_direct"] = True

    class DirectChatOpenAI(ChatOpenAI):
        def _generate(self, *args, **kwargs):
            result = super()._generate(*args, **kwargs)
            for generation in result.generations:
                mark(generation.message)
            return result

        async def _agenerate(self, *args, **kwargs):
            result = await super()._agenerate(*args, **kwargs)
            for generation in result.generations:
                mark(generation.message)
            return result

        def _stream(self, *args, **kwargs):
            for chunk in super()._stream(*args, **kwargs):
                mark(chunk.message)
                yield chunk

        async def _astream(self, *args, **kwargs):
            async for chunk in super()._astream(*args, **kwargs):
                mark(chunk.message)
                yield chunk

    return DirectChatOpenAI


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
    # vercel:openai/gpt-oss-120b (2026-08-12): unforced (default "json_schema",
    # OpenAI's strict Structured Outputs API), the model's tool-call args
    # failed pydantic validation on ~50% of calls (12-sample and 6-sample
    # trials) — wrong field name ("code" instead of "script"), a list instead
    # of a string, or an empty {"type": "object"} echoing the schema wrapper
    # itself. The identical model/schema/prompt via openrouter:openai/gpt-oss-120b
    # came back 12/12 clean on the same default method, so this is specific to
    # how Vercel's gateway serves this model under strict mode, not the model
    # itself. Forcing method="function_calling" on vercel: gave 12/12 clean in
    # two separate trials.
    "vercel:openai/gpt-oss-120b",
    # vercel:openai/gpt-oss-20b (2026-08-13): reported failure shape matches
    # vercel:openai/gpt-oss-120b above — unforced structured output leaked
    # gpt-oss's internal harmony-format channel text (e.g. "commentary
    # to=...") instead of the tool-call schema, failing pydantic validation
    # on a single-field response model. Evidence here is two production
    # failures (via a consumer project's scope-gate classifier), not a
    # controlled multi-sample trial like the 120b entry above — but the
    # same fix (method="function_calling") is the confirmed remedy for the
    # sibling model on the same gateway.
    "vercel:openai/gpt-oss-20b",
}


def requires_forced_function_calling(model_id: str) -> bool:
    """Return True if with_structured_output's method must be forced to
    "function_calling" for this model rather than left to auto-detection
    (see _FORCED_FUNCTION_CALLING_MODELS)."""
    return model_id in _FORCED_FUNCTION_CALLING_MODELS


# Models whose provider rejects a FORCED tool_choice outright ("Tool choice
# must be auto") but works fine with tool_choice="auto" — distinct from
# _RAW_TEXT_ONLY_MODELS above (which reject structured output entirely).
# openrouter:z-ai/glm-5.3-flash (2026-08-26): with_structured_output's
# "function_calling" method sends tool_choice="any" (LangChain's forced-choice
# value), which Z.AI's OpenRouter endpoint 400s on unconditionally. Confirmed
# via a direct API call that disabling reasoning (the qwen3.7-flash/
# nemotron-3.5-lightning fix above) is NOT an option here — this endpoint
# 400s with "Reasoning is mandatory for this endpoint and cannot be disabled."
# But a direct call with tool_choice="auto" (reasoning left on) returned a
# clean tool_calls response — so the fix is forcing "auto" instead of
# disabling anything. Use bind_structured_output_auto_tool_choice() below
# instead of with_structured_output() for these models.
_AUTO_TOOL_CHOICE_MODELS: set[str] = {
    "openrouter:z-ai/glm-5.3-flash",
    # anthropic:claude-opus-5-5 (2026-09-25): a forced tool_choice (what
    # with_structured_output(method="function_calling") sends) 400s outright —
    # "tool_choice: type \"tool\" and \"any\" are not supported for this
    # model." Confirmed via a direct API call that tool_choice="auto" with
    # the same tool works fine (clean tool_use block on the first call).
    "anthropic:claude-opus-5-5",
    # anthropic:claude-sonnet-5-5: the same 400 as claude-opus-5-5 above
    # (reported against RecipeStrategy; claude-haiku-5-5 is unaffected).
    "anthropic:claude-sonnet-5-5",
}


def requires_auto_tool_choice(model_id: str) -> bool:
    """Return True if structured output must bind tools with tool_choice="auto"
    instead of the forced choice with_structured_output(method="function_calling")
    would otherwise send (see _AUTO_TOOL_CHOICE_MODELS)."""
    return model_id in _AUTO_TOOL_CHOICE_MODELS


def bind_structured_output_auto_tool_choice(
    llm: BaseChatModel, schema: type, include_raw: bool = True
):
    """Structured-output chain equivalent to
    llm.with_structured_output(schema, method="function_calling", include_raw=include_raw),
    except it binds the tool with tool_choice="auto" instead of a forced choice.

    with_structured_output has no supported way to override the tool_choice
    value it sends for "function_calling" mode (LangChain hardcodes
    tool_choice="any"), so for models that reject a forced choice (see
    requires_auto_tool_choice) the chain has to be built by hand, mirroring
    what langchain_core.language_models.chat_models.BaseChatModel.with_structured_output
    does internally for the function_calling method.
    """
    from operator import itemgetter

    from langchain_core.output_parsers.openai_tools import PydanticToolsParser
    from langchain_core.runnables import RunnableMap, RunnablePassthrough

    bound = llm.bind_tools([schema], tool_choice="auto")
    parser = PydanticToolsParser(tools=[schema], first_tool_only=True)
    if not include_raw:
        return bound | parser
    parser_assign = RunnablePassthrough.assign(
        parsed=itemgetter("raw") | parser, parsing_error=lambda _: None
    )
    parser_none = RunnablePassthrough.assign(parsed=lambda _: None)
    parser_with_fallback = parser_assign.with_fallbacks(
        [parser_none], exception_key="parsing_error"
    )
    return RunnableMap(raw=bound) | parser_with_fallback


def bind_structured_output_for_model(
    llm: BaseChatModel, schema: type, model_id: str, *,
    include_raw: bool = True, force_function_calling_for_openai: bool = False,
):
    """Return the correct structured-output chain for model_id, applying every
    known per-model quirk uniformly (see this module's model registries) —
    this is the single place that combines them, instead of each strategy's
    own generation node re-deriving (and risking drifting apart on) the same
    branching:

    1. Gemini needs method="json_mode" (LangChain's default doesn't work).
    2. A model in _AUTO_TOOL_CHOICE_MODELS rejects a forced tool_choice
       outright — bind with tool_choice="auto" instead.
    3. A model in _FORCED_FUNCTION_CALLING_MODELS needs the method forced to
       "function_calling" because auto-detection picks the wrong one for it
       specifically (do NOT force this for every model — see the regression
       this caused for mantle-oa:google.gemma-4-31b, documented on
       _FORCED_FUNCTION_CALLING_MODELS itself).
    4. Otherwise, plain with_structured_output (auto-detected method).

    force_function_calling_for_openai is a SCHEMA-specific opt-in, not a
    model quirk: pass True when schema has a free-form dict field (e.g.
    RecipeDSL's style/styles, or TriangleOp/RectangleOp's spec dicts) that
    can't satisfy OpenAI's strict json_schema structured-outputs mode
    (which requires additionalProperties: false on every object schema) —
    function_calling mode doesn't enforce that. Checked after the three
    per-model quirks above (a hard API rejection always wins), so it only
    ever changes behavior for an is_openai_model() call that would otherwise
    have fallen through to the plain default.
    """
    if is_gemini_model(model_id):
        return llm.with_structured_output(schema, method="json_mode", include_raw=include_raw)
    if requires_auto_tool_choice(model_id):
        return bind_structured_output_auto_tool_choice(llm, schema, include_raw=include_raw)
    if requires_forced_function_calling(model_id):
        return llm.with_structured_output(schema, method="function_calling", include_raw=include_raw)
    if force_function_calling_for_openai and is_openai_model(model_id):
        return llm.with_structured_output(schema, method="function_calling", include_raw=include_raw)
    return llm.with_structured_output(schema, include_raw=include_raw)


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


def config_kwargs(config: "dict | None") -> dict:
    """`config=` kwarg for a direct LLM call, only when there is a config to pass.

    Strategy nodes pass their LangGraph run config down explicitly so callbacks
    (tracing, cost tracking) reach each LLM call whether or not the runtime
    propagates context to the call site.

    The caller's `configurable` is dropped (see `inner_run_config`)."""
    config = inner_run_config(config)
    return {"config": config} if config else {}


def inner_run_config(config: "dict | None") -> dict:
    """A copy of a caller's RunnableConfig without `configurable`.

    `configurable` carries the caller's LangGraph state (thread_id, checkpoint
    ids, a checkpointer), which addresses the caller's graph. Inheriting it makes
    our own inner graphs, which have no checkpointer, try to use the caller's
    (e.g. a SqliteSaver error). Callbacks, tags, metadata and run_name still flow."""
    return {k: v for k, v in config.items() if k != "configurable"} if config else {}


def extract_text(content) -> str:
    """Return the text of a LangChain message .content, regardless of whether it's
    a plain string or a list of content blocks.

    Anthropic models (confirmed on claude-opus-5-5, 2026-09-26) return .content as
    a list of blocks — e.g. a "thinking" block followed by a "text" block — rather
    than collapsing to a bare string, on a real fraction of calls even with the
    exact same prompt/model (5 of 12 identical-shape selector calls in one batch).
    Code that assumes .content is always a string (e.g. regexing JSON out of it)
    crashes with "TypeError: expected string or bytes-like object, got 'list'" on
    exactly those calls, and retrying doesn't help when a specific prompt reliably
    triggers the list shape every time.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


def extract_usage(response: AIMessage) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a LangChain AIMessage response."""
    usage = response.usage_metadata or {}
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)


# LangChain's response_metadata["model_provider"] -> genai-prices provider_id,
# for the providers whose responses carry no cost but whose model_provider names
# exactly one pricing source. "openai" is deliberately absent: ChatOpenAI reports
# it for every OpenAI-compatible endpoint (Baseten, Tinker, Mantle, ...), so a bare
# name like gpt-oss-120b would be priced at OpenAI's rates whichever host served it.
# A response from api.openai.com itself is told apart by the openai_direct mark
# that _direct_openai_class() stamps on it.
_GENAI_PRICES_PROVIDERS = {"anthropic": "anthropic", "google_genai": "google"}


def extract_cost(response: AIMessage) -> "float | None":
    """Extract per-request cost (USD) from an AIMessage. A cost the provider
    reported is used as is: currently only OpenRouter does (via the extra_body
    opt-in in _GENERIC_DEFAULT_KWARGS, surfaced as response_metadata
    ["token_usage"]["cost"]). Anthropic, Google and OpenAI report tokens only, so their
    responses are priced from token usage with the optional `genai-prices`
    package (an estimate), as is a response from api.openai.com itself (see
    _direct_openai_class); other providers (e.g. Bedrock, OpenAI-compatible
    endpoints) return None."""
    metadata = getattr(response, "response_metadata", None)
    token_usage = metadata.get("token_usage") if isinstance(metadata, dict) else None
    cost = token_usage.get("cost") if isinstance(token_usage, dict) else None
    if isinstance(cost, bool):
        return None
    if isinstance(cost, (int, float)):
        return float(cost)
    if isinstance(cost, str):
        try:
            return float(cost)
        except ValueError:
            return None
    return _estimate_cost(response)


def _estimate_cost(response: AIMessage) -> "float | None":
    """Price a response from its token usage (output_tokens already includes
    thinking tokens, which both providers bill as output; input_tokens already
    includes cached tokens, as genai-prices expects). None when the provider is
    not in _GENAI_PRICES_PROVIDERS, the response has no usage, `genai-prices` is
    not installed, or it does not know the model."""
    metadata = getattr(response, "response_metadata", None)
    if not isinstance(metadata, dict):
        return None
    if metadata.get("openai_direct") is True:
        provider_id = "openai"
    else:
        provider_id = _GENAI_PRICES_PROVIDERS.get(metadata.get("model_provider"))
    model_name = metadata.get("model_name")
    usage = getattr(response, "usage_metadata", None)
    if provider_id is None or not isinstance(model_name, str) or not usage:
        return None
    try:
        from genai_prices import Usage, calc_price
    except ImportError:
        return None
    details = usage.get("input_token_details") or {}
    # OpenAI prefixes the cache key with the service tier ("flex_cache_read"); reading
    # only "cache_read" would bill those cached tokens at the full input rate.
    tier = metadata.get("service_tier")
    tier = tier if tier in ("flex", "priority") else None
    cache_read = details.get(f"{tier}_cache_read" if tier else "cache_read", 0)
    # Anthropic splits cache writes by TTL and zeroes the generic key when it does.
    cache_write = details.get("cache_creation", 0) or (
        details.get("ephemeral_5m_input_tokens", 0) + details.get("ephemeral_1h_input_tokens", 0)
    )
    try:
        price = calc_price(
            Usage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
            ),
            model_name, provider_id=provider_id,
            # Without this a flex/priority request is silently priced as the default tier.
            price_context={"service_tier": tier} if tier else None,
        )
    except (LookupError, ValueError):  # unknown model; inconsistent usage (cache > input)
        return None
    return float(price.total_price)

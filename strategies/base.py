from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.settings import ModelSettings

from logging import getLogger


if TYPE_CHECKING:
    from ir.renderer import Renderer


DEFAULT_AGENT_MODEL = "anthropic:claude-sonnet-4-6"
#DEFAULT_AGENT_MODEL = "openai-responses:gpt-5.1-codex-mini"


def cache_model_settings(enable: bool) -> ModelSettings:
    """Return ModelSettings with Anthropic prompt caching enabled or empty."""
    if not enable:
        return {}
    return AnthropicModelSettings(
        anthropic_cache_instructions=True,
        anthropic_cache_tool_definitions=True,
    )


class SubstanceStrategy(ABC):
    """Abstract base class for substance generation strategies."""

    logger = getLogger(__name__)

    def __init__(self, enable_cache: bool = False, thinking: bool = False):
        super().__init__()
        self.thinking = thinking
        self.model_settings: ModelSettings = cache_model_settings(enable_cache)
        if thinking:
            # Unified `thinking: True` is honored by providers whose model
            # profile sets `supports_thinking` (Anthropic, Gemini 2.5+, OpenAI
            # reasoning models). It is silently DROPPED for OpenAI-compatible
            # providers whose profile resolves to `supports_thinking=False`
            # — notably `ollama:gemma4` (the `gemma` prefix maps to
            # `google_model_profile`, which only enables thinking for
            # `gemini-2.5`/`gemini-3` names). pydantic-ai's
            # `OpenAIChatModel._translate_thinking` reads `openai_reasoning_effort`
            # before that profile gate, so adding it makes `--thinking` actually
            # engage reasoning for ollama (and other OpenAIChatModel providers).
            # It is ignored by providers that don't read it (Anthropic, native
            # Google), where `thinking: True` already works.
            self.model_settings = {
                **self.model_settings,
                'thinking': True,
                'openai_reasoning_effort': 'medium',
            }
        self.logger.info(f"Initialized strategy: {self.__class__.__name__}")

    @abstractmethod
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Build and return a configured agent for this strategy.

        Used by the web app (AGUIApp) which needs a single Agent object.
        Multi-agent strategies should return the primary/draft agent here.
        """
        ...

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: "Renderer | None" = None,
    ):
        """Run the strategy end-to-end and return an AgentRunResult.

        Override this method to implement multi-agent orchestration.
        The default delegates to build_agent().run(prompt).

        Args:
            prompt: The user's diagram request.
            model: LLM model identifier.
            renderer: Optional renderer for IR-based strategies. Raw strategies ignore this.
        """
        agent = self.build_agent(model=model)
        return await agent.run(prompt)

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic_ai import Agent

from logging import getLogger


if TYPE_CHECKING:
    from ir.renderer import Renderer


DEFAULT_AGENT_MODEL = "anthropic:claude-sonnet-4-6"
#DEFAULT_AGENT_MODEL = "openai-responses:gpt-5.1-codex-mini"

class SubstanceStrategy(ABC):
    """Abstract base class for substance generation strategies."""

    logger = getLogger(__name__)

    def __init__(self):
        super().__init__()
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

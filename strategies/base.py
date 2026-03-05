from abc import ABC, abstractmethod

from pydantic_ai import Agent

from logging import getLogger


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

    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL):
        """Run the strategy end-to-end and return an AgentRunResult.

        Override this method to implement multi-agent orchestration.
        The default delegates to build_agent().run(prompt).
        """
        agent = self.build_agent(model=model)
        return await agent.run(prompt)

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from logging import getLogger
from langgraph.graph.state import CompiledStateGraph

if TYPE_CHECKING:
    from ir.renderer import Renderer

DEFAULT_AGENT_MODEL = "anthropic:claude-sonnet-4-6"


class SubstanceStrategy(ABC):
    """Abstract base class for substance generation strategies."""

    logger = getLogger(__name__)

    def __init__(self, enable_cache: bool = False):
        super().__init__()
        self.enable_cache = enable_cache
        self.logger.info(f"Initialized strategy: {self.__class__.__name__}")

    @abstractmethod
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None) -> CompiledStateGraph:
        """Build and return a compiled LangGraph agent for this strategy.

        Used by the web app which needs a single runnable graph.
        renderer: optional Renderer to use (defaults to TikZRenderer if None).
        """
        ...

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: "Renderer | None" = None,
    ) -> Any:
        """Run the strategy end-to-end and return a StructuredRunResult.

        Override this method to implement multi-agent orchestration.
        The default delegates to build_agent().
        """
        from langchain_core.messages import HumanMessage
        graph = self.build_agent(model=model)
        result = await graph.ainvoke({"messages": [HumanMessage(content=prompt)]})
        return result

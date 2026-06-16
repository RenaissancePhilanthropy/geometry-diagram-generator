from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from logging import getLogger
from langgraph.graph.state import CompiledStateGraph

if TYPE_CHECKING:
    from ..ir.renderer import Renderer
    from langchain_core.runnables import RunnableConfig

DEFAULT_AGENT_MODEL = "anthropic:claude-sonnet-4-6"


class SubstanceStrategy(ABC):
    """Abstract base class for substance generation strategies."""

    logger = getLogger(__name__)

    def __init__(self, enable_cache: bool = False):
        super().__init__()
        self.enable_cache = enable_cache
        self.logger.info(f"Initialized strategy: {self.__class__.__name__}")

    def _build_run_config(
        self,
        config: "Optional[RunnableConfig]" = None,
        callbacks: "Optional[list]" = None,
    ) -> dict:
        """Build a LangGraph run config merging caller callbacks with env handler."""
        from ..util.tracing import get_callback_handler

        result = dict(config) if config else {}

        existing_callbacks = result.get("callbacks")

        if existing_callbacks is not None and not isinstance(existing_callbacks, list):
            # Non-list callback manager — don't attempt to merge; return as-is.
            return result

        # Collect callbacks into a list.
        merged: list = list(existing_callbacks) if existing_callbacks else []
        if "callbacks" in result:
            del result["callbacks"]

        if callbacks:
            for cb in callbacks:
                if cb is not None:
                    merged.append(cb)

        h = get_callback_handler()
        if h is not None and all(cb is not h for cb in merged):
            merged.append(h)

        if merged:
            result["callbacks"] = merged

        return result

    @property
    def _run_config(self) -> dict:
        return self._build_run_config()

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
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            config=self._run_config,
        )
        return result

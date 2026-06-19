from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional, Union

from logging import getLogger
from langgraph.graph.state import CompiledStateGraph

if TYPE_CHECKING:
    from ..ir.renderer import Renderer
    from langchain_core.runnables import RunnableConfig
    from langchain_core.callbacks import BaseCallbackManager

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
        callbacks: "Optional[Union[list, BaseCallbackManager]]" = None,
    ) -> dict:
        """Build a LangGraph run config merging caller callbacks with env handler."""
        from langchain_core.callbacks import BaseCallbackManager

        from ..util.tracing import get_callback_handler

        result = dict(config) if config else {}

        existing_callbacks = result.get("callbacks")

        # Normalize existing_callbacks from config: extract handlers if it's a manager.
        if isinstance(existing_callbacks, BaseCallbackManager):
            existing_list: list = list(existing_callbacks.handlers)
        elif existing_callbacks is not None:
            existing_list = list(existing_callbacks)
        else:
            existing_list = []

        if "callbacks" in result:
            del result["callbacks"]

        # Normalize the explicit callbacks arg: extract handlers if it's a manager.
        if isinstance(callbacks, BaseCallbackManager):
            extra: list = list(callbacks.handlers)
        else:
            extra = [cb for cb in (callbacks or []) if cb is not None]

        merged = existing_list + extra

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

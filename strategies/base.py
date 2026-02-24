from abc import ABC, abstractmethod

from pydantic_ai import Agent

from logging import getLogger


class SubstanceStrategy(ABC):
    """Abstract base class for substance generation strategies."""

    logger = getLogger(__name__)

    def __init__(self):
        super().__init__()
        self.logger.info(f"Initialized strategy: {self.__class__.__name__}")

    @abstractmethod
    def build_agent(self, domain: str) -> Agent:
        """Build and return a configured agent for this strategy."""
        ...

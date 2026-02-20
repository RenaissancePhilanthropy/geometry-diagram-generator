from abc import ABC, abstractmethod

from pydantic_ai import Agent


class SubstanceStrategy(ABC):
    @abstractmethod
    def build_agent(self, domain: str) -> Agent:
        """Build and return a configured agent for this strategy."""
        ...

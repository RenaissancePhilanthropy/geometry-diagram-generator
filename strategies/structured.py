
from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy


class StructureStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL):
        raise NotImplementedError("Structured strategy not implemented yet.")
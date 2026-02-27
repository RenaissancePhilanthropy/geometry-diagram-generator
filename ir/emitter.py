from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable


@runtime_checkable
class DiagramLike(Protocol):
    """Structural protocol satisfied by both static Diagram and dynamic domain models."""
    objects: list
    predicates: list


class SubstanceEmitter(ABC):
    """Extension point for domain-specific substance transformation.

    Each domain that needs custom serialization (e.g. expanding high-level
    constructs into lower-level Penrose code) subclasses this and implements
    emit().  If the domain needs DomainInfo or other context, accept it in
    __init__ rather than threading it through emit().
    """

    @abstractmethod
    def emit(self, diagram: DiagramLike) -> str:
        """Transform a diagram into a Penrose substance string."""
        ...

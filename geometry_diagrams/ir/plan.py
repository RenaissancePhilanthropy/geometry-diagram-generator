"""
ConstructionPlan schema for the two-phase strategy.

The planner LLM produces a ConstructionPlan describing the geometric
construction in natural language. The constructor LLM then translates
each step into a concrete DiagramIR.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ConstructionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    """Natural language description of this step, e.g. 'Find circumcenter O of triangle T'."""

    entities_produced: List[str] = Field(default_factory=list)
    """IDs of geometric entities this step defines, e.g. ['O', 'circ_T']."""

    depends_on: List[str] = Field(default_factory=list)
    """IDs of entities this step needs (must be defined in earlier steps)."""


class ConstructionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: List[ConstructionStep]
    """Ordered construction steps — each builds on previous ones."""

    geometric_checks: List[str] = Field(default_factory=list)
    """Natural language descriptions of expected geometric properties,
    e.g. 'O, G, H are collinear (Euler line)'."""

    rendering_notes: Optional[str] = None
    """Optional notes on what should be drawn / labeled / marked."""

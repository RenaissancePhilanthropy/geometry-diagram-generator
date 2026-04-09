from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


class RubricItem(BaseModel):
    id: str
    text: str
    category: str = "custom"


class BenchmarkPrompt(BaseModel):
    id: str
    prompt: str
    rubric: list[RubricItem] = []
    reference_svg: str | None = None
    tags: list[str] = []
    tier: int | None = None


class BenchmarkDefinition(BaseModel):
    id: str
    shared_rubric: list[RubricItem] = []
    prompts: list[BenchmarkPrompt]

    @field_validator("prompts")
    @classmethod
    def prompt_ids_unique(cls, prompts: list[BenchmarkPrompt]) -> list[BenchmarkPrompt]:
        seen: set[str] = set()
        for p in prompts:
            if p.id in seen:
                raise ValueError(f"Duplicate prompt id: {p.id!r}")
            seen.add(p.id)
        return prompts

    def effective_rubric(self, prompt_id: str) -> list[RubricItem]:
        """Returns prompt.rubric + shared_rubric for a given prompt_id."""
        for p in self.prompts:
            if p.id == prompt_id:
                return list(p.rubric) + list(self.shared_rubric)
        raise ValueError(f"Unknown prompt_id: {prompt_id!r}")


def load_definition(path: Path) -> BenchmarkDefinition:
    with open(path) as f:
        data = yaml.safe_load(f)
    return BenchmarkDefinition.model_validate(data)

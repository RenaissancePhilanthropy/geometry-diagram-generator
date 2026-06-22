"""Dataset loading for GEPA optimization.

Loads scenario YAML files into ScenarioData objects that can be
used as the GEPA training/validation datasets.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Ensure project root is on sys.path for evals.scenarios import
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals.scenarios import _validate_scenarios


@dataclass
class ScenarioData:
    """A single evaluation scenario — the DataInst type for GEPA.

    Contains all information needed to run and evaluate a scenario,
    including the prompt, expected properties, required labels, etc.
    """

    id: str
    prompt: str
    tier: int | None = None
    tags: list[str] = field(default_factory=list)
    expected_properties: list[dict] = field(default_factory=list)
    structural_checks: list[dict] = field(default_factory=list)
    required_labels: list[str] = field(default_factory=list)
    required_entities: list[dict] = field(default_factory=list)
    required_canvas: dict = field(default_factory=dict)
    expected_points: dict = field(default_factory=dict)
    coordinate_tolerance: float = 1e-4
    queries: list[dict] = field(default_factory=list)


def load_scenarios(path: str) -> list[ScenarioData]:
    """Load and validate a scenario YAML file into ScenarioData objects.

    Parameters
    ----------
    path : str
        Path to a YAML file containing a list of scenario definitions.

    Returns
    -------
    list[ScenarioData]
        Validated scenario data objects.
    """
    with Path(path).open() as f:
        raw = yaml.safe_load(f)
    validated = _validate_scenarios(raw)
    return [ScenarioData(**s) for s in validated]


# Preset dataset paths (relative to project root)
TRAIN_DATASET = "evals/scenarios_core.yaml"
VAL_DATASET = "evals/scenarios_generalization.yaml"
SMOKE_DATASET = "evals/scenarios_smoke.yaml"
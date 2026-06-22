"""GEPA adapter package for recipe strategy prompt optimization."""
from gepa_adapter.adapter import RecipeGEPAAdapter, ScenarioTrace
from gepa_adapter.dataset import ScenarioData, load_scenarios, TRAIN_DATASET, VAL_DATASET, SMOKE_DATASET
from gepa_adapter.scoring import ScenarioResult, compute_score, build_failure_feedback

__all__ = [
    "RecipeGEPAAdapter",
    "ScenarioData",
    "ScenarioResult",
    "ScenarioTrace",
    "load_scenarios",
    "compute_score",
    "build_failure_feedback",
    "TRAIN_DATASET",
    "VAL_DATASET",
    "SMOKE_DATASET",
]
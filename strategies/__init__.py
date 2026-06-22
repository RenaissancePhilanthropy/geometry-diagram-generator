# Apply Ollama compatibility fix before any Agent calls.
# Ollama rejects assistant messages with content=null; this patch replaces
# content=None with content="" in the OpenAI chat message builder.
# See util/ollama_compat.py for details and upstream issue reference.
import util.ollama_compat  # noqa: F401

from .base import SubstanceStrategy
from .raw_code import RawCodeStrategy
from .raw_code_with_revise import RawCodeWithReviseStrategy
from .plan_and_code import PlanAndCodeStrategy
from .structured import StructureStrategy
from .structured_plus_refine import StructuredPlusRefineStrategy
from .structured_two_phase import StructuredTwoPhaseStrategy
from .recipe import RecipeStrategy
from .progressive_tools import ProgressiveToolsStrategy, ProgressiveToolsRunResult

__all__ = [
    "SubstanceStrategy",
    "RawCodeStrategy",
    "RawCodeWithReviseStrategy",
    "PlanAndCodeStrategy",
    "StructureStrategy",
    "StructuredPlusRefineStrategy",
    "StructuredTwoPhaseStrategy",
    "RecipeStrategy",
    "ProgressiveToolsStrategy",
    "ProgressiveToolsRunResult",
]

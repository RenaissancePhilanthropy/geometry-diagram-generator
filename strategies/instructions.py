"""Shared instruction fragments for strategy prompt templates.

This module re-exports all constants from the split instruction modules for
backward compatibility. Import directly from the sub-modules for new code.
"""

from .instructions_tikz import (  # noqa: F401
    PLANNER_INSTRUCTIONS,
    RAW_TIKZ_INSTRUCTIONS,
    PLAN_CODER_TIKZ_INSTRUCTIONS,
    DRAFT_INSTRUCTIONS,
    CODE_FROM_PLAN_INSTRUCTIONS,
    REVISION_PROMPT,
    STRUCTURED_REFINE_PROMPT,
    REVISION_INSTRUCTIONS,
    REVISION_FORCE_INSTRUCTIONS,
    STRUCTURED_REFINE_INSTRUCTIONS,
)
from .instructions_structured import STRUCTURED_STRATEGY_IR_INSTRUCTIONS  # noqa: F401
from .instructions_progressive import (  # noqa: F401
    PROGRESSIVE_TOOLS_PHASE1_INSTRUCTIONS,
    PROGRESSIVE_TOOLS_PHASE2_INSTRUCTIONS,
    PROGRESSIVE_TOOLS_PHASE2_REPAIR_PREFIX,
    PROGRESSIVE_TOOLS_PHASE3_INSTRUCTIONS,
    PROGRESSIVE_TOOLS_PHASE4_INSTRUCTIONS,
)
from .instructions_two_phase import TWO_PHASE_PLANNER_INSTRUCTIONS  # noqa: F401
from .instructions_recipe import (  # noqa: F401
    RECIPE_SELECTION_SYSTEM,
    RECIPE_GENERATION_SYSTEM,
    RECIPE_DSL_QUICK_REF,
)

"""
Static analysis of TikZ/tkz-euclide code.

This module re-exports all public functions from the split analysis modules for
backward compatibility. Import directly from the sub-modules for new code:
  - util.tikz_extraction  — regex-based extraction of points, commands, marks, labels
  - util.tikz_geometry    — coordinate resolution and geometric property validation
  - util.tikz_validation  — scenario-level checks (labels, canvas, entities)
"""

from .tikz_extraction import (  # noqa: F401
    extract_defined_points,
    extract_computed_points,
    extract_draw_commands,
    extract_marks,
    extract_labels,
    extract_canvas_features,
)
from .tikz_geometry import (  # noqa: F401
    resolve_all_coordinates,
    validate_geometric_property,
)
from .tikz_validation import (  # noqa: F401
    validate_required_labels,
    validate_required_canvas,
    validate_expected_points,
    validate_required_entities,
)

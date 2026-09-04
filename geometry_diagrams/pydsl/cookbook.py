# geometry_diagrams/pydsl/cookbook.py
"""Experimental diagram cookbook: opt-in helper functions layered on top of
the core pydsl API (geometry_diagrams/pydsl/api.py).

This is ticket 08's infrastructure-only module — deliberately empty. Later
tickets (09-12 of the diagram-kinds-poc feature) add real helper functions
here, one per elementary-math diagram kind that benefits from a
higher-level construction shortcut, and list their names in
`geometry_diagrams.pydsl.__init__`'s `COOKBOOK_NAMES`.

Anything defined here is only ever handed to a sandboxed pydsl script when
the caller has opted in: `PythonFullStrategy.run(experimental_diagram_cookbook=True)`
(threaded through to `geometry_diagrams.pydsl.sandbox.run_script`'s
`enable_cookbook` flag). With the flag unset (the default everywhere,
including `RecipeStrategy`/`facade.py`, which never runs pydsl scripts at
all and has no way to enable this), none of these names ever reach the
sandbox's tool namespace — see `_sandbox_child.py`'s `_build_tool_names`.
"""
from __future__ import annotations

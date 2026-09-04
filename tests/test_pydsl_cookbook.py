"""Tests for the (currently empty) experimental cookbook module and its
gating plumbing — ticket 08's infrastructure-only scope. No real cookbook
helper functions exist yet; later tickets populate cookbook.py and
COOKBOOK_NAMES."""
from __future__ import annotations

import types

import geometry_diagrams.pydsl as pydsl_module
from geometry_diagrams.pydsl import cookbook


def test_cookbook_module_is_empty_placeholder():
    """cookbook.py exists and is importable, but exports nothing yet —
    later tickets (09-12) add real functions here."""
    public_names = [n for n in dir(cookbook) if not n.startswith("_") and n != "annotations"]
    assert public_names == []


def test_cookbook_names_is_empty_list_on_pydsl_package():
    assert pydsl_module.COOKBOOK_NAMES == []


def test_cookbook_names_is_not_exported_in_all():
    """Kept out of __all__ so it's never handed to the sandbox child as a
    regular callable tool — it's a name list, not itself an API function."""
    assert "COOKBOOK_NAMES" not in pydsl_module.__all__


def test_build_tool_names_excludes_cookbook_by_default():
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    fake_module = types.SimpleNamespace(__all__=["point", "triangle"], COOKBOOK_NAMES=["future_helper"])
    assert _build_tool_names(fake_module, enable_cookbook=False) == ["point", "triangle"]


def test_build_tool_names_includes_cookbook_when_enabled():
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    fake_module = types.SimpleNamespace(__all__=["point", "triangle"], COOKBOOK_NAMES=["future_helper"])
    assert _build_tool_names(fake_module, enable_cookbook=True) == ["point", "triangle", "future_helper"]


def test_build_tool_names_with_real_module_and_enabled_but_empty_cookbook_matches_all():
    """Regression: with COOKBOOK_NAMES still empty (this ticket's scope), enabling
    the flag must produce the exact same tool-name set as leaving it off."""
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    assert _build_tool_names(pydsl_module, enable_cookbook=True) == list(pydsl_module.__all__)
    assert _build_tool_names(pydsl_module, enable_cookbook=False) == list(pydsl_module.__all__)

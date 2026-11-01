"""Did-you-mean candidate pool includes enabled feature-group and cookbook names."""
from __future__ import annotations

from geometry_diagrams.pydsl.retry import build_retry_message

_PRIZM = "The variable `prizm` is not defined"


def test_no_hint_for_gated_name_by_default():
    assert "did you mean" not in build_retry_message(_PRIZM, "prizm()")


def test_feature_group_name_suggested_when_group_enabled():
    msg = build_retry_message(_PRIZM, "prizm()", features=["solids"])
    assert "did you mean 'prism'" in msg


def test_cookbook_name_suggested_only_when_enabled():
    text = "The variable `unit_gird` is not defined"
    assert "did you mean" not in build_retry_message(text, "unit_gird()")
    assert "did you mean 'unit_grid'" in build_retry_message(text, "unit_gird()", enable_cookbook=True)

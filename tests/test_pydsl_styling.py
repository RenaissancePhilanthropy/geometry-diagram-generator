"""Tests for pydsl's draw()/fill() styling support and the Builder plumbing
it depends on. Builder.build() previously never passed styles= to
DiagramIR at all — any style dict a script built would silently vanish.
draw()/fill() build a style dict from their kwargs and register it via
Builder._register_style(), mirroring the recipe DSL's own pattern
(recipe/lower.py's _resolve_style())."""
from geometry_diagrams.pydsl.builder import Builder, new_builder_context


def test_register_style_returns_fresh_key_and_stores_dict():
    builder = Builder()
    key = builder._register_style({"color": "red", "thick": True})
    assert key in builder._styles
    assert builder._styles[key] == {"color": "red", "thick": True}


def test_register_style_returns_distinct_keys_for_separate_calls():
    builder = Builder()
    key1 = builder._register_style({"color": "red"})
    key2 = builder._register_style({"color": "red"})
    assert key1 != key2  # no dedup, by design


def test_build_includes_registered_styles_in_diagram_ir():
    with new_builder_context() as builder:
        key = builder._register_style({"color": "blue"})
        ir = builder.build()
    assert ir.styles == {key: {"color": "blue"}}


def test_build_with_no_registered_styles_has_empty_styles_dict():
    with new_builder_context() as builder:
        ir = builder.build()
    assert ir.styles == {}

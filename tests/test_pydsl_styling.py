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


import pytest

from geometry_diagrams.pydsl.api import draw, point, polygon, segment
from geometry_diagrams.pydsl.handles import AngleRef, Point


def _drawn_style(ir, obj_id):
    from geometry_diagrams.ir.ir import Draw

    defs = [r for r in ir.render if isinstance(r, Draw) and r.obj == obj_id]
    assert len(defs) == 1
    style_key = defs[0].style
    return ir.styles[style_key] if style_key else None


def test_draw_with_no_style_kwargs_records_none_style():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) is None
    assert ir.styles == {}


def test_draw_color_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, color="red")
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"color": "red"}


def test_draw_thick_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, thick=True)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"thick": True}


def test_draw_thin_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, thin=True)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"thin": True}


def test_draw_width_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, width=2.5)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"line_width": 2.5}


def test_draw_dashed_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, dashed=True)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"dashed": True}


def test_draw_dotted_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, dotted=True)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"dotted": True}


def test_draw_arrow_start_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, arrow_start=True)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"<-": True}


def test_draw_arrow_end_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, arrow_end=True)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"->": True}


def test_draw_both_arrows_kwarg():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        draw(seg, arrow_start=True, arrow_end=True)
        ir = builder.build()
    assert _drawn_style(ir, seg.id) == {"<->": True}


def test_draw_thick_and_width_together_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        with pytest.raises(ValueError, match="at most one"):
            draw(seg, thick=True, width=2.0)


def test_draw_thick_and_thin_together_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        with pytest.raises(ValueError, match="at most one"):
            draw(seg, thick=True, thin=True)


def test_draw_dashed_and_dotted_together_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        with pytest.raises(ValueError, match="at most one"):
            draw(seg, dashed=True, dotted=True)


def test_draw_zero_width_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        with pytest.raises(ValueError, match="positive"):
            draw(seg, width=0)


def test_draw_negative_width_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        with pytest.raises(ValueError, match="positive"):
            draw(seg, width=-1)


def test_draw_still_rejects_point():
    with new_builder_context():
        p = point(0, 0)
        with pytest.raises(ValueError, match="Point"):
            draw(p)


def test_draw_still_rejects_angle_ref():
    with new_builder_context() as builder:
        from geometry_diagrams.pydsl.handles import Point as PointHandle

        a, o, b = point(0, 0), point(1, 0), point(0, 1)
        ref = AngleRef(a=a, o=o, b=b, _builder=builder)
        with pytest.raises(ValueError, match="AngleRef"):
            draw(ref)


from geometry_diagrams.pydsl.api import fill


def _filled_style_and_opacity(ir, obj_id):
    from geometry_diagrams.ir.ir import Fill

    defs = [r for r in ir.render if isinstance(r, Fill) and r.obj == obj_id]
    assert len(defs) == 1
    style_key = defs[0].style
    style = ir.styles[style_key] if style_key else None
    return style, defs[0].opacity


def test_fill_default_records_none_style_and_opacity_one():
    with new_builder_context() as builder:
        pts = [point(0, 0), point(4, 0), point(2, 3)]
        tri = polygon(*pts)
        fill(tri)
        ir = builder.build()
    style, opacity = _filled_style_and_opacity(ir, tri.id)
    assert style is None
    assert opacity == 1.0
    assert ir.styles == {}


def test_fill_color_only():
    with new_builder_context() as builder:
        pts = [point(0, 0), point(4, 0), point(2, 3)]
        tri = polygon(*pts)
        fill(tri, color="red")
        ir = builder.build()
    style, opacity = _filled_style_and_opacity(ir, tri.id)
    assert style == {"color": "red"}
    assert opacity == 1.0


def test_fill_opacity_only_still_registers_style_dict():
    """opacity != 1.0 must land in the style dict even with no color,
    since fill() writes opacity into the style dict unconditionally
    whenever it's non-default — required so the TikZ-path fix works
    regardless of whether a color is also given."""
    with new_builder_context() as builder:
        pts = [point(0, 0), point(4, 0), point(2, 3)]
        tri = polygon(*pts)
        fill(tri, opacity=0.5)
        ir = builder.build()
    style, opacity = _filled_style_and_opacity(ir, tri.id)
    assert style == {"opacity": 0.5}
    assert opacity == 0.5


def test_fill_color_and_opacity():
    with new_builder_context() as builder:
        pts = [point(0, 0), point(4, 0), point(2, 3)]
        tri = polygon(*pts)
        fill(tri, color="red", opacity=0.3)
        ir = builder.build()
    style, opacity = _filled_style_and_opacity(ir, tri.id)
    assert style == {"color": "red", "opacity": 0.3}
    assert opacity == 0.3


def test_fill_opacity_out_of_range_raises():
    with new_builder_context():
        pts = [point(0, 0), point(4, 0), point(2, 3)]
        tri = polygon(*pts)
        with pytest.raises(ValueError, match="between 0 and 1"):
            fill(tri, opacity=1.5)
        with pytest.raises(ValueError, match="between 0 and 1"):
            fill(tri, opacity=-0.1)


def test_fill_still_rejects_point():
    with new_builder_context():
        p = point(0, 0)
        with pytest.raises(ValueError, match="Point"):
            fill(p)


def test_fill_still_rejects_angle_ref():
    with new_builder_context() as builder:
        a, o, b = point(0, 0), point(1, 0), point(0, 1)
        ref = AngleRef(a=a, o=o, b=b, _builder=builder)
        with pytest.raises(ValueError, match="AngleRef"):
            fill(ref)

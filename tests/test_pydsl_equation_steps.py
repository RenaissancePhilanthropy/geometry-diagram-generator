# tests/test_pydsl_equation_steps.py
"""Tests for the equation_steps() pydsl primitive — a general, ungated
helper (ticket 06) that stacks label_text() calls vertically and sizes an
explicit canvas() to fit them. Follows the same conventions as
test_pydsl_draw_brace.py (unit seam) and test_pydsl_composite_demo.py
(end-to-end rendering seam), since equation_steps composes two existing
primitives (LabelFreeText via label_text(), Canvas via canvas()) rather
than introducing a new IR RenderOp kind."""
import re

import pytest

from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.ir import LabelFreeText
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.pydsl.api import canvas, equation_steps
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.pydsl.sandbox import run_script


# ---------------------------------------------------------------------------
# Seam (a): equation_steps() builds a correct DiagramIR fragment
# ---------------------------------------------------------------------------

def test_equation_steps_records_stacked_label_free_text_ops_with_decreasing_y():
    with new_builder_context() as builder:
        equation_steps(["3x + 5 = 20", "3x = 15", "x = 5"])
        ir = builder.build()
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 3
    assert [l.text for l in labels] == ["3x + 5 = 20", "3x = 15", "x = 5"]
    ys = [l.at[1] for l in labels]
    assert ys == [0.0, -1.2, -2.4]
    assert all(l.at[0] == 0.0 for l in labels)


def test_equation_steps_respects_x_and_y_step_overrides():
    with new_builder_context() as builder:
        equation_steps(["a", "b"], x=3.0, y_step=2.0)
        ir = builder.build()
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert [l.at for l in labels] == [[3.0, 0.0], [3.0, -2.0]]


def test_equation_steps_sets_canvas_sized_to_number_of_lines():
    with new_builder_context() as builder:
        equation_steps(["a", "b", "c", "d"], y_step=1.2)
        ir = builder.build()
    assert ir.canvas is not None
    # 4 lines at y = 0, -1.2, -2.4, -3.6 must all fall strictly inside the
    # canvas y-range, with the range sized to the line count (not some
    # unrelated fixed constant).
    assert ir.canvas.ymin < -3.6
    assert ir.canvas.ymax > 0.0
    assert ir.canvas.xmin < 0.0 < ir.canvas.xmax


def test_equation_steps_does_not_call_canvas_twice():
    # equation_steps() calls canvas() itself; a script that already called
    # canvas() must get the existing "only one call allowed" error rather
    # than silently overwriting it or crashing some other way.
    with new_builder_context():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        with pytest.raises(ValueError):
            equation_steps(["a", "b"])


def test_equation_steps_rejects_empty_lines():
    with new_builder_context():
        with pytest.raises(ValueError):
            equation_steps([])


def test_equation_steps_requires_a_builder():
    with pytest.raises(RuntimeError):
        equation_steps(["a"])


def test_equation_steps_is_exported_ungated_in_pydsl_all():
    import geometry_diagrams.pydsl as pydsl_module

    assert "equation_steps" in pydsl_module.__all__
    assert pydsl_module.equation_steps is equation_steps


def test_equation_steps_appears_in_generated_stub_with_no_flag_required():
    from geometry_diagrams.pydsl.stub import generate_stub

    stub = generate_stub()
    assert "def equation_steps(" in stub


def test_equation_steps_works_through_the_real_sandbox():
    script = "equation_steps(['3x + 5 = 20', '3x = 15', 'x = 5'])\n"
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    labels = [r for r in result.diagram_ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 3
    assert result.diagram_ir.canvas is not None


# ---------------------------------------------------------------------------
# Seam (b): end-to-end rendering through to_svg.py and to_tikz.py
# ---------------------------------------------------------------------------

_ALGEBRA_STEPS = [
    "3x + 5 = 20",
    r"3x + 5 = 20 \Rightarrow 3x = 15",
    r"x = \frac{15}{3}",
    "x = 5",
]


def _build_equation_steps_ir(lines=_ALGEBRA_STEPS, y_step=1.2):
    with new_builder_context() as builder:
        equation_steps(lines, y_step=y_step)
        ir = builder.build()
    return ir


def test_equation_steps_ir_has_zero_geometric_defines():
    # Acceptance: a DiagramIR built purely from equation_steps(...) has zero
    # points/segments/circles/etc — only LabelFreeText render ops.
    ir = _build_equation_steps_ir()
    assert ir.define == []
    assert len(ir.render) == len(_ALGEBRA_STEPS)


def test_equation_steps_ir_compiles_and_passes_checks():
    ir = _build_equation_steps_ir()
    sym = compile_defs(ir)  # must not raise despite zero geometric defines
    assert run_checks(ir.checks, sym) == []


def test_equation_steps_renders_to_svg_with_one_element_per_line():
    ir = _build_equation_steps_ir()
    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    assert svg.count('data-role="label-free-text"') == len(_ALGEBRA_STEPS)


def _svg_label_ys(svg: str) -> "list[float]":
    """Extract each label-free-text element's y coordinate in render order.
    Plain lines render as <text x=".." y="..">; fraction/sub-superscript/
    arrow lines render as mathtext <g transform="translate(x,y)"> paths —
    the two shapes anchor text differently (dominant-baseline="central" vs.
    a glyph-path origin), so callers comparing gaps should use same-shape
    lines only."""
    ys = []
    for tag in re.finditer(r'<(?:text|g) data-role="label-free-text"[^>]*>', svg):
        el = tag.group()
        m_text = re.search(r'\by="([-\d.]+)"', el)
        m_g = re.search(r'translate\(([-\d.]+),([-\d.]+)\)', el)
        ys.append(float(m_text.group(1)) if m_text else float(m_g.group(2)))
    return ys


def test_equation_steps_renders_to_svg_with_consistent_vertical_spacing():
    # Plain (non-LaTeX-heavy) lines all render through the same <text>
    # shape, so their gaps must be exactly equal — proof that the
    # one-construction-unit-per-line + auto canvas approach produces
    # deterministic pixel spacing (the ticket's core rationale).
    ir = _build_equation_steps_ir(lines=["a = 1", "b = 2", "c = 3", "d = 4"])
    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    ys = _svg_label_ys(svg)
    assert len(ys) == 4
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    assert gaps[0] > 0  # later lines sit lower on the page (larger SVG y)
    assert all(gap == pytest.approx(gaps[0], abs=0.05) for gap in gaps)


def test_equation_steps_renders_to_svg_with_latex_heavy_lines_in_top_to_bottom_order():
    # Mixing plain and mathtext (fraction/arrow) lines changes the glyph
    # anchor per-line, but stacking order must still be preserved: each
    # line's pixel y strictly increases down the page.
    ir = _build_equation_steps_ir()
    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    ys = _svg_label_ys(svg)
    assert len(ys) == len(_ALGEBRA_STEPS)
    assert ys == sorted(ys)
    assert len(set(ys)) == len(ys)


def test_equation_steps_renders_to_tikz_with_one_node_per_line():
    ir = _build_equation_steps_ir()
    sym = compile_defs(ir)
    tikz = ir_to_tikz(ir, sym)
    assert len(re.findall(r"\\node at", tikz)) == len(_ALGEBRA_STEPS)


def test_equation_steps_renders_to_tikz_preserving_latex_fraction_and_arrow():
    ir = _build_equation_steps_ir()
    sym = compile_defs(ir)
    tikz = ir_to_tikz(ir, sym)
    assert r"\Rightarrow" in tikz
    assert r"\frac{15}{3}" in tikz


def test_equation_steps_renders_to_tikz_with_consistent_vertical_spacing():
    ir = _build_equation_steps_ir(y_step=1.2)
    sym = compile_defs(ir)
    tikz = ir_to_tikz(ir, sym)
    ys = [float(m) for m in re.findall(r"\\node at \([-\d.]+,([-\d.]+)\)", tikz)]
    assert ys == [0.0, -1.2, -2.4, -3.6]

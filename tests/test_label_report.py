"""evals/label_report.py: the SVG-only label measurements, figure sampling and the comparison."""
from __future__ import annotations

import json
import sys

import pytest

from evals import label_report as lr
from geometry_diagrams.ir import ir

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">
<circle data-ir-id="O" data-type="point" cx="100.00" cy="100.00" r="2.5" fill="black" />
<line data-ir-id="s" data-type="segment" data-endpoints="A,B" x1="0.00" y1="200.00" x2="200.00" y2="200.00" stroke="black" />
<circle data-ir-id="c" data-type="circle" data-center="Z" cx="300.00" cy="100.00" r="40" fill="none" />
{labels}
</svg>"""


def _label(role, for_, bbox, text="x"):
    b = ",".join(str(v) for v in bbox)
    return f'<text data-role="{role}" data-for="{for_}" data-bbox="{b}" data-label-text="{text}" x="0" y="0">{text}</text>'


def _measure(*labels):
    return lr.measure_svg(SVG.format(labels="\n".join(labels)))


def test_a_point_label_on_its_dot_far_from_it_and_beside_it():
    on = _measure(_label("label-point", "O", (98, 98, 106, 106)))
    far = _measure(_label("label-point", "O", (150, 90, 160, 110)))
    ok = _measure(_label("label-point", "O", (108, 94, 118, 106)))
    assert (on["point_on_dot"], on["point_far"]) == (1, 0)
    assert (far["point_on_dot"], far["point_far"]) == (0, 1)
    assert (ok["point_on_dot"], ok["point_far"]) == (0, 0) and ok["labels"][0]["gap"] == 8.0


def test_a_segment_label_beside_far_from_and_past_the_end_of_its_line():
    beside = _measure(_label("label-segment", "s", (90, 180, 110, 192)))   # centre 13 px above the line, mid
    far = _measure(_label("label-segment", "s", (90, 120, 110, 140)))      # 70 px above
    past = _measure(_label("label-segment", "s", (260, 188, 280, 198)))    # beside the line but at t = 1.35
    assert [m["segment_far"] for m in (beside, far, past)] == [0, 1, 1]
    assert beside["labels"][0]["drift"] == 14.0 and beside["labels"][0]["t"] == 0.5


def test_a_circle_centre_locates_a_point_that_is_not_drawn_and_unlocatable_labels_are_unmeasured():
    by_circle = _measure(_label("label-point", "Z", (298, 98, 306, 106)))
    unknown = _measure(_label("label-point", "nowhere", (0, 0, 10, 10)), _label("label-segment", "arc9", (0, 0, 10, 10)))
    assert by_circle["point_on_dot"] == 1 and unknown["unmeasured"] == 2 and unknown["point_far"] == 0


def test_overlapping_label_boxes_are_counted_once_per_pair():
    m = _measure(_label("label-point", "O", (108, 94, 118, 106)), _label("label-angle", "a", (112, 98, 130, 110)),
                 _label("label-free-text", "", (200, 10, 210, 20)))
    assert m["label_overlaps"] == 1 and len(m["labels"]) == 3


# --- sampling ----------------------------------------------------------------------------

def _record(sid, x, **extra):
    d = ir.DiagramIR(canvas=ir.Canvas(xmin=0, xmax=5, ymin=0, ymax=5), define=[ir.PointFixed(id="A", x=x, y=1.0)],
                     render=[ir.LabelPoint(p="A", text=None)])
    return {"scenario_id": sid, "strategy": "recipe", "svg_rendered": True, "diagram_ir": d.model_dump(mode="json"), **extra}


def test_load_figures_dedups_by_content_skips_records_without_a_figure_and_samples_by_seed(tmp_path):
    rows = [_record("a", 1.0), _record("a-again", 1.0), _record("b", 2.0), _record("c", 3.0),
            {"scenario_id": "no-ir"}, _record("d", 4.0, svg_rendered=False)]
    f = tmp_path / "r.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    allf = lr.load_figures(f, 100, 0)
    assert len(allf) == 3 and {x["scenario"] for x in allf} <= {"a", "a-again", "b", "c"}
    assert [x["key"] for x in lr.load_figures(tmp_path, 2, 7)] == [x["key"] for x in lr.load_figures(tmp_path, 2, 7)]
    assert len(lr.load_figures(tmp_path, 2, 7)) == 2


def test_run_report_renders_and_measures_a_stored_figure():
    fig = {"key": "k1", "scenario": "s", "strategy": "recipe", "diagram_ir": _record("s", 2.0)["diagram_ir"]}
    report = lr.run_report([fig], progress=False)
    row = report["figures"]["k1"]
    assert "error" not in row and row["labels"][0]["role"] == "label-point" and report["failed"] == 0
    assert lr.totals(report)["labels"] == 1


def test_a_stored_figure_that_cannot_render_is_recorded_not_raised():
    report = lr.run_report([{"key": "bad", "scenario": "s", "strategy": "x", "diagram_ir": {"nonsense": 1}}], progress=False)
    assert "error" in report["figures"]["bad"] and report["failed"] == 1 and lr.totals(report)["figures"] == 0


# --- comparison and code root --------------------------------------------------------------

def _report(code, **per_figure):
    figs = {k: {"scenario": k, "strategy": "s", "labels": [], "unmeasured": 0,
                **{m: 0 for m in lr._MEASURES}, **v} for k, v in per_figure.items()}
    return {"code": code, "figures": figs, "failed": 0}


def test_compare_reports_totals_and_which_figures_got_worse():
    before = _report("old", a={"point_on_dot": 2}, b={"segment_far": 1}, c={})
    after = _report("new", a={"point_on_dot": 0}, b={"segment_far": 3}, c={"label_overlaps": 1})
    text = lr.compare(before, after)
    assert "figures compared: 3" in text
    assert "point_on_dot" in text and "2 ->     0  (-2)" in text
    assert "segment_far" in text and "1 ->     3  (+2)" in text
    assert "worse on segment_far: b[b] +2" in text and "worse on label_overlaps: c[c] +1" in text
    assert "worse on point_on_dot" not in text


def test_code_root_must_actually_supply_geometry_diagrams(tmp_path):
    before = list(sys.path)
    try:
        with pytest.raises(SystemExit, match="geometry_diagrams was imported from"):
            lr._use_code_root(str(tmp_path))  # a directory with no such package: the repo's copy is already loaded
    finally:
        sys.path[:] = before
    lr._use_code_root(None)  # no root: nothing to do

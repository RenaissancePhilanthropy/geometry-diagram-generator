"""Scenario point names resolve to figure ids: exact id, then the text of the one
label that shows it, then the script's variable name."""
from __future__ import annotations

import pytest

from evals.property_names import NameResolutionError, NameResolver
from evals.run import _collect_check_outcomes
from evals.sympy_checks import _validate_properties_sympy
from geometry_diagrams.ir import ir


def _diagram(*labels: tuple[str, str | None]) -> ir.DiagramIR:
    defs = [ir.PointFixed(id=pid, x=float(i), y=0.0) for i, (pid, _) in enumerate(labels)]
    render = [ir.LabelPoint(p=pid, text=text) for pid, text in labels]
    return ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=5, ymin=-1, ymax=1), define=defs, render=render,
    )


PTS = {"__pydsl_pt_1": (0.0, 0.0), "__pydsl_pt_2": (4.0, 0.0), "__pydsl_pt_3": (2.0, 0.0), "Pp": (1.0, 1.0)}
DIAGRAM = _diagram(("__pydsl_pt_1", "A"), ("__pydsl_pt_2", "B"), ("__pydsl_pt_3", "M"), ("Pp", "P"))


def test_exact_id_wins_and_is_not_recorded():
    r = NameResolver(PTS, None)  # no labels to contradict the ids
    assert r.resolve("Pp") == "Pp" and r.resolve("__pydsl_pt_1") == "__pydsl_pt_1" and r.resolved == {}
    # a point labelled with another text is not reached by its id: the reader sees the label
    with pytest.raises(NameResolutionError):
        NameResolver(PTS, DIAGRAM).resolve("__pydsl_pt_1")


def test_label_text_resolves_an_opaque_or_renamed_point():
    r = NameResolver(PTS, DIAGRAM)
    assert r.resolve("A") == "__pydsl_pt_1" and r.resolve("P") == "Pp"
    assert r.resolved == {"A": "__pydsl_pt_1", "P": "Pp"}


def test_label_text_ignores_math_delimiters_and_accepts_prime_spellings():
    pts = {"x1": (0.0, 0.0)}
    d = _diagram(("x1", "$A'$"))
    r = NameResolver(pts, d)
    assert r.resolve("A'") == "x1" and r.resolve("A_prime") == "x1"


def test_variable_ids_are_the_last_resort():
    r = NameResolver(PTS, DIAGRAM, {"mid": "__pydsl_pt_3", "ghost": "not_a_point"})
    assert r.resolve("mid") == "__pydsl_pt_3"
    with pytest.raises(NameResolutionError) as ei:
        r.resolve("ghost")
    assert ei.value.kind == "unresolved"


def test_a_label_wins_over_a_variable_name():
    r = NameResolver(PTS, DIAGRAM, {"A": "__pydsl_pt_2"})
    assert r.resolve("A") == "__pydsl_pt_1"


def test_a_text_on_several_points_is_ambiguous():
    d = _diagram(("p1", "A"), ("p2", "A"))
    r = NameResolver({"p1": (0.0, 0.0), "p2": (1.0, 0.0)}, d)
    with pytest.raises(NameResolutionError, match="several points") as ei:
        r.resolve("A")
    assert ei.value.kind == "ambiguous"


def test_an_unknown_name_is_unresolved_and_labels_on_missing_points_are_ignored():
    r = NameResolver({"p1": (0.0, 0.0)}, _diagram(("p1", "A"), ("gone", "Z")))
    with pytest.raises(NameResolutionError) as ei:
        r.resolve("Z")
    assert ei.value.kind == "unresolved"


def test_resolve_args_recurses_and_keeps_numbers():
    r = NameResolver(PTS, DIAGRAM)
    assert r.resolve_args([["A", "B"], 5.0]) == [["__pydsl_pt_1", "__pydsl_pt_2"], 5.0]


def _props(*props):
    return list(props)


def test_properties_use_the_resolver_and_report_what_was_resolved():
    props = _props({"name": "m", "type": "midpoint", "args": ["M", "A", "B"]})
    (plain,) = _validate_properties_sympy(props, PTS)
    assert plain["passed"] is False and "not in symbol table" in plain["message"]
    (res,) = _validate_properties_sympy(props, PTS, resolver=NameResolver(PTS, DIAGRAM))
    assert res["passed"] is True
    assert res["resolved_names"] == {"M": "__pydsl_pt_3", "A": "__pydsl_pt_1", "B": "__pydsl_pt_2"}
    assert "resolution" not in res


def test_an_unresolved_name_fails_with_its_own_marker_and_gate_suffix():
    props = _props({"name": "m", "type": "midpoint", "args": ["Q", "A", "B"]})
    (r,) = _validate_properties_sympy(props, PTS, resolver=NameResolver(PTS, DIAGRAM))
    assert r["passed"] is False and r["resolution"] == "unresolved"
    failures, _, _ = _collect_check_outcomes({"sympy_property_checks": [r]})
    assert failures == ["property:m:unresolved"]


def test_a_geometry_failure_keeps_the_plain_gate_name():
    props = _props({"name": "m", "type": "midpoint", "args": ["P", "A", "B"]})
    (r,) = _validate_properties_sympy(props, PTS, resolver=NameResolver(PTS, DIAGRAM))
    assert r["passed"] is False and "resolution" not in r
    failures, _, _ = _collect_check_outcomes({"sympy_property_checks": [r]})
    assert failures == ["property:m"]


def test_render_only_and_unknown_types_do_not_resolve_their_text_arguments():
    props = _props(
        {"name": "l", "type": "label_present", "args": ["not a point"]},
        {"name": "u", "type": "future_check", "args": ["not a point"], "unsupported": True},
    )
    results = _validate_properties_sympy(props, PTS, resolver=NameResolver(PTS, DIAGRAM))
    assert [r["passed"] for r in results] == [True, None]
    assert all("resolution" not in r for r in results)


def test_the_facade_label_lookup_is_shared():
    from geometry_diagrams.facade import labeled_point_ids as via_facade
    from geometry_diagrams.ir.point_labels import labeled_point_ids
    assert via_facade is labeled_point_ids  # the facade re-exports the shared helper
    assert labeled_point_ids(DIAGRAM)["P"] == {"Pp"}
    assert labeled_point_ids(_diagram(("p", None))) == {}


def test_a_primed_name_matches_an_id_spelling_it_another_way():
    pts = {"A": (0.0, 0.0), "Ap": (1.0, 0.0), "Bprime": (2.0, 0.0)}
    r = NameResolver(pts, None)
    assert r.resolve("A'") == "Ap" and r.resolve("B'") == "Bprime"
    assert r.resolve("A") == "A"  # an unprimed name is never matched loosely
    with pytest.raises(NameResolutionError):
        r.resolve("C'")


def test_two_ids_for_a_primed_name_are_ambiguous():
    r = NameResolver({"Ap": (0.0, 0.0), "A1": (1.0, 0.0)}, None)
    with pytest.raises(NameResolutionError) as ei:
        r.resolve("A'")
    assert ei.value.kind == "ambiguous"


# --- review findings: no silent wrong resolution -------------------------------------

def _labelled(points: dict, labels: dict) -> NameResolver:
    """A resolver over ``points`` where ``labels`` maps point id -> label text."""
    d = ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=5, ymin=-1, ymax=1),
        define=[ir.PointFixed(id=pid, x=float(i), y=0.0) for i, pid in enumerate(points)],
        render=[ir.LabelPoint(p=pid, text=t) for pid, t in labels.items()],
    )
    return NameResolver({pid: (float(i), 0.0) for i, pid in enumerate(points)}, d)


def test_a_loose_prime_id_is_skipped_when_its_own_label_says_it_is_another_point():
    r = _labelled(["P1"], {"P1": "$P_1$"})
    with pytest.raises(NameResolutionError) as ei:
        r.resolve("P'")
    assert ei.value.kind == "unresolved"
    assert _labelled(["Pp"], {}).resolve("P'") == "Pp"  # an unlabelled loose id is still taken
    assert _labelled(["Pp"], {"Pp": "P'"}).resolve("P'") == "Pp"


def test_a_strict_prime_spelling_beats_a_loose_one():
    assert NameResolver({"Aprime": (0.0, 0.0), "A1": (1.0, 0.0)}, None).resolve("A'") == "Aprime"
    assert NameResolver({"A_prime": (0.0, 0.0), "Ap": (1.0, 0.0)}, None).resolve("A'") == "A_prime"


@pytest.mark.parametrize("points,labels,name", [
    (["A", "pt1"], {"pt1": "A"}, "A"),                    # a helper id vs the point labelled "A"
    (["M", "q", "s"], {"q": "M", "s": "M"}, "M"),         # two other points show the name
    (["A", "B"], {"A": "B", "B": "A"}, "B"),              # swapped labels
])
def test_an_id_and_a_different_point_labelled_with_the_same_name_is_ambiguous(points, labels, name):
    with pytest.raises(NameResolutionError) as ei:
        _labelled(points, labels).resolve(name)
    assert ei.value.kind == "ambiguous"


def test_an_id_that_labels_itself_resolves_to_itself():
    assert _labelled(["A", "B"], {"A": "A", "B": "B"}).resolve("A") == "A"
    assert _labelled(["A"], {"A": "$A$"}).resolve("A") == "A"


def test_a_label_beats_a_loose_prime_id_and_subscripts_are_read():
    r = _labelled(["x", "A1"], {"x": "A'"})
    assert r.resolve("A'") == "x"
    assert _labelled(["x"], {"x": "$A_1$"}).resolve("A_1") == "x"


def test_a_failed_property_message_names_the_resolved_ids():
    props = [{"name": "c", "type": "collinear", "args": ["A", "B", "P"]}]
    pts = {**PTS, "__pydsl_pt_4": (1.0, 5.0)}
    d = _diagram(("__pydsl_pt_1", "A"), ("__pydsl_pt_2", "B"), ("__pydsl_pt_4", "P"))
    (r,) = _validate_properties_sympy(props, pts, resolver=NameResolver(pts, d))
    assert r["passed"] is False and "[names: A -> __pydsl_pt_1" in r["message"]
    assert r["resolved_names"]["P"] == "__pydsl_pt_4"


# --- the eval runner wiring ----------------------------------------------------------

@pytest.mark.asyncio
async def test_run_scenario_resolves_names_and_gates_on_the_marker(monkeypatch, tmp_path):
    from evals.run import _STRATEGY_MAP, run_scenario
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    d = ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=5, ymin=-1, ymax=1),
        define=[
            ir.PointFixed(id="pa", x=0.0, y=0.0), ir.PointFixed(id="pb", x=4.0, y=0.0),
            ir.PointFixed(id="pm", x=2.0, y=0.0),
        ],
        render=[ir.LabelPoint(p="pa", text="A"), ir.LabelPoint(p="pb", text="B"), ir.LabelPoint(p="pm", text="M")],
    )

    class _S:
        def __init__(self, enable_cache: bool = False, features=None):
            self.features = frozenset(features or ())

        async def run(self, prompt, model=None, renderer=None, **kw):
            return await run_ir_pipeline(d, SVGRenderer())

    monkeypatch.setitem(_STRATEGY_MAP, "structured", _S)

    async def run(*props, **kw):
        sc = {"id": "s", "prompt": "p", "expected_properties": list(props)}
        return await run_scenario(sc, "structured", "m", 1, tmp_path, "b", **kw)

    ok = await run({"name": "m", "type": "midpoint", "args": ["M", "A", "B"]})
    assert ok["variable_ids"] == {}  # the record carries python_full's variable names (none for this strategy)
    assert ok["sympy_property_checks"][0]["passed"] is True
    assert ok["sympy_property_checks"][0]["resolved_names"] == {"M": "pm", "A": "pa", "B": "pb"}
    assert ok["gate_status"] == "pass"

    missing = await run({"name": "m", "type": "midpoint", "args": ["Q", "A", "B"]})
    assert missing["gate_failures"] == ["property:m:unresolved"] and missing["gate_status"] == "fail"

    wrong = await run({"name": "m", "type": "midpoint", "args": ["A", "A", "B"]})
    assert wrong["gate_failures"] == ["property:m"]

    off = await run({"name": "m", "type": "midpoint", "args": ["Q", "A", "B"]}, gate_properties=False)
    assert off["gate_failures"] == [] and off["sympy_property_checks"][0]["resolution"] == "unresolved"


# --- second review ---------------------------------------------------------------------

def test_two_names_that_resolve_to_one_point_are_ambiguous_not_a_trivial_pass():
    r = _labelled(["p", "m"], {"p": "A"})
    r._labels["B"] = {"p"}  # a second label text on the same point
    r._own["p"] = {"A", "B"}
    with pytest.raises(NameResolutionError, match="same point") as ei:
        r.resolve_args(["A", "B"])
    assert ei.value.kind == "ambiguous"
    props = [{"name": "m", "type": "equal_lengths", "args": [["A", "m"], ["B", "m"]]}]
    (res,) = _validate_properties_sympy(props, r._points, resolver=r)
    assert res["passed"] is False and res["resolution"] == "ambiguous"


def test_the_same_name_repeated_is_not_a_collapse():
    r = _labelled(["a", "b"], {"a": "A", "b": "B"})
    assert r.resolve_args([["A", "B"], ["A", "B"]]) == [["a", "b"], ["a", "b"]]


def test_an_exact_id_whose_own_label_shows_another_text_is_not_a_match():
    r = _labelled(["A", "B"], {"A": "B"})  # id A shows "B"; id B is unlabelled; nobody shows "A"
    with pytest.raises(NameResolutionError) as ei:
        r.resolve("A")
    assert ei.value.kind == "unresolved"


def test_the_figure_that_relabels_a_stock_id_is_flagged_for_both_names():
    r = _labelled(["A", "B"], {"A": "B"})
    with pytest.raises(NameResolutionError) as ei:
        r.resolve("B")
    assert ei.value.kind == "ambiguous"


def test_an_auto_labelled_point_shows_its_id_so_it_is_not_a_loose_prime_match():
    d = ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=5, ymin=-1, ymax=1),
        define=[ir.PointFixed(id="A1", x=0.0, y=0.0)],
        render=[ir.LabelPoint(p="A1", text=None)],
    )
    r = NameResolver({"A1": (0.0, 0.0)}, d)
    with pytest.raises(NameResolutionError) as ei:
        r.resolve("A'")
    assert ei.value.kind == "unresolved"
    assert r.resolve("A1") == "A1"
    # a point with no label at all still takes the loose spelling
    assert NameResolver({"A1": (0.0, 0.0)}, ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=5, ymin=-1, ymax=1),
        define=[ir.PointFixed(id="A1", x=0.0, y=0.0)], render=[])).resolve("A'") == "A1"


def test_unicode_primes_and_braced_subscripts_match():
    assert _labelled(["x"], {"x": "A′"}).resolve("A'") == "x"
    assert _labelled(["x"], {"x": "$A_{1}$"}).resolve("A_1") == "x"
    assert _labelled(["x"], {"x": "$A_1$"}).resolve("A_{1}") == "x"


# --- one gate-failure rule for the runner and regrade ----------------------------------

def test_property_gate_failures_names_naming_problems_and_dedups_against_tikz():
    from evals.gate import property_gate_failures
    results = [
        {"name": "geo", "passed": False}, {"name": "nm", "passed": False, "resolution": "unresolved"},
        {"name": "amb", "passed": False, "resolution": "ambiguous"}, {"name": "ok", "passed": True},
        {"name": "skip", "passed": None},
    ]
    failures, skipped = property_gate_failures(results)
    assert failures == ["property:geo", "property:nm:unresolved", "property:amb:ambiguous"]
    assert skipped == ["property:skip"]
    failures, _ = property_gate_failures(results, already_failed={"geo"})
    assert "property:geo" not in failures and "property:nm:unresolved" in failures
    assert property_gate_failures(results, gate=False) == ([], ["property:skip"])


def test_a_property_the_tikz_check_also_failed_is_not_counted_twice():
    rec = {
        "tikz_checks": {"m": {"passed": False, "type": "midpoint"}},
        "sympy_property_checks": [{"name": "m", "type": "midpoint", "passed": False, "message": ""}],
    }
    failures, _, _ = _collect_check_outcomes(rec)
    assert failures == ["m"]


def test_leaderboard_separates_point_naming_failures_from_geometry():
    from evals.leaderboard_analyze import _failure_modes
    recs = [{"gate_status": "fail", "gate_failures": [
        "property:a", "property:b:unresolved", "property:c:ambiguous"]}]
    assert dict(_failure_modes(recs)) == {"property": 1, "property:naming": 2}
    plot = pytest.importorskip("evals.leaderboard_plot")
    assert plot._failure_bucket({}, "property", "property:b:unresolved") == "point naming"
    assert plot._failure_bucket({}, "property", "property:a") == "geometric predicate"

"""Eval records persist pipeline warnings; scenarios may gate on them."""
from __future__ import annotations

import pytest

from evals.run import _STRATEGY_MAP, run_scenario
from evals.scenarios import _validate_scenarios, load_scenarios
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult, run_ir_pipeline

SUB = "does not match its true length"


def _diagram(label_text=None, length_label=None):
    prism = ir.RectangularPrism(
        id="P", origin="O", length=10, width=6, height=5, **({"length_label": length_label} if length_label else {})
    )
    render = [ir.Draw(obj="P")]
    if label_text is not None:
        render.append(ir.LabelSegment(seg="P_e_010_110", text=label_text))
    return ir.DiagramIR(define=[ir.PointFixed(id="O", x=0, y=0), prism], render=render)


def _make_strategy(builder):
    class _S:
        def __init__(self, enable_cache: bool = False, features=None):
            self.features = frozenset(features or ())

        async def run(self, prompt, model=None, renderer=None, **kw):
            return await builder()

    return _S


def _pipeline(diagram):
    async def build():
        return await run_ir_pipeline(diagram, SVGRenderer())
    return _make_strategy(build)


def _known(warnings):
    async def build():
        d = _diagram()
        r = await run_ir_pipeline(d, SVGRenderer())
        r.warnings = list(warnings)
        return r
    return _make_strategy(build)


def _failing():
    async def build():
        raise RuntimeError("boom")
    return _make_strategy(build)


async def _run(monkeypatch, tmp_path, strategy, **sc):
    monkeypatch.setitem(_STRATEGY_MAP, "structured", strategy)
    scenario = {"id": "s", "prompt": "p", **sc}
    return await run_scenario(scenario, "structured", "m", 1, tmp_path, "b")


async def test_record_contains_warnings(monkeypatch, tmp_path):
    rec = await _run(monkeypatch, tmp_path, _known(["w1", "w2"]))
    assert rec["warnings"] == ["w1", "w2"]
    rec = await _run(monkeypatch, tmp_path, _known([]))
    assert rec["warnings"] == []


async def test_failed_run_records_empty_warnings(monkeypatch, tmp_path):
    rec = await _run(monkeypatch, tmp_path, _failing())
    assert rec["warnings"] == [] and rec["error"] == "boom"


async def test_gate_fails_on_matching_warning_only(monkeypatch, tmp_path):
    rec = await _run(monkeypatch, tmp_path, _known(["x flagged y"]), fail_on_warnings=["flagged"])
    assert rec["gate_status"] == "fail" and "warning:flagged" in rec["gate_failures"]
    rec = await _run(monkeypatch, tmp_path, _known(["x flagged y"]), fail_on_warnings=["Flagged"])
    assert rec["gate_status"] == "pass" and rec["gate_failures"] == []
    rec = await _run(monkeypatch, tmp_path, _known(["x flagged y"]))
    assert rec["gate_status"] == "pass"


async def test_one_entry_per_matching_substring(monkeypatch, tmp_path):
    rec = await _run(
        monkeypatch, tmp_path, _known(["alpha beta", "beta"]),
        fail_on_warnings=["beta", "gamma", "alpha"],
    )
    assert rec["gate_failures"] == ["warning:beta", "warning:alpha"]


async def test_end_to_end_manual_label(monkeypatch, tmp_path):
    bad = await _run(monkeypatch, tmp_path, _pipeline(_diagram("5")), fail_on_warnings=[SUB])
    assert any(SUB in w for w in bad["warnings"])
    assert bad["gate_status"] == "fail" and f"warning:{SUB}" in bad["gate_failures"]
    good = await _run(monkeypatch, tmp_path, _pipeline(_diagram("10")), fail_on_warnings=[SUB])
    assert good["warnings"] == [] and good["gate_status"] == "pass"


async def test_end_to_end_field_label(monkeypatch, tmp_path):
    bad = await _run(monkeypatch, tmp_path, _pipeline(_diagram(length_label="7")), fail_on_warnings=[SUB])
    assert bad["gate_status"] == "fail" and f"warning:{SUB}" in bad["gate_failures"]
    good = await _run(monkeypatch, tmp_path, _pipeline(_diagram(length_label="10")), fail_on_warnings=[SUB])
    assert good["gate_status"] == "pass"


def _sc(**over):
    return [{"id": "sc1", "prompt": "p", **over}]


def test_validator_accepts_and_defaults():
    assert _validate_scenarios(_sc())[0]["fail_on_warnings"] == []
    assert _validate_scenarios(_sc(fail_on_warnings=[]))[0]["fail_on_warnings"] == []
    assert _validate_scenarios(_sc(fail_on_warnings=["a"]))[0]["fail_on_warnings"] == ["a"]


@pytest.mark.parametrize("bad", ["a", {"a": 1}, [""], [1], ["a", None]])
def test_validator_rejects_bad_values(bad):
    with pytest.raises(ValueError, match="sc1.*fail_on_warnings"):
        _validate_scenarios(_sc(fail_on_warnings=bad))


def test_solids_yaml_gates_dimension_scenarios():
    scs = {s["id"]: s for s in load_scenarios("evals/scenarios_solids.yaml")}
    gated = {i for i, s in scs.items() if s["fail_on_warnings"] == [SUB]}
    assert gated == {
        "prism-oblique-solid", "prism-oblique-solid-feet", "prism-oblique-wireframe-base-area",
        "prism-oblique-wireframe-base-area-feet", "prism-unit-cubes-isometric",
    }


def test_scenarios_without_key_still_load():
    scs = load_scenarios("evals/scenarios.yaml")
    assert scs and all(s["fail_on_warnings"] == [] for s in scs)

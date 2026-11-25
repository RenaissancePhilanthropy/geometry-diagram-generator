"""Scenario property arguments are checked at load: a degenerate or malformed one
(a repeated point, an angle named by a number) would fail every model, so it is an
error in the scenario file, not a verdict on the figure."""
from __future__ import annotations

import glob

import pytest

from evals import scenarios as sc

# Edit-chain and locality-judgment files use a different schema (no `prompt`).
_OTHER_SCHEMA = {"scenarios_editing_chains.yaml", "scenarios_locality_judgment.yaml"}
_FILES = sorted(f for f in glob.glob("evals/scenarios*.yaml") if f.split("/")[-1] not in _OTHER_SCHEMA)


def _load(ptype: str, args: list):
    return sc._validate_scenarios([{
        "id": "s", "prompt": "p", "expected_properties": [{"name": "n", "type": ptype, "args": args}],
    }])


@pytest.mark.parametrize("ptype,args", [
    ("right_angle", ["A", "O", "B"]), ("angle_value", ["A", "O", "B", 90]),
    ("angle_equal", [["A", "O", "B"], ["C", "P", "D"]]),
    ("equal_lengths", [["A", "B"], ["C", "D"]]), ("parallel", [["A", "B"], ["C", "D"]]),
    ("perpendicular", [["A", "B"], ["C", "D"]]), ("collinear", ["A", "B", "C"]),
    ("collinear", ["A", "B", "C", "D"]), ("midpoint", ["M", "A", "B"]),
])
def test_well_formed_arguments_load(ptype, args):
    _load(ptype, args)


@pytest.mark.parametrize("ptype,args", [
    ("right_angle", ["A", "A", "B"]),                       # a repeated point: no angle
    ("angle_value", ["A", "O", "A", 90]),
    ("angle_equal", [["A", "O", "B"]]),                     # one angle
    ("angle_equal", [["1", "2"], ["3", "2"]]),              # angles named by number, as pairs
    ("angle_equal", [["A", "O", "A"], ["C", "P", "D"]]),
    ("equal_lengths", [["A", "A"], ["C", "D"]]),            # a zero-length segment
    ("parallel", [["A", "B", "C"], ["D", "E"]]),             # a segment of three points
    ("perpendicular", [["R", "B"], ["M", "M"]]),
    ("collinear", ["C", "F", "C"]),                         # trivially true
    ("collinear", ["A", "B"]),
    ("midpoint", ["M", "A", "A"]),
    ("right_angle", ["A", 5, "B"]),                         # a number where a point belongs
])
def test_degenerate_or_malformed_arguments_are_rejected(ptype, args):
    with pytest.raises(ValueError, match="expected_properties\\[1\\]"):
        _load(ptype, args)


@pytest.mark.parametrize("path", _FILES)
def test_every_scenario_file_loads(path):
    assert sc.load_scenarios(path)


def test_the_two_other_schema_files_are_the_only_ones_excluded():
    assert {f.split("/")[-1] for f in glob.glob("evals/scenarios*.yaml")} - {f.split("/")[-1] for f in _FILES} == _OTHER_SCHEMA

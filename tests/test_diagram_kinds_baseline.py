"""Unit tests for the diagram-kinds-poc ticket 07 baseline runner's
non-LLM logic: manifest schema validation (manifest_lib.py) and the
generation-log + verdict combination logic (finalize_manifest.py). The 30
real PythonFullStrategy.run() calls are the integration run itself (see
.scratch/diagram-kinds-poc/baseline/run_baseline.py and its manifest.json
output) and are intentionally not exercised here.

These modules live under .scratch/diagram-kinds-poc/baseline/ (PoC
artifacts, not part of the geometry_diagrams package), so this test file
loads them directly by file path rather than via a normal package import.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BASELINE_DIR = (
    Path(__file__).resolve().parents[1]
    / ".scratch" / "diagram-kinds-poc" / "baseline"
)


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, BASELINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def kinds_prompts():
    return _load_module("kinds_prompts")


@pytest.fixture(scope="module")
def manifest_lib():
    return _load_module("manifest_lib")


@pytest.fixture(scope="module")
def finalize_manifest(manifest_lib, kinds_prompts):
    # finalize_manifest.py imports manifest_lib/kinds_prompts by inserting
    # BASELINE_DIR onto sys.path itself -- already satisfied since
    # _load_module below runs after the two fixtures above have executed.
    return _load_module("finalize_manifest")


# ---------------------------------------------------------------------------
# kinds_prompts.py
# ---------------------------------------------------------------------------

def test_thirty_kinds_declared(kinds_prompts):
    assert len(kinds_prompts.KIND_PROMPTS) == 30
    assert len(kinds_prompts.KIND_NAMES) == 30
    assert len(set(kinds_prompts.KIND_NAMES)) == 30


def test_none_kind_has_no_prompt(kinds_prompts):
    prompts_by_kind = dict(kinds_prompts.KIND_PROMPTS)
    assert prompts_by_kind["none"] is None


def test_every_other_kind_has_a_nonempty_prompt(kinds_prompts):
    for kind, prompt in kinds_prompts.KIND_PROMPTS:
        if kind == "none":
            continue
        assert isinstance(prompt, str) and prompt.strip(), f"{kind} has no usable prompt"


# ---------------------------------------------------------------------------
# manifest_lib.py
# ---------------------------------------------------------------------------

def test_manifest_entry_pass_requires_svg_path(manifest_lib):
    with pytest.raises(ValueError, match="no svg_path"):
        manifest_lib.ManifestEntry(kind="grid_area", verdict="pass", svg_path=None)


def test_manifest_entry_partial_requires_svg_path(manifest_lib):
    with pytest.raises(ValueError, match="no svg_path"):
        manifest_lib.ManifestEntry(kind="grid_area", verdict="partial", svg_path="")


def test_manifest_entry_fail_forbids_svg_path(manifest_lib):
    with pytest.raises(ValueError, match="'fail'"):
        manifest_lib.ManifestEntry(kind="grid_area", verdict="fail", svg_path="svgs/grid_area.svg")


def test_manifest_entry_rejects_unknown_verdict(manifest_lib):
    with pytest.raises(ValueError, match="invalid verdict"):
        manifest_lib.ManifestEntry(kind="grid_area", verdict="great")


def test_manifest_entry_valid_shapes_construct_cleanly(manifest_lib):
    manifest_lib.ManifestEntry(kind="grid_area", verdict="pass", svg_path="svgs/grid_area.svg")
    manifest_lib.ManifestEntry(kind="scatter_plot", verdict="partial", svg_path="svgs/scatter_plot.svg", notes="axes unlabeled")
    manifest_lib.ManifestEntry(kind="none", verdict="fail", svg_path=None)


def test_write_and_read_manifest_round_trips(tmp_path, manifest_lib):
    entries = [
        manifest_lib.ManifestEntry(kind="grid_area", verdict="pass", svg_path="svgs/grid_area.svg", notes="clean"),
        manifest_lib.ManifestEntry(kind="none", verdict="pass", svg_path=None, notes="not a rendering kind"),
    ]
    path = tmp_path / "manifest.json"
    manifest_lib.write_manifest(entries, path)
    loaded = manifest_lib.read_manifest(path)
    assert loaded == entries


def test_write_manifest_rejects_duplicate_kinds(tmp_path, manifest_lib):
    entries = [
        manifest_lib.ManifestEntry(kind="grid_area", verdict="fail"),
        manifest_lib.ManifestEntry(kind="grid_area", verdict="fail"),
    ]
    with pytest.raises(ValueError, match="duplicate"):
        manifest_lib.write_manifest(entries, tmp_path / "manifest.json")


def test_write_manifest_enforces_expected_kind_coverage(tmp_path, manifest_lib):
    entries = [manifest_lib.ManifestEntry(kind="grid_area", verdict="fail")]
    with pytest.raises(ValueError, match="missing"):
        manifest_lib.write_manifest(
            entries, tmp_path / "manifest.json", expected_kinds=["grid_area", "tape_diagram"],
        )


def test_write_manifest_accepts_exact_expected_coverage(tmp_path, manifest_lib):
    entries = [
        manifest_lib.ManifestEntry(kind="grid_area", verdict="fail"),
        manifest_lib.ManifestEntry(kind="tape_diagram", verdict="fail"),
    ]
    manifest_lib.write_manifest(
        entries, tmp_path / "manifest.json", expected_kinds=["grid_area", "tape_diagram"],
    )
    assert json.loads((tmp_path / "manifest.json").read_text())


# ---------------------------------------------------------------------------
# finalize_manifest.py
# ---------------------------------------------------------------------------

def test_build_entries_pulls_svg_path_from_generation_log(finalize_manifest):
    generation_log = [
        {"kind": "grid_area", "ok": True, "svg_path": "svgs/grid_area.svg"},
        {"kind": "none", "ok": None, "svg_path": None},
    ]
    verdicts = {kind: ("fail", "not reviewed") for kind, _ in finalize_manifest.KIND_PROMPTS}
    verdicts["grid_area"] = ("pass", "looks right")
    verdicts["none"] = ("pass", "not a rendering kind")

    entries = finalize_manifest.build_entries(generation_log, verdicts)

    by_kind = {e.kind: e for e in entries}
    assert by_kind["grid_area"].svg_path == "svgs/grid_area.svg"
    assert by_kind["grid_area"].verdict == "pass"
    assert by_kind["none"].svg_path is None
    assert by_kind["none"].verdict == "pass"
    assert len(entries) == 30


def test_build_entries_raises_if_pass_has_no_logged_svg(finalize_manifest):
    generation_log = [{"kind": "grid_area", "ok": False, "svg_path": None}]
    verdicts = {kind: ("fail", "") for kind, _ in finalize_manifest.KIND_PROMPTS}
    verdicts["grid_area"] = ("pass", "should have failed generation")

    with pytest.raises(ValueError, match="no svg_path"):
        finalize_manifest.build_entries(generation_log, verdicts)


def test_build_entries_raises_if_verdicts_missing_a_kind(finalize_manifest):
    verdicts = {kind: ("fail", "") for kind, _ in finalize_manifest.KIND_PROMPTS if kind != "grid_area"}
    with pytest.raises(KeyError):
        finalize_manifest.build_entries([], verdicts)

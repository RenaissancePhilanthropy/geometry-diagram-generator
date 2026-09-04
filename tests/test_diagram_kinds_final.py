"""Unit tests for the diagram-kinds gallery's final-assembly non-LLM logic:
manifest schema validation (diagram_kinds_manifest_lib.py) and the
baseline + fresh-choices combination logic
(assemble_diagram_kinds_manifest.py). The real fresh PythonFullStrategy.run()
attempts (area_model, attribute_chart, coordinate_plane, scatter_plot,
shape_comparison, plus round-2's work_table and l_prism) are the integration
work itself (see docs/gen_diagram_kinds_examples.py, docs/diagram_kinds_prompts.py,
and docs/examples/diagram_kinds/generation_log.json/manifest.json) and are
intentionally not exercised here -- mirrors
tests/test_diagram_kinds_baseline.py's precedent.

The assembly scripts live under docs/ (permanent, following the
docs/gen_examples.py pattern) but still read the original baseline
manifest from .scratch/diagram-kinds-poc/baseline/ (diagram-kinds-poc's
disposable working area, left in place independently of this move), so
this test file loads them directly by file path rather than via a normal
package import.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
BASELINE_DIR = (
    Path(__file__).resolve().parents[1]
    / ".scratch" / "diagram-kinds-poc" / "baseline"
)


def _load_module(name: str, directory: Path):
    spec = importlib.util.spec_from_file_location(name, directory / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def kinds_prompts():
    return _load_module("kinds_prompts", BASELINE_DIR)


@pytest.fixture(scope="module")
def final_manifest_lib():
    return _load_module("diagram_kinds_manifest_lib", DOCS_DIR)


@pytest.fixture(scope="module")
def assemble_manifest(final_manifest_lib, kinds_prompts):
    # assemble_diagram_kinds_manifest.py imports kinds_prompts/
    # diagram_kinds_manifest_lib by inserting both directories onto
    # sys.path itself -- already satisfied since _load_module above runs
    # after the two fixtures above have executed.
    return _load_module("assemble_diagram_kinds_manifest", DOCS_DIR)


# ---------------------------------------------------------------------------
# final_manifest_lib.py
# ---------------------------------------------------------------------------

def test_ok_entry_requires_svg_path(final_manifest_lib):
    with pytest.raises(ValueError, match="no svg_path"):
        final_manifest_lib.FinalManifestEntry(
            kind="grid_area", svg_path=None, source="baseline-reuse", status="ok",
        )


def test_none_kind_ok_entry_may_omit_svg_path(final_manifest_lib):
    entry = final_manifest_lib.FinalManifestEntry(
        kind="none", svg_path=None, source="baseline-reuse", status="ok", notes="not a rendering kind",
    )
    assert entry.svg_path is None


def test_known_gap_requires_notes(final_manifest_lib):
    with pytest.raises(ValueError, match="known-gap"):
        final_manifest_lib.FinalManifestEntry(
            kind="scatter_plot", svg_path=None, source="fresh-generation", status="known-gap", notes="",
        )


def test_known_gap_may_omit_svg_path(final_manifest_lib):
    entry = final_manifest_lib.FinalManifestEntry(
        kind="scatter_plot", svg_path=None, source="fresh-generation",
        status="known-gap", notes="tried 3 prompt iterations, canvas aspect ratio still broken",
    )
    assert entry.svg_path is None


def test_rejects_unknown_source(final_manifest_lib):
    with pytest.raises(ValueError, match="invalid source"):
        final_manifest_lib.FinalManifestEntry(
            kind="grid_area", svg_path="svgs/grid_area.svg", source="hand-authored", status="ok",
        )


def test_rejects_unknown_status(final_manifest_lib):
    with pytest.raises(ValueError, match="invalid status"):
        final_manifest_lib.FinalManifestEntry(
            kind="grid_area", svg_path="svgs/grid_area.svg", source="baseline-reuse", status="great",
        )


def test_write_and_read_manifest_round_trips(tmp_path, final_manifest_lib):
    entries = [
        final_manifest_lib.FinalManifestEntry(
            kind="grid_area", svg_path="svgs/grid_area.svg", source="baseline-reuse", status="ok", notes="clean",
        ),
        final_manifest_lib.FinalManifestEntry(
            kind="none", svg_path=None, source="baseline-reuse", status="ok", notes="not a rendering kind",
        ),
    ]
    path = tmp_path / "manifest.json"
    final_manifest_lib.write_manifest(entries, path)
    loaded = final_manifest_lib.read_manifest(path)
    assert loaded == entries


def test_write_and_read_manifest_round_trips_script_path(tmp_path, final_manifest_lib):
    entries = [
        final_manifest_lib.FinalManifestEntry(
            kind="work_table", svg_path="svgs/work_table.svg", source="fresh-generation",
            status="ok", notes="uniform rows", script_path="scripts/work_table.py",
        ),
    ]
    path = tmp_path / "manifest.json"
    final_manifest_lib.write_manifest(entries, path)
    loaded = final_manifest_lib.read_manifest(path)
    assert loaded == entries
    assert loaded[0].script_path == "scripts/work_table.py"


def test_finalmanifestentry_script_path_defaults_to_none(final_manifest_lib):
    entry = final_manifest_lib.FinalManifestEntry(
        kind="grid_area", svg_path="svgs/grid_area.svg", source="baseline-reuse", status="ok",
    )
    assert entry.script_path is None


def test_write_manifest_rejects_duplicate_kinds(tmp_path, final_manifest_lib):
    entries = [
        final_manifest_lib.FinalManifestEntry(kind="grid_area", svg_path=None, source="baseline-reuse", status="known-gap", notes="x"),
        final_manifest_lib.FinalManifestEntry(kind="grid_area", svg_path=None, source="baseline-reuse", status="known-gap", notes="x"),
    ]
    with pytest.raises(ValueError, match="duplicate"):
        final_manifest_lib.write_manifest(entries, tmp_path / "manifest.json")


def test_write_manifest_enforces_expected_kind_coverage(tmp_path, final_manifest_lib):
    entries = [
        final_manifest_lib.FinalManifestEntry(kind="grid_area", svg_path=None, source="baseline-reuse", status="known-gap", notes="x"),
    ]
    with pytest.raises(ValueError, match="missing"):
        final_manifest_lib.write_manifest(
            entries, tmp_path / "manifest.json", expected_kinds=["grid_area", "tape_diagram"],
        )


# ---------------------------------------------------------------------------
# assemble_manifest.py
# ---------------------------------------------------------------------------

def _baseline_row(kind: str, verdict: str, svg_path=None, notes: str = "") -> dict:
    return {"kind": kind, "verdict": verdict, "svg_path": svg_path, "notes": notes}


def test_build_final_entries_reuses_baseline_pass_kinds(assemble_manifest):
    baseline_manifest = [
        _baseline_row("grid_area", "pass", "svgs/grid_area.svg", "clean"),
        _baseline_row("none", "pass", None, "not a rendering kind"),
    ]
    entries = assemble_manifest.build_final_entries(baseline_manifest, fresh_choices={})
    by_kind = {e.kind: e for e in entries}
    assert by_kind["grid_area"].source == "baseline-reuse"
    assert by_kind["grid_area"].status == "ok"
    assert by_kind["grid_area"].svg_path == "svgs/grid_area.svg"
    assert by_kind["none"].svg_path is None


def test_build_final_entries_uses_fresh_choice_for_ok_override(assemble_manifest):
    baseline_manifest = [_baseline_row("area_model", "partial", "svgs/area_model.svg", "baseline defect")]
    fresh_choices = {
        "area_model": {
            "status": "ok",
            "attempt_svg": "attempts/area_model_attempt0.svg",
            "notes": "fixed via cookbook helper",
        },
    }
    entries = assemble_manifest.build_final_entries(baseline_manifest, fresh_choices)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source == "fresh-generation"
    assert entry.status == "ok"
    assert entry.svg_path == "attempts/area_model_attempt0.svg"
    assert entry.notes == "fixed via cookbook helper"


def test_build_final_entries_uses_fresh_choice_for_known_gap(assemble_manifest):
    baseline_manifest = [_baseline_row("scatter_plot", "partial", "svgs/scatter_plot.svg", "baseline defect")]
    fresh_choices = {
        "scatter_plot": {
            "status": "known-gap",
            "notes": "3 attempts tried, still clipped",
        },
    }
    entries = assemble_manifest.build_final_entries(baseline_manifest, fresh_choices)
    entry = entries[0]
    assert entry.source == "fresh-generation"
    assert entry.status == "known-gap"
    assert entry.svg_path is None
    assert entry.notes == "3 attempts tried, still clipped"


def test_build_final_entries_raises_on_unaccounted_non_passing_kind(assemble_manifest):
    baseline_manifest = [_baseline_row("shape_comparison", "partial", "svgs/shape_comparison.svg", "defect")]
    with pytest.raises(ValueError, match="fresh_choices"):
        assemble_manifest.build_final_entries(baseline_manifest, fresh_choices={})


def test_build_final_entries_covers_all_30_real_kinds(assemble_manifest, kinds_prompts):
    """Sanity check against the real baseline manifest + this ticket's
    real FRESH_CHOICES -- catches drift if a future edit adds/removes a
    kind on either side without updating the other."""
    import json

    baseline_manifest = json.loads((BASELINE_DIR / "manifest.json").read_text())
    entries = assemble_manifest.build_final_entries(baseline_manifest, assemble_manifest.FRESH_CHOICES)
    assert {e.kind for e in entries} == set(kinds_prompts.KIND_NAMES)
    assert len(entries) == 30


def test_real_fresh_choices_cover_exactly_the_flagged_kinds(assemble_manifest):
    assert set(assemble_manifest.FRESH_CHOICES.keys()) == {
        "area_model", "attribute_chart", "coordinate_plane", "scatter_plot", "shape_comparison",
        "work_table", "l_prism",
    }


def test_build_final_entries_threads_script_path_from_fresh_choice(assemble_manifest):
    baseline_manifest = [_baseline_row("work_table", "pass", "svgs/work_table.svg", "clean")]
    fresh_choices = {
        "work_table": {
            "status": "ok",
            "attempt_svg": "attempts/work_table_attempt0.svg",
            "attempt_script": "attempt_scripts/work_table_attempt0.py",
            "notes": "uniform row heights via table_grid()",
        },
    }
    entries = assemble_manifest.build_final_entries(baseline_manifest, fresh_choices)
    assert entries[0].script_path == "attempt_scripts/work_table_attempt0.py"


def test_build_final_entries_omits_script_path_when_not_given(assemble_manifest):
    baseline_manifest = [_baseline_row("grid_area", "pass", "svgs/grid_area.svg", "clean")]
    entries = assemble_manifest.build_final_entries(baseline_manifest, fresh_choices={})
    assert entries[0].script_path is None

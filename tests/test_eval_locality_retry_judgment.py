"""Tests for evals/eval_locality_retry_judgment.py's own scoring logic —
mocks what "the real model" returns for the retry call, so these never hit
a live API. The point is to validate that run_fixture correctly detects
the retry call and scores pass/fail correctly in all four quadrants
(illegitimate fixed/not-fixed, legitimate preserved/wrongly-restored),
not to validate any actual model's judgment."""
from __future__ import annotations

import pytest

from evals.eval_locality_retry_judgment import _load_fixtures, run_fixture, summarize
from geometry_diagrams.strategies import python_full as pf_module

_PRIOR_SCRIPT = "a = point(0, 0)\nb = point(1, 0)\ndraw_points(a, b)\n"
_DROPPED_B_SCRIPT = "a = point(0, 0)\ndraw_points(a)\n"


def _illegitimate_fixture():
    return {
        "id": "test-illegitimate",
        "category": "illegitimate",
        "request": "move a",
        "prior_script": _PRIOR_SCRIPT,
        "edited_script": _DROPPED_B_SCRIPT,
        "expect_still_unmatched": [],
    }


def _legitimate_fixture():
    return {
        "id": "test-legitimate",
        "category": "legitimate",
        "request": "remove b",
        "prior_script": _PRIOR_SCRIPT,
        "edited_script": _DROPPED_B_SCRIPT,
        "expect_still_unmatched": ["b"],
    }


@pytest.mark.asyncio
async def test_illegitimate_fixture_passes_when_retry_restores_the_dropped_entity(monkeypatch):
    async def fake_real_model(prompt, model, enable_cache=False):
        # _edit_search_replace always applies against top["script"] — the
        # turn-1 BASELINE (_PRIOR_SCRIPT), not the corrupted first attempt's
        # output — so "correctly fixes it" means a no-op from that
        # baseline: recognize the drop was accidental, leave b alone.
        return [{"old_string": _PRIOR_SCRIPT, "new_string": _PRIOR_SCRIPT}], 0, 0, None

    monkeypatch.setattr(pf_module, "generate_search_replace", fake_real_model)

    result = await run_fixture(_illegitimate_fixture(), "test-model")

    assert result["error"] is None
    assert result["locality_retry_fired"] is True
    assert result["passed"] is True


@pytest.mark.asyncio
async def test_illegitimate_fixture_fails_when_retry_does_not_restore(monkeypatch):
    async def fake_real_model(prompt, model, enable_cache=False):
        # Reproduces the same corruption again from the baseline — a real
        # model failing to recognize/fix genuine corruption.
        return [{"old_string": _PRIOR_SCRIPT, "new_string": _DROPPED_B_SCRIPT}], 0, 0, None

    monkeypatch.setattr(pf_module, "generate_search_replace", fake_real_model)

    result = await run_fixture(_illegitimate_fixture(), "test-model")

    assert result["passed"] is False
    assert result["actual_still_unmatched"] == ["b"]


@pytest.mark.asyncio
async def test_legitimate_fixture_passes_when_retry_preserves_the_deletion(monkeypatch):
    async def fake_real_model(prompt, model, enable_cache=False):
        # Correctly recognizes the deletion was intentional and reproduces
        # it again from the baseline.
        return [{"old_string": _PRIOR_SCRIPT, "new_string": _DROPPED_B_SCRIPT}], 0, 0, None

    monkeypatch.setattr(pf_module, "generate_search_replace", fake_real_model)

    result = await run_fixture(_legitimate_fixture(), "test-model")

    assert result["passed"] is True
    assert result["actual_still_unmatched"] == ["b"]


@pytest.mark.asyncio
async def test_legitimate_fixture_fails_when_retry_wrongly_restores_a_real_deletion(monkeypatch):
    async def fake_real_model(prompt, model, enable_cache=False):
        # Incorrectly "fixes" a legitimate deletion by resubmitting the
        # baseline unchanged (b comes back) — exactly the false-positive
        # risk this eval exists to catch.
        return [{"old_string": _PRIOR_SCRIPT, "new_string": _PRIOR_SCRIPT}], 0, 0, None

    monkeypatch.setattr(pf_module, "generate_search_replace", fake_real_model)

    result = await run_fixture(_legitimate_fixture(), "test-model")

    assert result["passed"] is False
    assert result["actual_still_unmatched"] == []


@pytest.mark.asyncio
async def test_run_fixture_reports_error_when_prior_script_is_invalid():
    fixture = _illegitimate_fixture()
    fixture["prior_script"] = "this is not valid pydsl :::"

    result = await run_fixture(fixture, "test-model")

    assert result["passed"] is None
    assert "prior_script failed to execute" in result["error"]


@pytest.mark.asyncio
async def test_run_fixture_restores_generate_search_replace_even_on_failure(monkeypatch):
    """The monkeypatch-swap-restore in run_fixture uses try/finally — confirm
    a prior_script failure (which returns early, before the swap) still
    leaves the module's real generate_search_replace untouched, and that a
    successful run restores it too (no leaked patch across fixtures)."""
    original = pf_module.generate_search_replace

    fixture = _illegitimate_fixture()
    fixture["prior_script"] = "this is not valid pydsl :::"
    await run_fixture(fixture, "test-model")
    assert pf_module.generate_search_replace is original

    async def fake_real_model(prompt, model, enable_cache=False):
        return [{"old_string": _PRIOR_SCRIPT, "new_string": _PRIOR_SCRIPT}], 0, 0, None

    monkeypatch.setattr(pf_module, "generate_search_replace", fake_real_model)
    await run_fixture(_illegitimate_fixture(), "test-model")
    assert pf_module.generate_search_replace is fake_real_model  # monkeypatch's own restore happens after the test


def test_load_fixtures_rejects_unknown_category(tmp_path):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        "- id: x\n"
        "  category: sideways\n"
        "  request: r\n"
        "  prior_script: p\n"
        "  edited_script: e\n"
        "  expect_still_unmatched: []\n"
    )
    with pytest.raises(ValueError, match="category must be"):
        _load_fixtures(str(bad_yaml))


def test_summarize_computes_per_category_pass_and_error_counts():
    results = [
        {"category": "illegitimate", "passed": True},
        {"category": "illegitimate", "passed": False},
        {"category": "illegitimate", "passed": None},
        {"category": "legitimate", "passed": True},
        {"category": "legitimate", "passed": True},
    ]
    summary = summarize(results)
    assert summary["illegitimate"] == {"total": 3, "passed": 1, "errored": 1}
    assert summary["legitimate"] == {"total": 2, "passed": 2, "errored": 0}


def test_the_real_fixture_bank_loads_and_has_both_categories():
    fixtures = _load_fixtures("evals/scenarios_locality_judgment.yaml")
    categories = {f["category"] for f in fixtures}
    assert categories == {"illegitimate", "legitimate"}
    assert len(fixtures) >= 4
    for fx in fixtures:
        assert fx["prior_script"].strip()
        assert fx["edited_script"].strip()
        assert fx["request"].strip()

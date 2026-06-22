"""Unit tests for the deterministic CoT confidence analyzer (`util.cot_analyzer`).

These cover the lexicon counting and the flipped confidence rubric
(struggle / self-caught contradictions LOWER confidence). The analyzer is
pure text — no LLM, no ground truth — so the tests are deterministic and fast.
"""
from __future__ import annotations

from util.cot_analyzer import analyze_cot


# ---------------------------------------------------------------------------
# Empty / no-CoT
# ---------------------------------------------------------------------------

def test_no_cot_returns_none_score():
    out = analyze_cot(None)
    assert out["score"] is None
    assert out["signals"] == {}
    assert out["reasoning"] == "(no CoT)"


def test_empty_cot_returns_none_score():
    assert analyze_cot("").get("score") is None
    assert analyze_cot("   ").get("score") is None


# ---------------------------------------------------------------------------
# Lexicon counting (controlled snippets)
# ---------------------------------------------------------------------------

def test_contradiction_counted():
    """A self-caught contradiction is the highest-value low-confidence signal,
    but its IMPACT depends on position (see test_*_late/early below). The raw
    count is always reported."""
    out = analyze_cot("triangle ABC is not equilateral!")
    sig = out["signals"]
    assert sig["contradictions"] == 1
    assert sig["hedging"] == 0
    assert sig["self_corrections"] == 0


def test_early_contradiction_is_benign():
    """A single contradiction EARLY in the CoT (resolved before the answer) is
    benign exploration — half-weighted, so it must NOT drop a clean CoT."""
    clean_tail = ("Construct triangle ABC. Place the midpoint M of side AB. "
                  "Draw segment CM. Label all points. " * 4)
    early = "oh, not equilateral. " + clean_tail
    # contradiction is at the very start; the long clean tail makes its relative
    # position early, so late_contradictions is 0 and it is half-weighted
    out = analyze_cot(early)
    assert out["signals"]["contradictions"] == 1
    assert out["signals"]["late_contradictions"] == 0
    assert out["score"] == 5


def test_late_contradiction_lowers_score():
    """A contradiction in the LAST THIRD (caught near/after the answer) is the
    real low-confidence signal — full weight -> score 3."""
    clean_prefix = "Construct triangle ABC. Place midpoint M of AB. Draw segment CM. Label all points. "
    late = clean_prefix * 4 + "It doesn't work."
    out = analyze_cot(late)
    assert out["signals"]["contradictions"] == 1
    assert out["signals"]["late_contradictions"] == 1
    assert out["score"] == 3


def test_hedging_counted():
    out = analyze_cot("Maybe I think perhaps")
    assert out["signals"]["hedging"] == 3


def test_self_correction_counted():
    out = analyze_cot("Wait, actually, hmm")
    assert out["signals"]["self_corrections"] == 3


def test_struggle_counted():
    out = analyze_cot("let me try this, let me try that")
    # bare "let me try" matches twice
    assert out["signals"]["struggle"] >= 2


def test_giveup_counted():
    out = analyze_cot("just use it, let's just go, for now")
    assert out["signals"]["giveup"] == 3


# ---------------------------------------------------------------------------
# Rubric: clean vs flailing
# ---------------------------------------------------------------------------

def test_clean_cot_scores_five():
    clean = (
        "Construct triangle ABC with the given side lengths. "
        "Place the midpoint M of side AB. Draw segment CM. "
        "Label all vertices and the midpoint. The diagram is complete."
    )
    out = analyze_cot(clean)
    assert out["score"] == 5
    sig = out["signals"]
    assert sig["contradictions"] == 0
    assert sig["self_corrections"] == 0


def test_heavy_contradictions_score_one():
    # 8+ self-caught contradictions -> score 1
    flailing = "It doesn't work. " * 10 + "that's wrong, off by a lot, fails."
    out = analyze_cot(flailing)
    assert out["signals"]["contradictions"] >= 8
    assert out["score"] == 1


def test_flailing_self_corrections_score_one():
    # 50+ self-correction markers -> score 1
    flailing = "Wait, actually. " * 30
    out = analyze_cot(flailing)
    assert out["signals"]["self_corrections"] >= 50
    assert out["score"] == 1


def test_moderate_self_corrections_score_two():
    # 22-49 self-corrections -> score 2
    cot = "Wait, actually. " * 25  # 50 self-corrections -> would be score 1
    # use a count in the score-2 band instead
    cot2 = "Wait. " * 25  # 25 self-corrections
    out = analyze_cot(cot2)
    assert out["signals"]["self_corrections"] == 25
    assert out["score"] == 2


def test_light_hedging_scores_four():
    # 4 hedges, nothing else -> score 4 (h >= 4, but below score-3 bars)
    out = analyze_cot("maybe maybe maybe maybe")
    assert out["signals"]["hedging"] == 4
    assert out["score"] == 4


def test_giveup_scores_four():
    out = analyze_cot("just use just use")
    assert out["signals"]["giveup"] == 2
    assert out["score"] == 4


# ---------------------------------------------------------------------------
# Approach-switching (terse-and-verbose-agnostic flailing signal)
# ---------------------------------------------------------------------------

def test_approach_switch_counted():
    out = analyze_cot("Alternatively, instead, another way, different approach")
    assert out["signals"]["approach_switches"] == 4


def test_heavy_approach_switching_scores_two():
    # 3+ approach switches -> score 2 (validated: catches verbose-model fails
    # that otherwise score 3, without touching clean passes).
    out = analyze_cot("Alternatively. Instead. Another way.")
    assert out["signals"]["approach_switches"] == 3
    assert out["score"] == 2


def test_two_approach_switches_not_flagged():
    # a>=2 was retracted — two switches are non-informative (easy-scenario
    # passes weigh one alternative too) and must NOT lower a clean CoT.
    out = analyze_cot("Alternatively. Instead.")
    assert out["signals"]["approach_switches"] == 2
    assert out["score"] == 5


def test_single_approach_switch_not_flagged():
    # a single "instead" is normal planning, must NOT lower a clean CoT below 5
    out = analyze_cot("Use abstract mode instead of grid mode.")
    assert out["signals"]["approach_switches"] == 1
    assert out["score"] == 5


# ---------------------------------------------------------------------------
# Drop-in compatibility
# ---------------------------------------------------------------------------

def test_extra_kwargs_ignored():
    """prompt/dsl_json/model/enable_cache are accepted and do not change the
    result — the analyzer is text-only."""
    cot = "maybe maybe maybe maybe"
    base = analyze_cot(cot)
    with_kwargs = analyze_cot(
        cot,
        prompt="Draw a square.",
        dsl_json={"mode": "abstract"},
        model="ollama:gemma4",
        enable_cache=True,
    )
    assert base == with_kwargs


def test_signals_keys_present():
    out = analyze_cot("maybe wait doesn't work let me try just use")
    assert set(out["signals"]) == {
        "hedging", "self_corrections", "contradictions", "late_contradictions",
        "struggle", "giveup", "approach_switches", "marker_density", "cot_len",
    }
    assert out["signals"]["cot_len"] == len("maybe wait doesn't work let me try just use")


def test_marker_density_per_kchar():
    text = "maybe " * 200
    out = analyze_cot(text)
    h = out["signals"]["hedging"]
    expected = round(h / (len(text) / 1000), 2)
    assert out["signals"]["marker_density"] == expected
    assert h == 200


def test_reasoning_string_describes_markers():
    out = analyze_cot("maybe wait doesn't work")
    reasoning = out["reasoning"]
    assert "contradictions" in reasoning or "self-corrections" in reasoning or "hedges" in reasoning
"""Deterministic CoT confidence analyzer.

Replaces the LLM CoT judge (`util.llm_judge.analyze_cot_llm`) as the default
`analyze_cot`. Motivation: the LLM judge undercounts uncertainty markers in
long CoTs by 10-15x (it reported `hedging=0` on CoTs containing 30-43 hedging
phrases) and its rubric treats self-correction/verification as trust-raising,
so it returned a near-constant confidence=5 regardless of whether the output
was correct — useless as a "this came with low confidence" flag.

This analyzer is pure text analysis (no LLM call, no judge model, no ground
truth, no gate) — so it works in production where there are no verification
checks. It counts uncertainty markers across broadened lexicons and FLIPS the
rubric: struggle, especially self-caught contradictions, LOWERS confidence.

The signal is model- AND difficulty-dependent. On a curated HARD scenario
subset it separates well for verbose, self-correcting models (deepseek pass
4.27 vs fail 2.28). It does NOT generalize to terse-confident models or to the
full 201-scenario curriculum: deepseek collapses to pass 2.98 vs fail 2.59
(~64% of passes false-low) and gemma4 INVERTS (fail > pass). glm-5.2, used as
an OUT-OF-SAMPLE validation (never tuned on), inverts hardest — fail mean
4.67 > pass 4.00 on one set with 0% of fails flagged — because its failures
are terse, clean, plan-style CoTs (370-1900 chars, ~0 markers) failing on
mark/checker gates, with no uncertainty language to detect.

No single CoT feature separates across all models: the failure modes are
stylistically opposite. deepseek fails by verbose flailing (fails have LONGER
CoTs, 14k vs 4k) which markers catch; gemma4/glm-5.2 fail by terse confidence
(fails SHORTER, ~0 markers) which nothing in the text catches. CoT LENGTH was
tested as a model-agnostic signal and rejected — it points in opposite
directions per model, so using it would help glm-5.2 but break deepseek (whose
short low-marker CoTs are clean passes). It is a hard-subset, verbose-model
signal. Do not rely on it as a production confidence flag across a general
model/scenario mix; for terse-confident-wrong and silently-wrong CoTs the code
judge / deterministic geometric checks remain necessary.

Drop-in compatible with the old call sites: accepts and ignores `prompt`,
`dsl_json`, `model`, `enable_cache` (only `cot` is used). Synchronous.
"""
from __future__ import annotations

import re

# ---- Lexicons (broadened from the LLM judge's narrow 4-phrase set) ----
# Hedging: epistemic uncertainty about the answer / approach.
_HEDGING = re.compile(
    r"\b(maybe|i think|i believe|perhaps|possibly|probably|likely|might|"
    r"could be|seems|appears|assume|assuming|guess(?:ing)?|roughly|"
    r"approximate(?:ly)?|around|should be|hopefully|let'?s hope|"
    r"not sure|uncertain|unsure|i'?m not sure)\b",
    re.I,
)
# Self-correction: backtracking / revising a prior choice.
_SELF_CORRECTION = re.compile(
    r"\b(wait|actually|hmm|oops|mistake|wrong|redo|reconsider|hold on|"
    r"let me (?:fix|redo|reconsider|try again|re-?read)|"
    r"that'?s not right|correction|scratch that|never mind|no,|"
    r"let me reconsider|let me re-?read)\b",
    re.I,
)
# Contradiction: the model catches its OWN error or debugs a prior failure.
# The highest-value low-confidence signal — the model knew something was wrong.
_CONTRADICTION = re.compile(
    r"\b(doesn'?t (?:work|match|look right)|not (?:equilateral|"
    r"a right|going to work)|that'?s wrong|off by|"
    r"inconsisten\w*|contradict\w*|fails|failed|"
    r"the (?:issue|problem) is|not quite|won'?t work|can'?t be|"
    r"impossible|violates|so that doesn'?t work|"
    r"not a (?:right|equilateral)|previous attempt (?:failed|didn'?t))\b",
    re.I,
)
# Struggle: uncertainty about HOW to do it in the DSL / approximating / faking.
_STRUGGLE = re.compile(
    r"\b(not sure how|i don'?t know|let me try|trial|experiment|"
    r"see if this works|hope(?:fully)? this works|simplif\w*|"
    r"fake|pretend|workaround|hack|fudge|stand-?in|placeholder|dummy|"
    r"best effort|good enough|close enough|approximation|"
    r"let me think about how|getting complex|this is getting|"
    r"let me try (?:a |another |yet another |completely different )|"
    r"let me (?:simplify|reconsider))\b",
    re.I,
)
# Give-up: noticing a problem and shipping something anyway.
_GIVEUP = re.compile(
    r"\b(just (?:use|go with|pick|draw)|let'?s just|good enough|"
    r"this might be (?:a |an )?(?:simplification|error)|"
    r"i'?ll (?:just|go with)|for now)\b",
    re.I,
)
# Approach-switching: reconsidering / restarting the whole approach mid-CoT.
# Distinct from a single self-correction — this is the model abandoning one
# strategy for another ("alternatively", "instead", "another way", "start
# over"). Verbose models (deepseek) show this heavily on hard-scenario
# failures. Only a >= 3 fires in the rubric: a>=2 was retracted after the
# 201-scenario curriculum eval showed it flags easy-scenario passes (where the
# model harmlessly weighs one alternative) and worsens calibration without
# adding fail separation.
_APPROACH_SWITCH = re.compile(
    r"\b(alternatively|instead|another (?:way|approach)|"
    r"let'?s try (?:a |another |different )|different approach|"
    r"start over|restart|scrap|redo this)\b",
    re.I,
)


def _count(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text))


def analyze_cot(
    cot: str | None = None,
    *,
    prompt: str | None = None,
    dsl_json: dict | None = None,
    model: str | None = None,
    enable_cache: bool = False,
) -> dict:
    """Score a chain-of-thought for confidence (1-5), from text alone.

    Only `cot` is used; the other kwargs are accepted for drop-in
    compatibility with the old LLM `analyze_cot` call sites and ignored.

    Returns ``{"score", "reasoning", "signals"}`` where:
      - score: 1 (low confidence / flailing) .. 5 (clean, confident)
      - reasoning: short human-readable justification
      - signals: {hedging, self_corrections, contradictions,
                  late_contradictions, struggle, giveup, approach_switches,
                  marker_density, cot_len}
    """
    # Unused kwargs kept for call-site compatibility.
    _ = prompt, dsl_json, model, enable_cache

    if not cot or not cot.strip():
        return {"score": None, "reasoning": "(no CoT)", "signals": {}}

    length = max(len(cot), 1)
    h = _count(_HEDGING, cot)
    s = _count(_SELF_CORRECTION, cot)
    c = _count(_CONTRADICTION, cot)
    t = _count(_STRUGGLE, cot)
    g = _count(_GIVEUP, cot)
    a = _count(_APPROACH_SWITCH, cot)
    # Position-aware contradictions: a backtrack EARLY (resolved before the
    # answer is produced) is benign exploration; one LATE (caught near/after
    # the answer) is the real "I shipped something wrong" signal. Last third
    # of the CoT counts full weight; earlier ones count half. Validated on the
    # hard + curriculum runs: this lifts passes that harmlessly resolved an
    # early contradiction (false-low 18%->9% on deepseek-hard) without losing
    # fail coverage, and widens the pass/fail gap on both sets.
    c_late = sum(1 for m in _CONTRADICTION.finditer(cot) if m.start() / length > 0.66)
    c_eff = (c - c_late) * 0.5 + c_late  # early @0.5, late @1.0
    klen = length / 1000
    density = (h + s + c + t + a) / klen

    signals = {
        "hedging": h,
        "self_corrections": s,
        "contradictions": c,
        "late_contradictions": c_late,
        "struggle": t,
        "giveup": g,
        "approach_switches": a,
        "marker_density": round(density, 2),
        "cot_len": length,
    }

    # Confidence rubric — FLIPPED: struggle lowers confidence. Contradictions
    # (self-caught errors / debugging prior failures) are the strongest signal;
    # heavy self-correction = flailing. Approach-switching (>=3) is a strong
    # mid-CoT strategy abandonment. NOTE: a >=2 was tried and retracted — it
    # added no separation on the hard set and worsened inversion on the full
    # curriculum (it flags easy-scenario passes where the model harmlessly
    # considers one alternative). a==2 is non-informative, so only a>=3 fires.
    # Contradictions use the position-weighted c_eff (early @0.5, late @1.0)
    # EXCEPT the score-1 floor: 8+ contradictions anywhere is unambiguous
    # flailing regardless of position (and pass-safe — no gate-pass record
    # reaches it). Check strongest signals first.
    if c >= 8 or s >= 50:
        score = 1
    elif c_eff >= 3 or s >= 22 or (h >= 15 and s >= 15) or a >= 3:
        score = 2
    elif c_eff >= 1 or s >= 12 or h >= 8 or t >= 4:
        score = 3
    elif s >= 5 or h >= 4 or t >= 2 or g >= 2:
        score = 4
    else:
        score = 5

    parts = []
    if c:
        parts.append(f"{c} self-caught contradictions ({c_late} late)")
    if s:
        parts.append(f"{s} self-corrections")
    if a:
        parts.append(f"{a} approach switches")
    if h:
        parts.append(f"{h} hedges")
    if t:
        parts.append(f"{t} struggle markers")
    if g:
        parts.append(f"{g} give-up phrases")
    reasoning = (", ".join(parts) or "clean, low-marker CoT") + (
        f"; marker density {density:.1f}/kchar"
    )

    return {"score": score, "reasoning": reasoning, "signals": signals}
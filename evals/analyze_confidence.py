"""Analyze self-reported, metadata-first confidence against eval ground truth.

Reads eval-run JSONL (from `python -m evals.run ...`) and computes, per
(model x tier) cell, whether the self-reported confidence (hard = fenced prelude,
soft = structured first-field) predicts the deterministic gate outcome, and
how it compares to the cheap baselines (cot_analysis_score, llm_judge_score).

Design (see changes.md "Self-reported, metadata-first confidence"):
  - Truth label: binary (gate_status == "pass"); soft_pass and timeouts dropped.
  - Hard unit: record-level (one up-front prelude per record vs final gate).
  - Soft unit: all attempts (each attempt's soft vs that attempt's stage ==
    "success"); fallback-stage traces and attempts with no soft score are
    excluded. The coverage gap (attempts with no soft, and their fail rate) is
    reported because soft is structurally unavailable when the model's output
    failed to parse — hard (separate prelude call) covers that mode.
  - Never pooled across models; stratified by tier.

Pure-stdlib stats (no numpy/scipy/sklearn available in this env):
  - AUC-ROC via the Mann-Whitney rank formula (tie-handled), with bootstrap CIs.
  - Brier (score/CONFIDENCE_SCORE_MAX as probability) and ECE (ECE_N_BINS bins)
    for hard/soft only.
  - Cohen's d for pass/fail separation.
  - Precision/recall of "flag score < T -> predict fail" at FLAG_THRESHOLDS.
  - Silently-overconfident rate (fail AND score >= OVERCONF_THRESHOLD) — the
    online-safety metric.

Tunable constants (defined in the "Tunable constants" block below; this is a
quick reference — edit the definitions, not this table):

| Constant                | Was (magic)        | Purpose                                              |
|-------------------------|--------------------|------------------------------------------------------|
| CONFIDENCE_SCORE_MAX    | 100.0 (brier, ece) | score->probability divisor; matches schema le=100    |
| GATE_PASS / GATE_FAIL   | "pass" / "fail"    | truth-label gate statuses (soft_pass dropped)        |
| DIMS                    | _DIMS              | the three self-reported dimensions                   |
| FLAG_THRESHOLDS         | _FLAG_THRESHOLDS   | PR-curve "flag low confidence" thresholds            |
| OVERCONF_THRESHOLD      | 80                 | silently-overconfident score cutoff                  |
| OVERCONF_RATE_CAP       | 0.25 (_verdict)    | verdict's "overconf-HIGH" rate threshold             |
| DEFAULT_N_BOOT          | 2000 (3 places)    | bootstrap iterations                                 |
| BOOTSTRAP_ALPHA         | 0.05               | 95% percentile CI                                    |
| DEFAULT_SEED            | 0 (3 places)       | base bootstrap RNG seed                              |
| AUC_NULL                | 0.5 (_verdict)     | no-discrimination AUC baseline                       |
| SEED_OFFSET_*           | +0..+5 (analyze)   | per-metric bootstrap seed offsets                    |
| ECE_N_BINS              | 10 (ece default)   | ECE bin count                                        |

Usage:
    python -m evals.analyze_confidence --results evals/results/<run>.jsonl
    python -m evals.analyze_confidence --results a.jsonl b.jsonl --out report.json
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from strategies.confidence import geo_correctness_score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunable constants — all knobs in one place
# ---------------------------------------------------------------------------

# Confidence score range. Matches EvaluationMetadata.confidence_score (le=100)
# in strategies/confidence.py; used to convert a 0-100 score to a probability.
CONFIDENCE_SCORE_MAX = 100

# Truth label: only these gate_status values contribute observations.
# soft_pass is dropped (ambiguous: rendered, no checks to fail); timeouts have
# no recipe_metadata and drop naturally.
GATE_PASS = "pass"
GATE_FAIL = "fail"

# The three self-reported dimensions emitted by the model.
DIMS = ("geometric_correctness", "request_ambiguity", "end_to_end")

# "Flag low confidence -> predict fail" thresholds (score < T) for the PR curve.
FLAG_THRESHOLDS = (20, 40, 60, 80)

# A failure scored >= this is "silently overconfident" (the online-safety metric).
OVERCONF_THRESHOLD = 80
# A cell's silently-overconfident rate above this is flagged "overconf-HIGH".
OVERCONF_RATE_CAP = 0.25

# Bootstrap AUC confidence interval.
DEFAULT_N_BOOT = 2000
BOOTSTRAP_ALPHA = 0.05  # -> 95% percentile CI
DEFAULT_SEED = 0
# AUC value representing no discrimination (the "coin flip" baseline).
AUC_NULL = 0.5
# Per-metric bootstrap seed offsets (each stream independently reproducible
# but distinct, given one base seed).
SEED_OFFSET_HARD = 0
SEED_OFFSET_SOFT = 1
SEED_OFFSET_COT = 2
SEED_OFFSET_JUDGE = 3
SEED_OFFSET_HARD_DIMS = 4
SEED_OFFSET_SOFT_DIMS = 5

# ECE binning.
ECE_N_BINS = 10


# ---------------------------------------------------------------------------
# Pure-Python statistics
# ---------------------------------------------------------------------------

def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _rank_average(values: list[float]) -> list[float]:
    """Average ranks (1-indexed) with tie handling."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0  # positions i+1 .. j+1, averaged
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def auc_roc(scores: list[float], labels: list[int]) -> float | None:
    """AUC via the Mann-Whitney U statistic (tie-handled). None if one class empty."""
    n_pos = sum(1 for l in labels if l)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0 or not scores:
        return None
    ranks = _rank_average(scores)
    sum_pos_ranks = sum(ranks[i] for i in range(len(labels)) if labels[i])
    u = sum_pos_ranks - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def bootstrap_auc_ci(
    scores: list[float],
    labels: list[int],
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    alpha: float = BOOTSTRAP_ALPHA,
) -> tuple[float | None, float | None, float | None]:
    """(auc, lo, hi) 95% CI via percentile bootstrap. None if undefined."""
    auc = auc_roc(scores, labels)
    n = len(scores)
    if auc is None or n < 2:
        return auc, None, None
    rng = random.Random(seed)
    aucs: list[float] = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        s = [scores[i] for i in idx]
        l = [labels[i] for i in idx]
        a = auc_roc(s, l)
        if a is not None:
            aucs.append(a)
    if not aucs:
        return auc, None, None
    aucs.sort()
    lo = aucs[int((alpha / 2) * len(aucs))]
    hi = aucs[int((1 - alpha / 2) * len(aucs)) - 1]
    return auc, lo, hi


def brier(scores: list[float], labels: list[int]) -> float | None:
    """Mean squared error treating score/CONFIDENCE_SCORE_MAX as a probability."""
    if not scores:
        return None
    return sum(
        (s / CONFIDENCE_SCORE_MAX - (1.0 if l else 0.0)) ** 2
        for s, l in zip(scores, labels)
    ) / len(scores)


def ece(scores: list[float], labels: list[int], n_bins: int = ECE_N_BINS) -> float | None:
    """Expected Calibration Error (n_bins bins by predicted probability)."""
    if not scores:
        return None
    bins = [[0.0, 0, 0] for _ in range(n_bins)]  # [conf_sum, n, n_pos]
    for s, l in zip(scores, labels):
        p = s / CONFIDENCE_SCORE_MAX
        b = min(int(p * n_bins), n_bins - 1)
        bins[b][0] += p
        bins[b][1] += 1
        bins[b][2] += 1 if l else 0
    total = len(scores)
    return sum((n / total) * abs((pos / n) - (conf / n))
              for conf, n, pos in bins if n > 0)


def cohen_d(scores: list[float], labels: list[int]) -> float | None:
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if len(pos) < 2 or len(neg) < 2:
        return None
    mp, mn = _mean(pos), _mean(neg)
    vp = statistics.variance(pos)
    vn = statistics.variance(neg)
    pooled = math.sqrt(((len(pos) - 1) * vp + (len(neg) - 1) * vn) / (len(pos) + len(neg) - 2))
    return None if pooled == 0 else (mp - mn) / pooled


def pr_flag_low(scores: list[float], labels: list[int]) -> list[dict]:
    """Precision/recall of 'flag score < T -> predict fail' at each threshold."""
    n_fail = sum(1 for l in labels if not l)
    out = []
    for t in FLAG_THRESHOLDS:
        flagged = [(s, l) for s, l in zip(scores, labels) if s < t]
        n_flagged = len(flagged)
        n_flagged_fail = sum(1 for _, l in flagged if not l)
        out.append({
            "threshold": t,
            "precision": (n_flagged_fail / n_flagged) if n_flagged else None,
            "recall": (n_flagged_fail / n_fail) if n_fail else None,
            "n_flagged": n_flagged,
        })
    return out


# ---------------------------------------------------------------------------
# Observation extraction
# ---------------------------------------------------------------------------

def _dim_scores(meta: Any) -> dict[str, int | None]:
    """Extract per-dimension confidence_score from a serialized EvaluationMetadata."""
    out: dict[str, int | None] = {}
    if not isinstance(meta, dict):
        return {d: None for d in DIMS}
    for d in DIMS:
        sub = meta.get(d)
        if isinstance(sub, dict):
            v = sub.get("confidence_score")
            out[d] = int(v) if isinstance(v, (int, float)) else None
        else:
            out[d] = None
    return out


def _contradictions(meta: Any) -> bool | None:
    if not isinstance(meta, dict):
        return None
    v = meta.get("contradictions_found")
    return bool(v) if isinstance(v, bool) else None


def extract_observations(records: list[dict]) -> dict:
    hard_obs: list[dict] = []   # record-level
    soft_obs: list[dict] = []   # attempt-level
    cot_obs: list[dict] = []
    judge_obs: list[dict] = []
    coverage = {"total": 0, "no_soft": 0, "no_soft_fail": 0}
    # contradictions_found precision-for-fail (record-level, hard)
    contra_total = 0
    contra_fail = 0

    for r in records:
        model = r.get("model", "?")
        tier = r.get("tier")
        gate = r.get("gate_status")
        # Strict-pass label; drop soft_pass and timeouts (timeouts have no
        # recipe_metadata, so hard is None and they drop naturally, but be
        # explicit so they never enter the denominator).
        if gate not in (GATE_PASS, GATE_FAIL):
            continue
        label = gate == GATE_PASS
        rm = r.get("recipe_metadata") or {}
        hard_meta = rm.get("evaluation_metadata_hard")
        # Defensive fallback: on complete-failure records the record-level hard
        # may be None even though the prelude ran and stored it on each attempt
        # trace (hard is one up-front prelude shared across attempts). Fall back
        # to the last attempt that has it so the worst failures aren't silently
        # dropped (they're the most informative silently-overconfident cases).
        if hard_meta is None:
            for t in reversed(rm.get("attempt_traces") or []):
                if t.get("evaluation_metadata_hard"):
                    hard_meta = t.get("evaluation_metadata_hard")
                    break
        soft_meta_record = rm.get("evaluation_metadata_soft")

        hard = geo_correctness_score(hard_meta)
        if hard is not None:
            hard_obs.append({
                "model": model, "tier": tier, "score": float(hard), "label": label,
                "dims": _dim_scores(hard_meta), "contradictions": _contradictions(hard_meta),
            })
            c = _contradictions(hard_meta)
            if c is True:
                contra_total += 1
                if not label:
                    contra_fail += 1

        cot = r.get("cot_analysis_score")
        if cot is not None:
            cot_obs.append({"model": model, "tier": tier, "score": float(cot), "label": label})
        judge = r.get("llm_judge_score")
        if judge is not None:
            judge_obs.append({"model": model, "tier": tier, "score": float(judge), "label": label})

        # Attempt-level soft. hard is shared up-front so it stays record-level.
        for t in (rm.get("attempt_traces") or []):
            stage = t.get("stage") or ""
            if stage.startswith("fallback"):  # different strategy, no metadata
                continue
            coverage["total"] += 1
            soft = geo_correctness_score(t.get("evaluation_metadata_soft"))
            if soft is None:
                coverage["no_soft"] += 1
                if stage != "success":
                    coverage["no_soft_fail"] += 1
                continue
            soft_obs.append({
                "model": model, "tier": tier, "score": float(soft),
                "label": stage == "success",
                "dims": _dim_scores(t.get("evaluation_metadata_soft")),
                "attempt": t.get("attempt"),
            })

    return {
        "hard": hard_obs, "soft": soft_obs, "cot": cot_obs, "judge": judge_obs,
        "coverage": coverage,
        "contradictions": {"total_true": contra_total, "fail_given_true": contra_fail},
    }


# ---------------------------------------------------------------------------
# Per-cell metrics
# ---------------------------------------------------------------------------

def _metrics(obs: list[dict], with_calibration: bool, n_boot: int, seed: int) -> dict:
    scores = [o["score"] for o in obs]
    labels = [1 if o["label"] else 0 for o in obs]
    n = len(obs)
    n_pass = sum(labels)
    n_fail = n - n_pass
    auc, lo, hi = bootstrap_auc_ci(scores, labels, n_boot=n_boot, seed=seed)
    m = {
        "n": n, "n_pass": n_pass, "n_fail": n_fail,
        "auc": auc, "auc_lo": lo, "auc_hi": hi,
        "mean_pass": _mean([s for s, l in zip(scores, labels) if l]),
        "mean_fail": _mean([s for s, l in zip(scores, labels) if not l]),
        "cohen_d": cohen_d(scores, labels),
        "silently_overconf": sum(1 for s, l in zip(scores, labels) if (not l) and s >= OVERCONF_THRESHOLD),
    }
    m["silently_overconf_rate"] = (
        m["silently_overconf"] / n_fail if n_fail else None
    )
    if with_calibration:
        m["brier"] = brier(scores, labels)
        m["ece"] = ece(scores, labels)
        m["pr"] = pr_flag_low(scores, labels)
    return m


def _dim_metrics(obs: list[dict], n_boot: int, seed: int) -> dict[str, dict]:
    out = {}
    for d in DIMS:
        sub = [{"score": o["score"], "label": o["label"]} for o in obs
               if o["dims"].get(d) is not None]
        # rewrite score to the dimension score
        pairs = [(o["dims"][d], o["label"]) for o in obs if o["dims"].get(d) is not None]
        if not pairs:
            out[d] = {"n": 0, "auc": None}
            continue
        scores = [float(p[0]) for p in pairs]
        labels = [1 if p[1] else 0 for p in pairs]
        auc, lo, hi = bootstrap_auc_ci(scores, labels, n_boot=n_boot, seed=seed)
        out[d] = {"n": len(pairs), "auc": auc, "auc_lo": lo, "auc_hi": hi}
    return out


def _verdict(hard: dict, cot: dict | None, overconf_rate_cap: float = OVERCONF_RATE_CAP) -> str:
    if hard["auc"] is None or hard["n"] == 0:
        return "no-data"
    parts = []
    ci_ok = hard["auc_lo"] is not None and hard["auc_lo"] > AUC_NULL
    parts.append("AUC>0.5" if ci_ok else "AUC~0.5/uncertain")
    if cot and cot["auc"] is not None:
        parts.append("beats-cot" if hard["auc"] > cot["auc"] else "no-beat-cot")
    else:
        parts.append("no-cot-baseline")
    rate = hard["silently_overconf_rate"]
    parts.append("overconf-ok" if (rate is None or rate <= overconf_rate_cap) else "overconf-HIGH")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _fmt(x: float | None, nd: int = 2) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def _cell_report(model: str, tier: Any, cells: dict, n_boot: int) -> str:
    lines = [f"=== model={model}  tier={tier} ==="]
    hard = cells["hard"]
    soft = cells["soft"]
    cot = cells["cot"]
    judge = cells["judge"]
    if hard["n"]:
        lines.append(
            f"  HARD (record)  n={hard['n']} pass={hard['n_pass']} fail={hard['n_fail']}"
        )
        lines.append(
            f"    AUC={_fmt(hard['auc'])} [{_fmt(hard['auc_lo'])},{_fmt(hard['auc_hi'])}]  "
            f"Brier={_fmt(hard.get('brier'))}  ECE={_fmt(hard.get('ece'))}  d={_fmt(hard['cohen_d'])}"
        )
        lines.append(
            f"    mean pass={_fmt(hard['mean_pass'],0)} fail={_fmt(hard['mean_fail'],0)}  "
            f"silently-overconf={hard['silently_overconf']}/{hard['n_fail']} "
            f"({_fmt(hard['silently_overconf_rate']*100 if hard['silently_overconf_rate'] else None,0)}%)"
        )
        pr = hard.get("pr") or []
        pr_str = "  ".join(
            f"T{p['threshold']}:P={_fmt(p['precision'])}/R={_fmt(p['recall'])}" for p in pr
        )
        lines.append(f"    flag<T->fail: {pr_str}")
        dims = cells["hard_dims"]
        lines.append(
            "    per-dim AUC: " + "  ".join(f"{d[:3]}={_fmt(dims[d]['auc'])}" for d in DIMS)
        )
        lines.append(f"    verdict: {_verdict(hard, cot)}")
    else:
        lines.append("  HARD: no data")
    if soft["n"]:
        lines.append(
            f"  SOFT (attempt) n={soft['n']} pass={soft['n_pass']} fail={soft['n_fail']}"
        )
        lines.append(
            f"    AUC={_fmt(soft['auc'])} [{_fmt(soft['auc_lo'])},{_fmt(soft['auc_hi'])}]  "
            f"Brier={_fmt(soft.get('brier'))}  ECE={_fmt(soft.get('ece'))}  d={_fmt(soft['cohen_d'])}"
        )
        lines.append(
            f"    mean pass={_fmt(soft['mean_pass'],0)} fail={_fmt(soft['mean_fail'],0)}  "
            f"silently-overconf={soft['silently_overconf']}/{soft['n_fail']}"
        )
        dims = cells["soft_dims"]
        lines.append(
            "    per-dim AUC: " + "  ".join(f"{d[:3]}={_fmt(dims[d]['auc'])}" for d in DIMS)
        )
    else:
        lines.append("  SOFT: no data")
    lines.append(
        f"  COT (baseline)  n={cot['n']}  AUC={_fmt(cot['auc'])} "
        f"[{_fmt(cot['auc_lo'])},{_fmt(cot['auc_hi'])}]"
    )
    lines.append(
        f"  JUDGE (baseline) n={judge['n']} AUC={_fmt(judge['auc'])} "
        f"[{_fmt(judge['auc_lo'])},{_fmt(judge['auc_hi'])}]"
    )
    return "\n".join(lines)


def analyze(records: list[dict], n_boot: int = DEFAULT_N_BOOT, seed: int = DEFAULT_SEED) -> dict:
    obs = extract_observations(records)

    def cell_key(o):
        return (o["model"], o["tier"])

    def grouped(oblist):
        g: dict[tuple, list[dict]] = defaultdict(list)
        for o in oblist:
            g[cell_key(o)].append(o)
        return g

    hard_g = grouped(obs["hard"])
    soft_g = grouped(obs["soft"])
    cot_g = grouped(obs["cot"])
    judge_g = grouped(obs["judge"])
    all_keys = sorted(set(hard_g) | set(soft_g) | set(cot_g) | set(judge_g))

    report_cells = {}
    text_lines = []
    for key in all_keys:
        model, tier = key
        hard_m = _metrics(hard_g.get(key, []), with_calibration=True, n_boot=n_boot, seed=seed + SEED_OFFSET_HARD)
        soft_m = _metrics(soft_g.get(key, []), with_calibration=True, n_boot=n_boot, seed=seed + SEED_OFFSET_SOFT)
        cot_m = _metrics(cot_g.get(key, []), with_calibration=False, n_boot=n_boot, seed=seed + SEED_OFFSET_COT)
        judge_m = _metrics(judge_g.get(key, []), with_calibration=False, n_boot=n_boot, seed=seed + SEED_OFFSET_JUDGE)
        hard_dims = _dim_metrics(hard_g.get(key, []), n_boot=n_boot, seed=seed + SEED_OFFSET_HARD_DIMS)
        soft_dims = _dim_metrics(soft_g.get(key, []), n_boot=n_boot, seed=seed + SEED_OFFSET_SOFT_DIMS)
        cells = {"hard": hard_m, "soft": soft_m, "cot": cot_m, "judge": judge_m,
                 "hard_dims": hard_dims, "soft_dims": soft_dims}
        report_cells[f"{model}|{tier}"] = cells
        text_lines.append(_cell_report(model, tier, cells, n_boot))
        text_lines.append("")

    # On-fail hard-vs-soft mean gap (anti-anchoring test) — pooled within cell is
    # in the cell metrics; here we add a cross-cell note using record-level pairs.
    summary = {
        "n_records": len(records),
        "n_records_strict_pass_fail": len(obs["hard"]) + sum(
            1 for r in records if r.get("gate_status") in (GATE_PASS, GATE_FAIL)
        ),
        "coverage": obs["coverage"],
        "contradictions": obs["contradictions"],
        "cells": report_cells,
    }
    header = [
        f"records={len(records)}  (strict pass/fail used; soft_pass/timeouts dropped)",
        f"coverage gap: {obs['coverage']['no_soft']}/{obs['coverage']['total']} attempts had no soft "
        f"({obs['coverage']['no_soft_fail']} of those failed) — soft unavailable on unparseable outputs",
        f"contradictions_found=True: {obs['contradictions']['total_true']} records, "
        f"{obs['contradictions']['fail_given_true']} failed -> "
        f"precision-for-fail={_fmt(obs['contradictions']['fail_given_true']/obs['contradictions']['total_true'] if obs['contradictions']['total_true'] else None)}",
        "",
    ]
    summary["text"] = "\n".join(header + text_lines)
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_records(paths: list[str]) -> list[dict]:
    records: list[dict] = []
    for p in paths:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze self-reported confidence vs eval ground truth.")
    parser.add_argument("--results", nargs="+", required=True, help="Path(s) to eval-run JSONL.")
    parser.add_argument("--out", default=None, help="Write full report JSON here.")
    parser.add_argument("--n-boot", type=int, default=DEFAULT_N_BOOT, help="Bootstrap iterations for AUC CIs.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Bootstrap RNG seed.")
    args = parser.parse_args()

    records = _load_records(args.results)
    if not records:
        print("No records found.", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(records)} records from {len(args.results)} file(s)")

    summary = analyze(records, n_boot=args.n_boot, seed=args.seed)
    print()
    print(summary["text"])

    if args.out:
        out = Path(args.out)
        with out.open("w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"\nFull report written to {out}")


if __name__ == "__main__":
    main()
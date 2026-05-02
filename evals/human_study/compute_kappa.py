"""Compute Cohen's kappa, confusion matrices, and per-subgroup agreement.

Pre-registration: docs/human_study_protocol.md  (primary endpoint = section 7).

Reads:
    evals/human_study/sample.json
    evals/human_study/responses_<rater>.csv     (one per rater)
    evals/human_study/responses_consensus.csv   (optional, after consensus pass)

Writes:
    evals/human_study/results.json   (machine-readable; consumed by App E figures)

Usage:
    .venv/bin/python -m evals.human_study.compute_kappa
    .venv/bin/python -m evals.human_study.compute_kappa --raters mei,partner
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
HUMAN_STUDY_DIR = REPO_ROOT / "evals" / "human_study"


Q1_BINARY_MAP = {
    "yes": "pass",
    "partial": "fail",
    "no": "fail",
}

AUTO_BINARY_MAP = {
    "pass": "pass",
    "soft_pass": "pass",
    "fail": "fail",
}

Q1_THREEWAY_MAP = {
    "yes": "pass",
    "partial": "soft_pass",
    "no": "fail",
}


def cohens_kappa(rater1: list[str], rater2: list[str]) -> tuple[float, int]:
    """Return (kappa, n) for two raters' aligned label lists."""
    assert len(rater1) == len(rater2)
    n = len(rater1)
    if n == 0:
        return (float("nan"), 0)

    categories = sorted(set(rater1) | set(rater2))
    if len(categories) == 1:
        return (1.0, n)

    po = sum(a == b for a, b in zip(rater1, rater2)) / n
    pe = 0.0
    for cat in categories:
        p1 = sum(1 for x in rater1 if x == cat) / n
        p2 = sum(1 for x in rater2 if x == cat) / n
        pe += p1 * p2

    if pe == 1.0:
        return (1.0 if po == 1.0 else 0.0, n)
    return ((po - pe) / (1.0 - pe), n)


def kappa_bootstrap_ci(
    rater1: list[str],
    rater2: list[str],
    n_resamples: int = 1000,
    seed: int = 1,
    alpha: float = 0.05,
) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(rater1)
    if n == 0:
        return (float("nan"), float("nan"))
    samples: list[float] = []
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        k, _ = cohens_kappa([rater1[i] for i in idx], [rater2[i] for i in idx])
        if not math.isnan(k):
            samples.append(k)
    samples.sort()
    if not samples:
        return (float("nan"), float("nan"))
    lo = samples[int((alpha / 2) * len(samples))]
    hi = samples[int((1 - alpha / 2) * len(samples)) - 1]
    return (lo, hi)


def confusion_matrix(rater1: list[str], rater2: list[str]) -> dict[tuple[str, str], int]:
    cm: Counter[tuple[str, str]] = Counter()
    for a, b in zip(rater1, rater2):
        cm[(a, b)] += 1
    return dict(cm)


def balanced_accuracy(truth: list[str], pred: list[str]) -> float:
    """Mean per-class recall."""
    classes = sorted(set(truth))
    if not classes:
        return float("nan")
    recalls = []
    for c in classes:
        tp = sum(1 for t, p in zip(truth, pred) if t == c and p == c)
        cond = sum(1 for t in truth if t == c)
        if cond == 0:
            continue
        recalls.append(tp / cond)
    return sum(recalls) / len(recalls) if recalls else float("nan")


def load_sample() -> dict:
    with (HUMAN_STUDY_DIR / "sample.json").open() as fh:
        return json.load(fh)


def load_responses(rater: str) -> dict[str, dict]:
    """Return {item_id: {q1: ..., q2: {predicate: ...}, notes: ...}}."""
    path = HUMAN_STUDY_DIR / f"responses_{rater}.csv"
    if not path.exists():
        return {}
    by_item: dict[str, dict] = {}
    with path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            iid = row["item_id"]
            if iid not in by_item:
                by_item[iid] = {"q1": "", "q2": {}, "notes": ""}
            if row.get("q1_overall"):
                by_item[iid]["q1"] = row["q1_overall"]
            if row.get("notes"):
                by_item[iid]["notes"] = row["notes"]
            if row.get("q2_predicate") and row.get("q2_agreement"):
                by_item[iid]["q2"][row["q2_predicate"]] = row["q2_agreement"]
    return by_item


def aligned_labels(
    sample: dict,
    by_item_a: dict[str, dict],
    by_item_b: dict[str, dict],
    project_a,
    project_b,
    items_filter=None,
) -> tuple[list[str], list[str], list[str]]:
    """Return (labels_a, labels_b, item_ids) for items both raters answered."""
    la, lb, ids = [], [], []
    for it in sample["items"]:
        iid = it["item_id"]
        if items_filter and not items_filter(it):
            continue
        a, b = by_item_a.get(iid), by_item_b.get(iid)
        if not a or not b:
            continue
        va, vb = project_a(a, it), project_b(b, it)
        if va is None or vb is None:
            continue
        la.append(va); lb.append(vb); ids.append(iid)
    return la, lb, ids


def primary_endpoint(sample: dict, consensus: dict[str, dict]) -> dict:
    """Cohen's kappa(auto-verdict, human-consensus) on binary collapse."""
    auto_labels: list[str] = []
    cons_labels: list[str] = []
    for it in sample["items"]:
        iid = it["item_id"]
        c = consensus.get(iid)
        if not c or not c.get("q1"):
            continue
        auto_labels.append(AUTO_BINARY_MAP.get(it["auto_verdict"], "fail"))
        cons_labels.append(Q1_BINARY_MAP.get(c["q1"], "fail"))

    if not auto_labels:
        return {"n": 0, "note": "no consensus labels available"}

    k, n = cohens_kappa(auto_labels, cons_labels)
    lo, hi = kappa_bootstrap_ci(auto_labels, cons_labels)
    bal_acc = balanced_accuracy(cons_labels, auto_labels)

    return {
        "endpoint": "kappa(auto, human-consensus) on binary collapse",
        "n": n,
        "kappa": k,
        "ci95_bootstrap": [lo, hi],
        "balanced_accuracy_auto_vs_consensus": bal_acc,
        "confusion_matrix_auto_x_consensus": _stringify_keys(confusion_matrix(auto_labels, cons_labels)),
        "interpretation_landis_koch": _landis_koch(k),
        "passes_pre_registered_threshold": (lo >= 0.70) if not math.isnan(lo) else None,
        "pre_registered_threshold": 0.70,
    }


def _stringify_keys(d: dict[tuple[str, str], int]) -> dict[str, int]:
    return {f"auto={a},human={b}": v for (a, b), v in d.items()}


def _landis_koch(k: float) -> str:
    if math.isnan(k):
        return "n/a"
    if k < 0.0: return "poor"
    if k < 0.20: return "slight"
    if k < 0.40: return "fair"
    if k < 0.60: return "moderate"
    if k < 0.80: return "substantial"
    return "almost-perfect"


def secondary_irr(by_item_a: dict, by_item_b: dict, sample: dict) -> dict:
    """Inter-rater Cohen's kappa between the two human raters (Q1 binary + 3-way)."""
    la, lb, _ = aligned_labels(
        sample, by_item_a, by_item_b,
        project_a=lambda r, it: Q1_BINARY_MAP.get(r["q1"]),
        project_b=lambda r, it: Q1_BINARY_MAP.get(r["q1"]),
    )
    k_bin, n_bin = cohens_kappa(la, lb)

    la3, lb3, _ = aligned_labels(
        sample, by_item_a, by_item_b,
        project_a=lambda r, it: Q1_THREEWAY_MAP.get(r["q1"]),
        project_b=lambda r, it: Q1_THREEWAY_MAP.get(r["q1"]),
    )
    k_three, n_three = cohens_kappa(la3, lb3)
    return {
        "irr_q1_binary": {"kappa": k_bin, "n": n_bin, "interpretation": _landis_koch(k_bin)},
        "irr_q1_threeway": {"kappa": k_three, "n": n_three, "interpretation": _landis_koch(k_three)},
    }


def per_subgroup(sample: dict, consensus: dict, key_fn, key_name: str) -> dict:
    out: dict[str, dict] = {}
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for it in sample["items"]:
        c = consensus.get(it["item_id"])
        if not c or not c.get("q1"):
            continue
        a = AUTO_BINARY_MAP.get(it["auto_verdict"], "fail")
        h = Q1_BINARY_MAP.get(c["q1"], "fail")
        groups[key_fn(it)].append((a, h))
    for grp, pairs in sorted(groups.items()):
        a_list = [p[0] for p in pairs]
        h_list = [p[1] for p in pairs]
        k, n = cohens_kappa(a_list, h_list)
        out[grp] = {"n": n, "kappa": k, "interpretation": _landis_koch(k)}
    return {f"by_{key_name}": out}


def per_predicate_q2(sample: dict, by_item_a: dict, by_item_b: dict, consensus_q2: dict) -> dict:
    """Per-predicate agreement rate (auto's verdict vs majority human view)."""
    by_pred: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for it in sample["items"]:
        iid = it["item_id"]
        for pred in it.get("predicate_checks", []):
            pname = pred["name"]
            auto_v = pred["verdict"]
            cons = (consensus_q2.get(iid) or {}).get(pname) or _majority_q2(by_item_a.get(iid, {}).get("q2", {}).get(pname),
                                                                            by_item_b.get(iid, {}).get("q2", {}).get(pname))
            if not cons:
                continue
            by_pred[pname].append((auto_v, cons))

    out: dict[str, dict] = {}
    for pname, pairs in sorted(by_pred.items()):
        agree = sum(1 for a, h in pairs if _q2_agreement_means_match(a, h))
        out[pname] = {
            "n": len(pairs),
            "agreement_rate": agree / len(pairs) if pairs else float("nan"),
            "disagreement_count": sum(1 for _, h in pairs if h == "disagrees"),
            "unsure_count": sum(1 for _, h in pairs if h == "unsure"),
        }
    return out


def _q2_agreement_means_match(auto_verdict: str, human_label: str) -> bool:
    if human_label == "agree-pass" and auto_verdict == "pass": return True
    if human_label == "agree-fail" and auto_verdict in ("fail", "skip"): return True
    return False


def _majority_q2(a: str | None, b: str | None) -> str | None:
    if a and b and a == b: return a
    if a and not b: return a
    if b and not a: return b
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raters", default="rater_a,rater_b", help="comma-separated rater ids matching responses_<rater>.csv")
    parser.add_argument("--consensus", default="consensus", help="consensus CSV name (responses_<name>.csv)")
    parser.add_argument("--output", type=Path, default=HUMAN_STUDY_DIR / "results.json")
    args = parser.parse_args()

    sample = load_sample()
    raters = [r.strip() for r in args.raters.split(",") if r.strip()]
    if len(raters) != 2:
        print(f"WARNING: expected 2 raters, got {len(raters)}: {raters}")
    rater_responses = {r: load_responses(r) for r in raters}

    consensus = load_responses(args.consensus) if (HUMAN_STUDY_DIR / f"responses_{args.consensus}.csv").exists() else {}
    if not consensus and len(raters) == 2:
        print(f"NOTE: no consensus CSV at responses_{args.consensus}.csv. Falling back to per-rater independent kappas.")

    results: dict = {
        "schema_version": 1,
        "sample_n": sample["actual_n"],
        "raters": raters,
        "consensus_available": bool(consensus),
        "responses_per_rater": {r: len(rr) for r, rr in rater_responses.items()},
    }

    if consensus:
        results["primary"] = primary_endpoint(sample, consensus)
        results["per_tier"] = per_subgroup(sample, consensus, key_fn=lambda it: it.get("tier", "T?"), key_name="tier")
        results["per_strategy"] = per_subgroup(sample, consensus, key_fn=lambda it: it["strategy"], key_name="strategy")
        results["per_model"] = per_subgroup(sample, consensus, key_fn=lambda it: _vendor(it["model"]), key_name="vendor")

    if len(raters) == 2:
        a, b = raters
        results["irr"] = secondary_irr(rater_responses[a], rater_responses[b], sample)

        a_q2 = {iid: r.get("q2", {}) for iid, r in rater_responses[a].items()}
        b_q2 = {iid: r.get("q2", {}) for iid, r in rater_responses[b].items()}
        cons_q2 = {iid: r.get("q2", {}) for iid, r in consensus.items()} if consensus else {}
        results["per_predicate_q2"] = per_predicate_q2(sample, rater_responses[a], rater_responses[b], cons_q2)

        for r in raters:
            la, lb_auto, _ = aligned_labels(
                sample, rater_responses[r], rater_responses[r],
                project_a=lambda r_, it: Q1_BINARY_MAP.get(r_["q1"]),
                project_b=lambda r_, it: AUTO_BINARY_MAP.get(it["auto_verdict"]),
            )
            k, n = cohens_kappa(la, lb_auto)
            results.setdefault("per_rater_vs_auto", {})[r] = {
                "kappa": k, "n": n, "interpretation": _landis_koch(k),
            }

    args.output.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"Wrote {args.output}")
    if "primary" in results:
        p = results["primary"]
        print(f"\nPRIMARY: kappa = {p['kappa']:.3f}  (95% CI [{p['ci95_bootstrap'][0]:.3f}, {p['ci95_bootstrap'][1]:.3f}])  N={p['n']}")
        print(f"         interpretation: {p['interpretation_landis_koch']}")
        print(f"         passes pre-registered threshold (0.70 lower CI): {p['passes_pre_registered_threshold']}")
    elif "irr" in results:
        irr = results["irr"]["irr_q1_binary"]
        print(f"\nIRR (Q1 binary, no consensus yet): kappa = {irr['kappa']:.3f}  N={irr['n']}  ({irr['interpretation']})")
    return 0


def _vendor(model: str) -> str:
    if "anthropic" in model: return "anthropic"
    if "openai" in model: return "openai"
    if "google" in model or "gemini" in model: return "google"
    return "other"


if __name__ == "__main__":
    raise SystemExit(main())

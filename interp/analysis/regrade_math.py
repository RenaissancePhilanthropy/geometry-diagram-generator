#!/usr/bin/env python
r"""Offline re-grade of captured MATH cells with the robust math_verify grader.

The 3-turn capture (interp/capture_qa.py) stores the full completion, the
extracted answer, and the gold answer in meta.jsonl; only the `ok` label depends
on the grader. The original string-normalize grader false-negatived on harmless
formatting differences (\frac{a}{b} vs a/b, \$, decimal vs fraction), which both
under-counted the pass rate AND polluted the "failures" with actually-correct
answers — biasing every confidence/calibration statistic.

Because the residual-stream npz files don't depend on the label, we re-grade
entirely offline from the stored `extracted` vs `gold` fields — no GPU, no
re-capture. Run this in a venv that has math_verify (interp/.venv). Backs up the
original meta.jsonl -> meta.jsonl.orig once so the raw capture is never lost.

Usage:
    interp/.venv/bin/python interp/analysis/regrade_math.py interp/activations/mtx_*_math
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

# interp/ on path so we reuse the exact grader the capture uses.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tasks_qa import _math_eq  # noqa: E402


def regrade(act_dir: str) -> None:
    d = Path(act_dir)
    meta = d / "meta.jsonl"
    if not meta.exists():
        print(f"  SKIP {d.name}: no meta.jsonl")
        return
    recs = [json.loads(line) for line in meta.open() if line.strip()]
    if not recs:
        print(f"  SKIP {d.name}: empty")
        return
    before = sum(bool(r["grade"]["ok"]) for r in recs)
    up = dn = 0
    for r in recs:
        old = bool(r["grade"]["ok"])
        new = _math_eq(r.get("extracted"), r.get("gold"))
        if new and not old:
            up += 1
        elif old and not new:
            dn += 1
        r["grade"]["ok"] = new
        r["grade"]["stage"] = "correct" if new else "answer"
    after = sum(bool(r["grade"]["ok"]) for r in recs)
    orig = d / "meta.jsonl.orig"
    if not orig.exists():
        shutil.copy(meta, orig)  # one-time backup of the raw capture labels
    with meta.open("w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    n = len(recs)
    print(f"  {d.name}: pass {before}/{n} ({100 * before / n:.0f}%) -> "
          f"{after}/{n} ({100 * after / n:.0f}%)   [+{up} rescued, -{dn} demoted]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("act_dirs", nargs="+", help="one or more mtx_*_math activation dirs")
    args = ap.parse_args()
    for d in args.act_dirs:
        regrade(d)

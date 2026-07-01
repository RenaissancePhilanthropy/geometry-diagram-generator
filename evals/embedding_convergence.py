"""Across-run embedding convergence — does a generator model produce similar
results for the same scenario across its runs, at each stage?

For each (generator_model, scenario) group — pooling all cot-bearing runs across
run_ids — and each **stage** (the CoT and the same answer representations the
in-run judge uses: `flat_dsl`, `raw_dsl`, `nl_ir`, `tikz`) and each **embedding
model** (gemma, qwen4b, qwen8b), reconstruct each run's stage embedding from the
existing per-run caches (no re-embedding) and score how **convergent** the runs
are at that stage:

  - mean_pairwise_cos  — mean cosine over all pairs of runs' stage vectors
                         (1 = all identical, ~0 = unrelated)
  - mean_centroid_cos  — mean cosine of each run's vector to the group centroid
  - spread             — 1 − mean_pairwise_cos (0 = fully convergent)

Scored per (scenario × gen_model × emb_model × stage), alongside the existing
in-run cot↔answer cosine (this is a different, consensus-style signal).

Per the design decisions: pool all runs per (model, scenario) regardless of
run_id; report both pairwise and centroid metrics; scenario-level correlation
(group convergence vs that (model, scenario)'s pass rate).

Reuses evals.embedding_judge (_extract_runs, render_record, REPRS) and
util.embeddings (chunk_text, _halve, cosine, pool, text_hash, MIN_HALVE_CHARS).
The gemma run chunked at max_chars=4000/overlap=400 with halve-on-stall; the
qwen runs used max_chars=30000/overlap=300 (whole-CoT, no halving). These are
replicated here so chunk hashes match the caches exactly.

Usage:
    python -m evals.embedding_convergence \\
        --results evals/results \\
        --cache gemma=evals/embedding_judge_out_gemmae/embeddings_cache.sqlite \\
        --cache qwen4b=evals/embedding_judge_out_qwene4b/embeddings_cache.sqlite \\
        --cache qwen8b=evals/embedding_judge_out_qwene8b/embeddings_cache.sqlite \\
        --out-dir evals/embedding_convergence_out
"""
from __future__ import annotations

import argparse
import array
import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from evals.embedding_judge import REPRS, _expand_paths, _extract_runs, render_record
from util.embeddings import MIN_HALVE_CHARS, _halve, chunk_text, cosine, pool, text_hash

# Stage = the CoT plus the answer reps. (tikz skipped per-run where empty.)
STAGE_COT = "cot"
STAGES = [STAGE_COT] + list(REPRS)

# Per-embedding-model reconstruction config: (max_chars, overlap, allow_halve).
# Must match what each run actually used so chunk hashes hit the cache.
EMB_CONFIGS = {
    "gemma": (4000, 400, True),
    "qwen4b": (30000, 300, False),
    "qwen8b": (30000, 300, False),
}


# ---------------------------------------------------------------------------
# cache + vector reconstruction
# ---------------------------------------------------------------------------

def load_cache(path: str) -> dict[str, array.array]:
    """{content_hash: array.array('f', vector)} from a sqlite embeddings cache."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    out: dict[str, array.array] = {}
    for row in conn.execute("SELECT content_hash, vec_json FROM embeddings"):
        out[row["content_hash"]] = array.array("f", json.loads(row["vec_json"]))
    conn.close()
    return out


def _stage_text(run: dict, stage: str) -> str | None:
    if stage == STAGE_COT:
        return run.get("cot")
    return render_record(run["_record"], stage)


def reconstruct(
    text: str | None,
    max_chars: int,
    overlap: int,
    allow_halve: bool,
    cache: dict[str, array.array],
    depth: int = 0,
) -> tuple[list[array.array] | None, int, int]:
    """Reconstruct the chunk vectors for ``text`` from ``cache``.

    Chunks ``text`` the same way the run did; looks up each chunk by hash; for a
    missing chunk (over-cap → the run halved it), replicates the halving and
    looks up the halves (recursively). Returns (chunk_vectors, n_found, n_total);
    chunk_vectors is None if nothing was found / text is empty.
    """
    if not text:
        return None, 0, 0
    chunks = chunk_text(text, max_chars, overlap)
    if not chunks:
        return None, 0, 0
    vecs: list[array.array] = []
    found = 0
    for ch in chunks:
        v = cache.get(text_hash(ch))
        if v is not None:
            vecs.append(v)
            found += 1
        elif allow_halve and depth < 6 and len(ch) >= MIN_HALVE_CHARS:
            sub, sf, st = _halve_and_collect(ch, max_chars, overlap, cache, depth + 1)
            if sub:
                vecs.extend(sub)
                found += sf
    return (vecs if vecs else None), found, len(chunks)


def _halve_and_collect(
    chunk: str, max_chars: int, overlap: int, cache: dict[str, array.array], depth: int
) -> tuple[list[array.array], int, int]:
    halves = _halve(chunk)
    out: list[array.array] = []
    found = 0
    for h in halves:
        v = cache.get(text_hash(h))
        if v is not None:
            out.append(v)
            found += 1
        elif depth < 6 and len(h) >= MIN_HALVE_CHARS:
            sub, sf, _ = _halve_and_collect(h, max_chars, overlap, cache, depth + 1)
            out.extend(sub)
            found += sf
    return out, found, 2


def doc_vector(
    text: str | None, max_chars: int, overlap: int, allow_halve: bool, cache: dict[str, array.array]
) -> list[float] | None:
    """One L2-normalized pooled vector for the stage text (char-length weighted)."""
    vecs, _, _ = reconstruct(text, max_chars, overlap, allow_halve, cache)
    if not vecs:
        return None
    weights = [float(len(v)) for v in vecs]  # proxy for chunk size; fine for pooling
    return pool([list(v) for v in vecs], weights)


# ---------------------------------------------------------------------------
# convergence metrics
# ---------------------------------------------------------------------------

def mean_pairwise_cos(vecs: list[list[float]]) -> float:
    n = len(vecs)
    if n < 2:
        return 1.0 if n == 1 else 0.0
    s = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            s += cosine(vecs[i], vecs[j])
            pairs += 1
    return s / pairs if pairs else 0.0


def mean_centroid_cos(vecs: list[list[float]]) -> float | None:
    if len(vecs) < 2:
        return None
    cen = pool(vecs)
    if cen is None:
        return None
    return sum(cosine(v, cen) for v in vecs) / len(vecs)


def _ranks(vals: list[float]) -> list[float]:
    o = sorted(range(len(vals)), key=lambda i: vals[i])
    rk = [0.0] * len(vals)
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[o[j + 1]] == vals[o[i]]:
            j += 1
        for x in range(i, j + 1):
            rk[o[x]] = (i + j) / 2.0
        i = j + 1
    return rk


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3:
        return None
    ra, rb = _ranks(a), _ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((y - mb) ** 2 for y in rb))
    if da == 0 or db == 0:
        return None
    return num / (da * db)


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def run(results_dir: str, caches: dict[str, str], out_dir: str) -> dict:
    files = _expand_paths([results_dir])
    if not files:
        print("No JSONL files found.", file=sys.stderr)
        return {"files": 0}
    runs, cov = _extract_runs(files, with_prompt=False)
    print(f"Loaded {len(runs)} cot-bearing runs from {len(files)} files.")

    # group by (model, scenario) across all run_ids
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in runs:
        groups[(r["model"], r["scenario_id"])].append(r)
    print(f"Groups (model × scenario): {len(groups)}; with ≥2 runs: "
          f"{sum(1 for v in groups.values() if len(v) >= 2)}.")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    recon_hits = {"found": 0, "total": 0}

    for emb_name, cache_path in caches.items():
        max_chars, overlap, allow_halve = EMB_CONFIGS.get(emb_name, (30000, 300, False))
        if emb_name not in EMB_CONFIGS:
            print(f"  warning: unknown emb model {emb_name!r}; using 30000/300 no-halve", file=sys.stderr)
        print(f"Loading cache {emb_name} ({cache_path})…", flush=True)
        cache = load_cache(cache_path)
        print(f"  {len(cache)} cached vectors.", flush=True)

        for (model, scenario), gruns in groups.items():
            for stage in STAGES:
                # scored runs: have a stage vector AND a pass/fail gate
                vvecs: list[list[float]] = []
                gates: list[str] = []
                for r in gruns:
                    gs = r.get("gate_status")
                    if gs not in ("pass", "fail"):
                        continue
                    txt = _stage_text(r, stage)
                    if not txt:
                        continue
                    vecs, nf, nt = reconstruct(txt, max_chars, overlap, allow_halve, cache)
                    recon_hits["found"] += nf
                    recon_hits["total"] += nt
                    if not vecs:
                        continue
                    dv = pool([list(v) for v in vecs], [float(len(v)) for v in vecs])
                    if dv is None:
                        continue
                    vvecs.append(dv)
                    gates.append(gs)
                n = len(vvecs)
                if n < 2:
                    continue
                mp = mean_pairwise_cos(vvecs)
                mc = mean_centroid_cos(vvecs)
                rows.append({
                    "scenario_id": scenario,
                    "model": model,
                    "emb_model": emb_name,
                    "stage": stage,
                    "mean_pairwise_cos": mp,
                    "mean_centroid_cos": mc,
                    "spread": 1.0 - mp,
                    "n_runs": n,
                    "pass_rate": sum(1 for g in gates if g == "pass") / n,
                })
        del cache  # release before next emb

    # write the long convergence table
    cols = ["scenario_id", "model", "emb_model", "stage",
            "mean_pairwise_cos", "mean_centroid_cos", "spread", "n_runs", "pass_rate"]
    with (out / "convergence.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["model"], r["scenario_id"], r["emb_model"], r["stage"])):
            w.writerow(r)

    _write_correlation(rows, out / "correlation.txt")
    _write_coverage(cov, groups, recon_hits, len(rows), caches, out / "coverage.txt")

    print(f"\nWrote {len(rows)} convergence rows to {out}/")
    print("  convergence.csv, correlation.txt, coverage.txt")
    return {"rows": len(rows), "groups": len(groups), "recon_hit_rate": recon_hits["found"] / max(1, recon_hits["total"])}


def _write_correlation(rows: list[dict], path: Path) -> None:
    """Scenario-level: does group convergence correlate with that group's pass rate?"""
    lines: list[str] = []
    lines.append("Scenario-level correlation: group convergence vs that (model×scenario)'s pass rate")
    lines.append("(Spearman over all (model×scenario) groups with ≥2 scored runs; +mean convergence of")
    lines.append(" high-pass (≥0.8) vs low-pass (<0.5) groups, and n.)")
    lines.append("=" * 90)
    # overall per (emb, stage)
    lines.append(f"{'emb_model':10s} {'stage':10s} {'n':>5s} {'ρ_pairwise':>10s} {'ρ_centroid':>10s} "
                 f"{'conv_hi':>8s} {'conv_lo':>8s} {'hi_n':>4s} {'lo_n':>4s}")
    lines.append("-" * 90)
    for emb in EMB_CONFIGS:
        for stage in STAGES:
            sub = [r for r in rows if r["emb_model"] == emb and r["stage"] == stage]
            if len(sub) < 3:
                lines.append(f"{emb:10s} {stage:10s} {len(sub):5d}   n/a")
                continue
            pp = spearman([r["mean_pairwise_cos"] for r in sub], [r["pass_rate"] for r in sub])
            pc = spearman([r["mean_centroid_cos"] for r in sub], [r["pass_rate"] for r in sub])
            hi = [r["mean_pairwise_cos"] for r in sub if r["pass_rate"] >= 0.8]
            lo = [r["mean_pairwise_cos"] for r in sub if r["pass_rate"] < 0.5]
            hi_m = sum(hi) / len(hi) if hi else None
            lo_m = sum(lo) / len(lo) if lo else None
            def f(x): return f"{x:.3f}" if x is not None else "  n/a"
            lines.append(f"{emb:10s} {stage:10s} {len(sub):5d} {f(pp):>10s} {f(pc):>10s} "
                         f"{f(hi_m):>8s} {f(lo_m):>8s} {len(hi):4d} {len(lo):4d}")
    # per (gen_model, emb, stage) — who converges and does it track pass rate?
    lines.append("\nper generator_model (mean_pairwise_cos averaged, and ρ vs pass_rate):")
    lines.append(f"{'model':34s} {'emb':8s} {'stage':10s} {'n':>4s} {'mean_conv':>9s} {'ρ':>8s}")
    lines.append("-" * 80)
    models = sorted({r["model"] for r in rows})
    for m in models:
        for emb in EMB_CONFIGS:
            for stage in STAGES:
                sub = [r for r in rows if r["model"] == m and r["emb_model"] == emb and r["stage"] == stage]
                if len(sub) < 3:
                    continue
                mc = sum(r["mean_pairwise_cos"] for r in sub) / len(sub)
                rho = spearman([r["mean_pairwise_cos"] for r in sub], [r["pass_rate"] for r in sub])
                lines.append(f"{m[:34]:34s} {emb:8s} {stage:10s} {len(sub):4d} {mc:9.3f} {f(rho):>8s}")
    path.write_text("\n".join(lines) + "\n")


def _write_coverage(cov: dict, groups: dict, recon_hits: dict, nrows: int, caches: dict, path: Path) -> None:
    lines: list[str] = []
    lines.append("Coverage report — across-run convergence")
    lines.append("=" * 50)
    lines.append(f"records seen:       {cov.get('records', 0)}")
    lines.append(f"unique w/ CoT:      {cov.get('kept', 0)}")
    lines.append(f"(model×scenario) groups: {len(groups)}")
    lines.append(f"  with ≥2 runs:     {sum(1 for v in groups.values() if len(v) >= 2)}")
    lines.append(f"  with ≥3 runs:     {sum(1 for v in groups.values() if len(v) >= 3)}")
    lines.append(f"embedding models:   {list(caches.keys())}")
    lines.append(f"stages:             {STAGES}")
    lines.append(f"convergence rows:   {nrows}")
    lines.append(f"reconstruction cache hit rate: "
                 f"{recon_hits['found']}/{recon_hits['total']} = "
                 f"{recon_hits['found'] / max(1, recon_hits['total']):.3f}")
    lines.append("")
    lines.append("Caveat: runs are pooled across all run_ids per the design decision. A few run_ids")
    lines.append("used the GEPA-optimized prompts; the records do NOT store a prompt-version marker,")
    lines.append("so optimized-only coverage cannot be computed from the data alone. Per the user,")
    lines.append("prompt variation had minimal effect, so pooling is acceptable.")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results", default="evals/results", help="dir of eval JSONL files")
    ap.add_argument("--cache", action="append", default=[],
                    help="NAME=PATH per embedding model (repeatable). "
                         "Defaults to the three finished runs' caches.")
    ap.add_argument("--out-dir", default="evals/embedding_convergence_out")
    args = ap.parse_args()
    if args.cache:
        caches = {}
        for spec in args.cache:
            name, _, path = spec.partition("=")
            caches[name] = path
    else:
        caches = {
            "gemma": "evals/embedding_judge_out_gemmae/embeddings_cache.sqlite",
            "qwen4b": "evals/embedding_judge_out_qwene4b/embeddings_cache.sqlite",
            "qwen8b": "evals/embedding_judge_out_qwene8b/embeddings_cache.sqlite",
        }
    run(args.results, caches, args.out_dir)


if __name__ == "__main__":
    main()
#!/usr/bin/env bash
set -euo pipefail

# Embedding judge — cosine(reasoning, answer) consistency per run, bucketed by
# model (verbatim) and aggregated per (model × scenario). Wraps
# evals/embedding_judge.py against the OpenAI-compatible embeddinggemma endpoint.
#
# Usage:
#   ./run_embedding_judge.sh                                # all evals/results/*.jsonl (deduped in-tool)
#   ./run_embedding_judge.sh evals/results/20260619-213519.jsonl
#   ./run_embedding_judge.sh a.jsonl b.jsonl
#   ./run_embedding_judge.sh --with-prompt-baseline
#   ./run_embedding_judge.sh --batch-size 8 --concurrency 8
#   ./run_embedding_judge.sh --out-dir /tmp/embj a.jsonl b.jsonl
#   ./run_embedding_judge.sh --help
#
# Parameters:
#   [FILES...]              One or more eval-run JSONL files to score. If none are
#                           given, ALL evals/results/*.jsonl are used. The tool
#                           recovers CoT from attempt_traces (the .cotbackfill.jsonl
#                           files are NOT required — the originals already carry
#                           CoT), skips records with no recoverable CoT, and dedups
#                           the same run across original / *_rescored / *.cotbackfill
#                           variants (keeping rescored > original > backfill, by run
#                           identity) so passing everything is safe — nothing is
#                           double-counted.
#   --out-dir DIR           Output directory (default evals/embedding_judge_out,
#                           gitignored). Writes runs.jsonl, matrix.csv,
#                           summary.txt, coverage.txt, repr_signal.txt, and a
#                           resumable embeddings_cache.sqlite.
#   --batch-size N          Chunks per embeddings request (default 8). Each chunk
#                           is ≤ --max-chars (~1400 Gemma tokens); keep batches small
#                           so each request is light and the single ollama server
#                           keeps up (big batches under concurrency overload it ->
#                           timeouts -> the client drops connections -> ollama logs
#                           "aborting embedding request" -> a retry cascade).
#   --concurrency N         Parallel embeddings requests (default 3). LOW on
#                           purpose: a single ollama server serialises embedding
#                           work, so high concurrency just queues and times out.
#   --max-chars N           Chunk size in chars (default 3000, ≈1000-1500
#                           embeddinggemma tokens). 3000 (not 4000) because TOKEN-
#                           DENSE content (code, coordinate lists, LaTeX) is ~2x
#                           denser than prose and a 4000-char dense chunk can
#                           itself exceed the 2048-token cap. Long texts are
#                           CHUNKED on whitespace boundaries with --overlap, never
#                           truncated; any rare over-cap chunk is halved on-stall.
#   --overlap N             Overlap between chunks in chars (default 300).
#   --per-call-timeout F    Per-request timeout in seconds (default 90). Generous:
#                           a slow request should FINISH, not be aborted (aborts
#                           cascade). An over-cap chunk is detected and HALVED
#                           immediately (no retries — it would always fail).
#   --embedding-model M     Embedding model id (default embeddinggemma). NOTE: the
#                           served id is `embeddinggemma`, NOT `gemma4` — the wrong
#                           id silently returns nothing.
#   --embedding-base-url U  OpenAI-compatible base URL
#                           (default http://192.168.178.31:11434/v1). Also honours
#                           the EMBEDDING_BASE_URL / EMBEDDING_MODEL /
#                           EMBEDDING_API_KEY env vars (CLI flags win).
#   --with-prompt-baseline  Also embed the original user_prompt and add a cos_prompt
#                           column = cosine(cot, user_prompt). See below.
#
# Long-text chunking (embeddinggemma caps at 2048 tokens): the server silently
# truncates over-cap inputs to ~the first 2048 tokens and sometimes stalls, so
# previously 72% of CoTs (57% of all CoT tokens) were dropped. Each text is now
# chunked into ≤~1400-token windows (boundary-aware, with overlap), embedded per
# chunk, and aggregated. Chunk vectors are cached (sha256-keyed), so re-runs are
# free and shared chunks across CoTs dedupe.
#
# What it scores (per run, per answer rep, kept SEPARATE — nothing is discarded):
#   cos_<rep>_max    best-matching chunk ("does some part of the reasoning match?")
#   cos_<rep>_mean   average per-chunk agreement
#   cos_<rep>_pooled cosine of the char-length-weighted, L2-normalized mean chunk vec
#   cos_combined_<a> naive mean of the available cos_<rep>_<a> (placeholder; a real
#                    single score can be weighted once we know which (rep, agg) tracks)
#   reps: flat_dsl (flattened construction), raw_dsl (full DSL JSON), nl_ir (NL from
#         compiled diagram_ir), tikz (tikz_code — usually None in eval files)
#
# This is an internal-COHERENCE signal (does the reasoning match the artifact the
# model built), read alongside gate/pass — NOT a correctness judge. repr_signal.txt
# reports each representation's AUC for predicting gate_status==pass so you can
# later see which representation tracks correctness and weight a real single score.
#
# AUC data caveat: failing runs are often no-CoT (dropped), so cot-bearing runs
# skew pass-heavy and repr_signal.txt AUC shows '-' on a single all-pass file. The
# default (all *.jsonl, deduped) pools files that include cot-bearing FAILS — e.g.
# 20260619-213519 (95 pass/77 fail), 20260619-220616 (100/76), 20260620-194957
# (11/27), 20260620-195029 (11/25); deepseek files like 20260620-154154 (0 pass/40
# fail) supply the fail side — which is what makes the AUC meaningful.
#
# --with-prompt-baseline in detail:
#   The four default scores compare the CoT to the diagram the model BUILT
#   (reasoning vs answer). --with-prompt-baseline adds a different axis: cos_prompt
#   = cosine(cot, user_prompt), i.e. does the chain-of-thought actually talk about
#   the geometry the prompt asked for (reasoning vs the PROMPT). It's a relevance
#   baseline, not an answer-consistency score, so it's off by default. It's useful
#   for interpretation: a high cos_prompt with a low cos_* answer score means the
#   model reasoned about the right problem but built something inconsistent with
#   that reasoning. Adds cos_prompt to runs.jsonl / matrix.csv / repr_signal.txt.
# HELP-END

FILES=()
OUT_DIR="evals/embedding_judge_out"
BATCH_SIZE=8
CONCURRENCY=3
MAX_CHARS=3000
OVERLAP=300
PER_CALL_TIMEOUT=90
EMBEDDING_MODEL="${EMBEDDING_MODEL:-embeddinggemma}"
EMBEDDING_BASE_URL="${EMBEDDING_BASE_URL:-http://192.168.178.31:11434/v1}"
EMBEDDING_API_KEY="${EMBEDDING_API_KEY:-ollama}"
WITH_PROMPT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir)              OUT_DIR="$2"; shift 2 ;;
    --batch-size)           BATCH_SIZE="$2"; shift 2 ;;
    --concurrency)          CONCURRENCY="$2"; shift 2 ;;
    --max-chars)            MAX_CHARS="$2"; shift 2 ;;
    --overlap)              OVERLAP="$2"; shift 2 ;;
    --per-call-timeout)     PER_CALL_TIMEOUT="$2"; shift 2 ;;
    --embedding-model)      EMBEDDING_MODEL="$2"; shift 2 ;;
    --embedding-base-url)   EMBEDDING_BASE_URL="$2"; shift 2 ;;
    --embedding-api-key)    EMBEDDING_API_KEY="$2"; shift 2 ;;
    --with-prompt-baseline) WITH_PROMPT=1; shift ;;
    --help|-h) sed -n '/^# Embedding judge/,/^# HELP-END/p' "$0" | sed 's/^# //'; exit 0 ;;
    --) shift; while [[ $# -gt 0 ]]; do FILES+=("$1"); shift; done ;;
    --*) echo "Unknown option: $1" >&2; exit 1 ;;
    *) FILES+=("$1"); shift ;;
  esac
done

# Default to ALL evals/results/*.jsonl if none given. The tool dedups the same
# run across original / *_rescored / *.cotbackfill variants, so passing everything
# is safe — nothing is double-counted.
if [[ ${#FILES[@]} -eq 0 ]]; then
  mapfile -t FILES < <(ls evals/results/*.jsonl 2>/dev/null || true)
  if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "No files given and none found at evals/results/*.jsonl" >&2
    exit 1
  fi
  echo "No files given; using ${#FILES[@]} jsonl file(s) (deduped in-tool)."
fi

ARGS=(
  --out-dir "$OUT_DIR"
  --embedding-model "$EMBEDDING_MODEL"
  --embedding-base-url "$EMBEDDING_BASE_URL"
  --embedding-api-key "$EMBEDDING_API_KEY"
  --concurrency "$CONCURRENCY"
  --batch-size "$BATCH_SIZE"
  --max-chars "$MAX_CHARS"
  --overlap "$OVERLAP"
  --per-call-timeout "$PER_CALL_TIMEOUT"
)
[[ "$WITH_PROMPT" -eq 1 ]] && ARGS+=(--with-prompt-baseline)
ARGS+=("${FILES[@]}")

uv run python -u -m evals.embedding_judge "${ARGS[@]}"

echo
echo "Done. Key outputs in $OUT_DIR/:"
echo "  coverage.txt    — per-model CoT coverage + per-representation availability"
echo "  repr_signal.txt — per-representation AUC vs gate-pass (informational)"
echo "  matrix.csv / summary.txt — per (model × scenario) mean/std/n cosines"
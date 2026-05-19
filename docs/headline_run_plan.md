# Headline-run launch plan

**Status:** DRAFT — pending budget approval
**Author:** generated 2026-05-02
**Target completion:** before paper submission deadline (1 week)

## Goal

Replace `leaderboard_pilot_v3` (30-scenario stratified pilot) with a full-scale headline run:
- 600 scenarios from the templated split (`evals/scenarios_generated.yaml`)
- 3 repeats per scenario per cell
- All 18 (model × strategy) cells, with two `geminiflash` cells documented as deployment-blocked

The full run is what `tab:headline`, the Pareto frontier, the heatmap, and the §6 findings will report on at submission.

## Cell matrix (18 cells, 16 effective)

| Model | Strategies | Notes |
|---|---|---|
| `anthropic:claude-opus-4-7` | raw_code, structured, recipe | Structured cell rate-limit-capped at ~12/30 in pilot; expect ~24/600 effective at quota tier |
| `anthropic:claude-sonnet-4-6` | raw_code, structured, recipe | All three cells unblocked |
| `anthropic:claude-haiku-4-5-20251001` | raw_code, structured, recipe | All three cells unblocked, fastest tier |
| `openai-responses:gpt-5.1` | raw_code, structured, recipe | All three cells unblocked |
| `google-gla:gemini-2.5-pro` | raw_code, structured, recipe | All three cells unblocked but slow (132 s/scen on structured) |
| `google-gla:gemini-2.5-flash` | raw_code only | structured + recipe blocked at API layer (§6.8) |

## Cost estimate (1800 runs per cell = 600 × 3)

Per-cell cost = $/scen (from `tab:headline`) × 1800. Conservative — assumes pilot cost/scen carries to 600-scenario draw with no token-count drift on harder templates.

| Cell | $/scen (pilot) | Cost (1800 runs) |
|---|---|---|
| Opus + raw_code | 0.329 | $592 |
| Opus + structured (capped at ~24) | 0.533 | ~$13 |
| Opus + recipe | (no pilot data; ~Sonnet × 5 = ~$0.30 est.) | ~$540 |
| Sonnet + raw_code | 0.047 | $85 |
| Sonnet + structured | 0.075 | $135 |
| Sonnet + recipe | 0.059 | $106 |
| Haiku + raw_code | 0.017 | $31 |
| Haiku + structured | 0.032 | $58 |
| Haiku + recipe | 0.022 | $40 |
| GPT-5.1 + raw_code | 0.062 | $112 |
| GPT-5.1 + structured | 0.057 | $103 |
| GPT-5.1 + recipe | 0.056 | $101 |
| Gemini Pro + raw_code | 0.040 | $72 |
| Gemini Pro + structured | 0.033 | $59 |
| Gemini Pro + recipe | 0.031 | $56 |
| Gemini Flash + raw_code | 0.009 | $16 |
| **Subtotal (all cells)** | | **~$2,120** |
| **Subtotal excluding Opus + recipe (no pilot data)** | | **~$1,580** |
| **Subtotal excluding Opus entirely** | | **~$975** |

The brief estimated $50–200, which only matches if Opus is excluded *and* we run cheap-tier cells only. **Recommendation: present the user three budget tiers** (full, no-Opus-recipe, no-Opus-at-all) and let them pick.

## Wall-clock estimate

Latency dominated by Gemini Pro + structured (132 s/scen). With concurrency=8 (matches pilot defaults):

| Bottleneck cell | Latency (s/scen) | Wall-clock (1800/8) |
|---|---|---|
| Gemini Pro + structured | 132 | 8.25 hr |
| Gemini Flash + raw_code | 99.7 | 6.23 hr |
| Gemini Pro + raw_code | 32.6 | 2.04 hr |
| Gemini Pro + recipe | 25.0 | 1.56 hr |
| Opus + raw_code | 18.0 | 1.13 hr |
| Sonnet + raw_code | 17.1 | 1.07 hr |
| GPT-5.1 + raw_code | 11.3 | 0.71 hr |
| Opus + structured | 10.0 | 0.63 hr (effectively rate-limited) |
| All others | < 10 | < 0.6 hr |

Cells run in parallel (different API providers), so total wall-clock ≈ slowest cell ≈ **~9 hours** for a single concurrency=8 attempt. Multiplied by 3 repeats it's still ≈ 9 h if all repeats run in the same launch (each repeat just adds scenarios to the same cell's queue), or 3× wall-clock if launched serially per repeat.

**Risk: Opus + structured.** Anthropic silent throttling makes wall-clock unpredictable. Pilot v4 stalled at 9/30 (concurrency=2) and 12/30 (concurrency=1) for >30 min. **Mitigation:** launch this cell separately at concurrency=1 with a max-time budget; document as N≪600 in `tab:headline` if it doesn't complete.

## Pre-flight checklist

- [ ] All API keys valid in `.env` (Anthropic, OpenAI, Google) — note: brief flags Gemini key as not-yet-rotated; rotate before launch.
- [ ] Renderer container running (`docker run -p 8001:8001 tikz-renderer`)
- [ ] Verifier hardening passes (1, 2, 3) all in main; centroid eval-side + IR-side both committed (this session)
- [ ] `evals/scenarios_generated.yaml` is up to date (regenerate from source if needed)
- [ ] Disk space: pilot was ~50 MB per repeat × 18 cells × 3 repeats × (600/30 = 20×) = ~54 GB. Verify free space.
- [ ] Quota check: hit Anthropic/OpenAI/Google dashboards before launch; bump tiers if at default.

## Launch sequence

Suggested ordering (cheap and fast first, so signal arrives early; expensive/slow cells in parallel after):

```bash
# Wave 1: fast + cheap (≤ 1 hr each, total budget ~$300)
for STRAT in raw_code structured recipe; do
  for MODEL in anthropic:claude-haiku-4-5-20251001 openai-responses:gpt-5.1 anthropic:claude-sonnet-4-6; do
    uv run python -m evals.run \
      --scenarios evals/scenarios_generated.yaml \
      --strategies $STRAT \
      --model $MODEL \
      --repeats 3 \
      --max-concurrency 8 \
      --output evals/results/headline_run \
      --no-llm-judge
  done
done

# Wave 2: Gemini (slow but cheap; can run overnight)
for STRAT in raw_code structured recipe; do
  uv run python -m evals.run \
    --scenarios evals/scenarios_generated.yaml \
    --strategies $STRAT \
    --model google-gla:gemini-2.5-pro \
    --repeats 3 \
    --max-concurrency 4 \
    --output evals/results/headline_run \
    --no-llm-judge
done
uv run python -m evals.run \
  --scenarios evals/scenarios_generated.yaml \
  --strategies raw_code \
  --model google-gla:gemini-2.5-flash \
  --repeats 3 \
  --max-concurrency 4 \
  --output evals/results/headline_run \
  --no-llm-judge

# Wave 3: Opus (expensive; explicit budget gate)
uv run python -m evals.run \
  --scenarios evals/scenarios_generated.yaml \
  --strategies raw_code,recipe \
  --model anthropic:claude-opus-4-7 \
  --repeats 3 \
  --max-concurrency 4 \
  --output evals/results/headline_run \
  --no-llm-judge

# Opus + structured: run last, separately, with a hard time budget
timeout 4h uv run python -m evals.run \
  --scenarios evals/scenarios_generated.yaml \
  --strategies structured \
  --model anthropic:claude-opus-4-7 \
  --repeats 1 \
  --max-concurrency 1 \
  --output evals/results/headline_run \
  --no-llm-judge
# repeat 2 and 3 only if repeat 1 completes; otherwise document as N≪600.
```

`--no-llm-judge` keeps cost down (judge pass can be added later via `evals/regrade.py` if needed; primary signal is the tikz_checks gate verdict).

## Post-run analysis

```bash
# Aggregate to a single leaderboard report
uv run python evals/leaderboard_analyze.py \
  --input-dir evals/results/headline_run \
  --output-md HEADLINE_REPORT.md \
  --output-csv headline.csv

# Refresh paper figures from the new run
PILOT_DIR=$REPO_ROOT/evals/results/headline_run \
  bash paper/scripts/refresh_figures.sh
```

## What to monitor during the run

- **Token-rate spikes:** flag if any model's avg `input_tokens` per scenario exceeds 1.5× pilot baseline (suggests harder-template token drift; budget may slip).
- **`gate_status` distribution shift:** if the strict-pass rate on a cell shifts by >10pp from pilot, sample 5 records and inspect manually before trusting the new number.
- **`duration_s` outliers:** Gemini Pro structured > 200 s/scen suggests rate-limit; cut and document.
- **Disk pressure:** pilot ~3 MB per record; 600×3×18 ≈ 100 GB worst case. `du -sh evals/results/headline_run` periodically.

## Decisions deferred to user

1. Budget tier (full / no-Opus-recipe / no-Opus). Default recommendation: **no-Opus-recipe** (≈$1,580) — Opus + recipe was not in the pilot, so we have no evidence it adds Pareto signal; skipping saves ~$540.
2. Whether to also rerun on `bench_curriculum.yaml` (201 scenarios, mostly LLM-extracted). Currently the paper reports both splits but the curriculum was only run during one earlier pilot. Adds ~$700 at full scope.
3. LLM-judge: leave off for cost (default). Re-add post-hoc via `evals/regrade.py` only if a reviewer pushes back on the verifier-only verdicts.
4. **Opus structured**: accept N≪600 as a deployment finding (pilot precedent), or push for a higher Anthropic quota tier first?

## When to launch

Soonest after this plan is approved. The full run wall-clock is ≈ 9 h dominated by Gemini Pro structured; an overnight launch returns results before next morning's paper-writing block. If launched 2026-05-03 (Sunday) evening, results arrive Monday morning, leaving 3 working days before paper submission for figure refresh + §6.7 case-study writing on the new data.

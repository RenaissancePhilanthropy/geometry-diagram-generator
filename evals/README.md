# evals/

Benchmark harness for the generation strategies. The commands you will use most are in the top-level [README](../README.md#development); this file is the map of what lives here.

## Quick runs

```bash
# Fast regression check, no renderer container needed
uv run python -m evals.run --scenarios evals/scenarios_smoke.yaml --strategies recipe \
  --model anthropic:claude-sonnet-4-6 --renderer svg --output evals/results

# Compare two result files (flags regressions)
uv run python -m evals.compare --baseline evals/results/<old>.jsonl evals/results/<new>.jsonl
```

`--scenarios` defaults to `scenarios_core.yaml`; `--renderer` defaults to `tikz` (needs the container on :8001), so pass `--renderer svg` to run without it. Results are appended as JSONL under `--output` (gitignored); every record carries the gate verdict (`gate_status`, `gate_failures`), token counts, latency and pipeline `warnings`. Run `python -m evals.run --help` for the full flag list.

## Scenario sets

| File | What it is |
|---|---|
| `scenarios_smoke.yaml` | A handful of scenarios for quick regressions |
| `scenarios_core.yaml` | The curated default benchmark |
| `scenarios.yaml` | Combined tiered set (Basic / Intermediate / Advanced) |
| `scenarios_generalization.yaml` | Tier 3: combining recipes and novel constructions no single recipe covers |
| `scenarios_stress.yaml` | Broader, harder coverage |
| `scenarios_query.yaml` | Render, then answer follow-up questions through `query_diagram` |
| `scenarios_solids.yaml` | Rectangular prisms and block stacks; skipped unless run with `--features solids` |
| `scenarios_pilot.yaml`, `scenarios_pilot_t3.yaml` | Pilot sets behind the leaderboard and paper results |
| `scenarios_geometry_curriculum.yaml` | Prompts derived from textbook curriculum structure (see [`curriculum/`](../curriculum/README.md)) |
| `scenarios_generated.yaml` | Template-generated scenarios (`generate_scenarios.py`; exports in `scenarios_generated_exports/`) |
| `scenarios_editing_chains.yaml` | Multi-turn edit chains, a different schema from the rest (see below) |
| `scenarios_locality_judgment.yaml` | Fixture bank for `eval_locality_retry_judgment.py` |

Scenario fields (gates, property checks, `requires_features`, `fail_on_warnings`, `forbidden_labels`) are validated by `scenarios.py`; the semantics are described under "Evals" in [CLAUDE.md](../CLAUDE.md).

## Scripts

| Script | Purpose |
|---|---|
| `run.py` | Main runner: scenarios x strategies x repeats |
| `compare.py` | Diff results across runs |
| `regrade.py` | Re-grade stored records against the current verifier, without regenerating |
| `sample_scenarios.py` | Deterministic stratified sample from a scenarios YAML |
| `generate_scenarios.py` | Build `scenarios_generated.yaml` from templates (see [docs/templated-scenarios.md](../docs/templated-scenarios.md)) |
| `ir_diagnostics.py` | Static analysis of a `DiagramIR` to classify failure modes |
| `sympy_checks.py` | SymPy-based property validation used by the gate |
| `reporting.py` | Result formatting and JSONL I/O |
| `leaderboard_launch.sh`, `leaderboard_analyze.py`, `leaderboard_plot.py` | Run, tabulate and plot the model x strategy leaderboard ([docs/headline_run_plan.md](../docs/headline_run_plan.md)) |
| `run_edit_chains.py`, `edit_chain_metrics.py`, `scenarios_editing_chains.py` | Multi-turn pydsl edit-chain reliability eval |
| `eval_locality_retry_judgment.py` | Isolated eval of the locality-violation retry's judgment call |
| `eval_viewer.py` | Backend for browsing and re-rendering results (frontend in [`eval-viewer-ui/`](../eval-viewer-ui)) |
| `human_study/` | Rating study for the paper; see its [README](human_study/README.md) |

## Cost and concurrency

Each concurrent `evals.run` process pays a sandbox cold-start for python_full scripts, so keep the number of simultaneous runs at or below the core count.

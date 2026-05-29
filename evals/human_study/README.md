# Human-correlation rating study — quick start

You're rating ~200 (prompt, diagram) pairs for the GeoGenBench paper. Each item is one model's attempt at a geometry prompt; the auto-verifier already scored it `pass` / `soft_pass` / `fail`. Your job: judge whether you agree.

The full pre-registered protocol is in [`docs/human_study_protocol.md`](../../docs/human_study_protocol.md). This file is just the runbook.

---

## 1. One-time setup

From the repo root:

```bash
# Install dependencies (only needed once, or after a pull)
uv sync

# Verify the env activates
source .venv/bin/activate
python -c "import csv, http.server; print('ok')"
```

No Docker is needed for rating. (Docker is only for *generating* new diagrams; the SVGs you'll rate are already on disk.)

---

## 2. Pick your rater name

Coordinate with your partner so you don't both pick the same name:

- **`rater_a`** — first rater
- **`rater_b`** — second rater

The analysis script (`compute_kappa.py`) defaults to these two names. If you use other names, pass `--raters <your-name>,<partner-name>` when running it.

---

## 3. Start the rating server

```bash
# From the repo root
.venv/bin/python -m evals.human_study.serve --rater rater_b
```

What happens:

- A local web server starts on `http://localhost:8765`.
- Your default browser auto-opens the viewer at `http://localhost:8765/evals/human_study/viewer.html?rater=rater_b`.
- The terminal prints the URL — share-able if you ever want to open it on another browser tab.

If port 8765 is in use, pass `--port 8766` (or any free port).

---

## 4. Rate

The viewer guides you. The short version:

- **Q1 (overall verdict)** — blind. You see only the prompt and diagram. Click `Yes` / `Partial` / `No`.
- **Q2 (per-property)** — unlocks after Q1. For each predicate the verifier checked, click `Agree` / `Disagree` / `Unsure` against the auto-verdict shown.
- **Notes** — optional. Use for disagreement reasoning or edge cases (helps the consensus discussion later).

### Keyboard shortcuts (much faster than mouse)

| | |
|---|---|
| Q1 — Yes / Partial / No | <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> |
| Q2 — Agree / Disagree / Unsure (next unanswered predicate) | <kbd>a</kbd> <kbd>d</kbd> <kbd>u</kbd> |
| Navigate | <kbd>←</kbd> <kbd>→</kbd> |
| Show keyboard help | <kbd>?</kbd> |

Press `?` in the viewer any time to recall this list.

### Workload

- 200 items, ~2–4 min each → roughly **7–13 hours** total per rater. Spread it across sessions; the tool resumes where you left off.
- Aim to finish independently before meeting for consensus.

---

## 5. Where your answers go

Every Q1 / Q2 click and every keystroke in the notes field auto-saves (~350ms debounce) to:

```
evals/human_study/responses_<your-rater-name>.csv
```

For `rater_b` that's `evals/human_study/responses_rater_b.csv`.

The save indicator at the top-right of the viewer turns:

- **Green `saved · N rows`** — last save succeeded
- **Orange `saving…`** — write in flight
- **Red `save failed`** — server unreachable; check the terminal where you ran `serve.py`

Live-watch progress in another terminal:

```bash
watch -n 1 'wc -l evals/human_study/responses_rater_b.csv'
```

---

## 6. Stop and resume

Stop: close the browser tab, then `Ctrl+C` in the terminal running the server. **Your progress is on disk — nothing is lost.**

Resume: re-run the same `serve.py` command (same `--rater` flag). The viewer loads your saved responses and lands on the first item you haven't answered.

---

## 7. When you're done

Independent annotation is complete when the header counts read **`0 left`**. Then:

1. Tell your co-rater. They should also be at `0 left`.
2. Run the analysis script (either of you):
   ```bash
   .venv/bin/python -m evals.human_study.compute_kappa
   ```
   Output: `evals/human_study/results.json`. This computes Cohen's κ between you and your partner (inter-rater reliability) before consensus.
3. Schedule the **consensus discussion** (≤90 min). Walk through every item where Q1 or Q2 differ; agree on a single label. Save consensus labels as `responses_consensus.csv` (use the viewer with `--rater consensus`).
4. Re-run `compute_kappa.py`. Final output is the primary κ(auto-verdict, human-consensus) reported in the paper's Appendix E.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Port already in use | Pass `--port <number>` to `serve.py` |
| SVG fails to load in viewer | Make sure you started `serve.py` from the **repo root**, not from `evals/human_study/` |
| Save indicator stuck on red | Server crashed — check the terminal, restart `serve.py`, refresh the browser |
| Browser shows old version of the viewer | Hard-refresh: <kbd>Cmd+Shift+R</kbd> (macOS) / <kbd>Ctrl+Shift+R</kbd> (Linux/Windows) |
| Keyboard shortcuts not working | The notes textarea captures keys — click outside it first |

If anything else seems broken, ping your co-rater (likely root cause: the viewer was just edited).

---

## File reference (for the curious)

- `viewer.html` — the rating UI (single-page app, no build step)
- `serve.py` — local HTTP server that hosts the viewer and writes the CSV
- `sample.json` — the frozen 200-item sample (deterministic, seed=42)
- `sample_human_study.py` — regenerates `sample.json` from canonical pilot data (you should not need to run this)
- `compute_kappa.py` — post-annotation analysis: Cohen's κ, bootstrap CIs, subgroups
- `responses_<rater>.csv` — per-rater output (auto-written by `serve.py`)

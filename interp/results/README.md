# interp/results — small experiment artifacts, tracked in git

Written by `interp/save_off_box.sh` (Tier A) before a GPU box is destroyed. One
subdirectory per capture run (`mtx_<model>_<task>`, `<model>_temporal`, `fix_*`, …)
holding that run's `meta.jsonl` (one line per record: grade, stated confidences,
P(True)/logprobs where captured, token positions) plus any analysis outputs, and a
`_manifest.json` recording how many `.npz` activation files the run had and where it
was saved from. Top-level files are the cross-run analysis caches
(`plot_cache.json`, `tier1_review.json`, `temporal_analysis.json`).

The `.npz` activations themselves are NOT here (gigabytes): Tier B of the same script
uploads them to `$RCLONE_REMOTE` / `$RSYNC_DEST`. To rerun probes or
`analysis/tier1_review.py`, restore a run dir by copying its npz files back next to
its `meta.jsonl` under `interp/activations/<run>/`.

Runs recorded here so far: `transfer_q15/{recipe,tikz,svg,english}` (Qwen2.5-1.5B reading-mode
pilot; npz still on Mei's laptop, ~950 MB). The July 2026 matrix (`mtx_*`, `*_temporal`,
`plot_cache.json`, `tier1_review.json`) was lost with its box — nothing to record.

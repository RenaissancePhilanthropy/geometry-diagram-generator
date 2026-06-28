# interp analysis scripts (offline, run from repo root with the interp venv)
# consistency.py    — semantic self-consistency (relation-type vocab Jaccard) across temp samples
# ordering.py       — coarse-to-fine onset depth per concept (multi-seed)
# coherent_map.py   — does decoded point set preserve figure shape (distance-matrix corr vs null)
# map_by_layer.py   — coherent-map / decodability by layer depth
# NOTE: hardcode interp/activations/big30; PCA(100) uncapped. Re-run AFTER the
# prompt-level grouping fix in probe.py (build_xy groups by base prompt).

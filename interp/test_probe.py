"""
Offline smoke test for the Phase-2 probe pipeline — synthetic data, no model/GPU.

Fabricates a capture run where the relation class is linearly encoded at layer 2
and pure noise at layer 0, writes it in capture.py's on-disk format, then checks
run_probe recovers it: high accuracy at the planted layer, ~chance at the noise
layer. This exercises load -> label -> per-layer train end to end.

    interp/.venv/bin/python interp/test_probe.py
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCRATCH = pathlib.Path(
    "/private/tmp/claude-501/-Users-mlc-Code-carnegie-geometry-diagram-generator/"
    "39b88f47-b744-493b-bcce-30147445d282/scratchpad/probe_synth"
)

# token text -> planted class (matches probe.label_relation keywords)
CLASS_TOKENS = {"perp": "perpendicular", "parallel": "parallel", "mid": "midpoint"}


def _make_synthetic(act_dir: pathlib.Path, n_prompts=40, D=16, seed=0):
    import numpy as np

    act_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    L = 3  # 3 layers: 0 = noise, 2 = signal
    class_dirs = {c: rng.normal(size=D) * 3 for c in set(CLASS_TOKENS.values())}
    kws = list(CLASS_TOKENS)

    with (act_dir / "meta.jsonl").open("w") as meta_f:
        for p in range(n_prompts):
            tokens, acts_layers = [], np.zeros((L, 0, D))
            cols = []
            for j in range(6):  # 6 tokens/prompt, ~half are relation tokens
                if j % 2 == 0:
                    kw = kws[(p + j) % len(kws)]
                    tokens.append(kw)
                    cls = CLASS_TOKENS[kw]
                    vec0 = rng.normal(size=D)                       # layer 0: noise
                    vec2 = class_dirs[cls] + rng.normal(size=D) * 0.5  # layer 2: signal
                else:
                    tokens.append("xyz")                            # non-relation
                    vec0 = rng.normal(size=D)
                    vec2 = rng.normal(size=D)
                cols.append((vec0, rng.normal(size=D), vec2))       # layer 1 = noise too
            P = len(tokens)
            acts = np.zeros((L, P, D), dtype=np.float16)
            for pos, (v0, v1, v2) in enumerate(cols):
                acts[0, pos], acts[1, pos], acts[2, pos] = v0, v1, v2
            pid = f"synth_{p}"
            np.savez_compressed(act_dir / f"{pid}.npz", acts=acts,
                                layer_ids=np.array([0, 1, 2]),
                                offsets=np.zeros((P, 2), dtype=int))
            meta_f.write(json.dumps({"pid": pid, "tokens": tokens,
                                     "prompt": "", "completion": ""}) + "\n")


def test_probe_recovers_planted_signal():
    from interp.probe import run_probe

    _make_synthetic(SCRATCH)
    out = run_probe(SCRATCH, "relation", test_frac=0.3, seed=0)
    curve = {c["layer"]: c["acc"] for c in out["curve"]}
    assert set(curve) == {0, 1, 2}, curve
    # planted layer 2 should be strongly decodable; noise layers near baseline
    assert curve[2] > 0.85, f"signal layer too low: {curve}"
    assert curve[2] > curve[0] + 0.3, f"signal not above noise: {curve}"
    print(f"\nok  probe recovered signal: layer accs {curve}")


if __name__ == "__main__":
    test_probe_recovers_planted_signal()
    print("\nPROBE SMOKE TEST PASSED")

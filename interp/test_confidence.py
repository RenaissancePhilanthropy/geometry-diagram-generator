"""
Offline tests for confidence elicitation + the fixed-slot metacognition read
(interp/confidence.py, probe.label_correctness_conf, verbalized_vs_internal).
No model / GPU — synthetic captures in the on-disk format.

    interp/.venv/bin/python interp/test_confidence.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCRATCH = pathlib.Path(tempfile.gettempdir()) / "geo_interp_conf_test"
COMPLETION_TMPL = '[{{"id":"M"}},{{"id":"L"}}] Confidence: {v}'


def test_parse_confidence():
    from interp.confidence import parse_confidence
    assert parse_confidence("...\nConfidence: 73") == 73
    assert parse_confidence("confidence = 5 done") == 5
    assert parse_confidence("Confidence: 250") == 100                 # clamped
    assert parse_confidence("no number here") is None
    assert parse_confidence("Confidence: 10 ... Confidence: 88") == 88  # last wins
    print("ok  parse_confidence")


def test_confidence_positions():
    from interp.confidence import confidence_positions
    comp = COMPLETION_TMPL.format(v=73)
    offs = [[i, i + 1] for i in range(len(comp))]                     # one token per char
    pos = confidence_positions(comp, offs)
    assert [comp[offs[p][0]] for p in pos] == ["7", "3"], (pos, comp)
    assert confidence_positions("no conf here", offs) == []
    print("ok  confidence_positions maps to the digit tokens")


def test_confidence_read_positions():
    from interp.confidence import confidence_read_positions
    comp = COMPLETION_TMPL.format(v=73)
    offs = [[i, i + 1] for i in range(len(comp))]                     # one token per char
    dpos, digits = confidence_read_positions(comp, offs)
    assert [comp[offs[p][0]] for p in digits] == ["7", "3"], (digits, comp)
    assert dpos == min(digits) - 1                                   # token before number
    assert comp[offs[dpos][0]] == " ", repr(comp[offs[dpos][0]])     # the space after ':'
    assert confidence_read_positions("no conf", offs) == (None, [])
    print("ok  confidence_read_positions: decision = the token that generates the number")


def test_add_confidence_request():
    from interp.confidence import CONFIDENCE_INSTRUCTION, add_confidence_request
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "draw X"}]
    out = add_confidence_request(msgs)
    assert out[-1]["content"].endswith(CONFIDENCE_INSTRUCTION)
    assert msgs[1]["content"] == "draw X"                            # original untouched
    print("ok  add_confidence_request appends to the user turn")


def test_read_pos_excludes_conf():
    from interp.confidence import confidence_read_positions
    from interp.probe import (label_correctness, label_correctness_conf,
                              label_correctness_conf_digit)
    comp = COMPLETION_TMPL.format(v=73)
    offs = [[i, i + 1] for i in range(len(comp))]
    dpos, digits = confidence_read_positions(comp, offs)
    pos_M, pos_L = comp.index('"M"') + 1, comp.index('"L"') + 1
    stored = sorted({pos_M, pos_L, dpos, *digits})
    rec = {"pos_map": {p: i for i, p in enumerate(stored)}, "tokens": list(comp),
           "meta": {"grade": {"ok": True}, "conf_positions": digits,
                    "conf_decision_pos": dpos}}
    assert list(label_correctness(rec)) == [pos_L], label_correctness(rec)   # skips conf+decision
    assert list(label_correctness_conf(rec)) == [dpos]                        # decision site
    assert list(label_correctness_conf_digit(rec)) == [max(digits)]           # digit site
    print("ok  entity read skips conf+decision; conf read=decision, digit read=digit")


def _make_conf_capture(act_dir: pathlib.Path, n=48, D=16, seed=7):
    """Synthetic --elicit-confidence capture: grade is linearly encoded at layer 2 at
    the confidence DECISION token; stated conf_value tracks the grade; layer 0 = noise."""
    import numpy as np

    from interp.confidence import confidence_read_positions
    act_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    L = 3
    dir_ok, dir_fail = rng.normal(size=D) * 3, rng.normal(size=D) * 3
    with (act_dir / "meta.jsonl").open("w") as mf:
        for k in range(n):
            ok = (k % 2 == 0)
            val = int(rng.integers(70, 96)) if ok else int(rng.integers(5, 36))
            comp = COMPLETION_TMPL.format(v=val)
            offs = [[i, i + 1] for i in range(len(comp))]
            dpos, digits = confidence_read_positions(comp, offs)
            pos_M, pos_L = comp.index('"M"') + 1, comp.index('"L"') + 1
            stored = sorted({pos_M, pos_L, dpos, *digits})
            dec_slot = stored.index(dpos)                 # decision token = read site
            acts = rng.normal(size=(L, len(stored), D)).astype(np.float16)
            acts[2, dec_slot] = (dir_ok if ok else dir_fail) + rng.normal(size=D) * 0.5
            pid = f"cf_{k}"
            np.savez_compressed(act_dir / f"{pid}.npz", acts=acts,
                                layer_ids=np.array([0, 1, 2]),
                                offsets=np.array(offs), positions=np.array(stored))
            mf.write(json.dumps({
                "pid": pid, "tokens": list(comp), "completion": comp,
                "grade": {"ok": ok, "stage": "success" if ok else "compile", "n_ops": 5},
                "conf_value": val, "conf_positions": digits, "conf_decision_pos": dpos,
                "ground_truth": {"entity_relations": {"M": "midpoint", "L": "perpendicular"}},
            }) + "\n")


def test_correctness_conf_probe():
    from interp.probe import run_probe
    _make_conf_capture(SCRATCH)
    out = run_probe(SCRATCH, "correctness_conf", test_frac=0.3, seed=0)
    curve = {c["layer"]: c["score"] for c in out["curve"]}
    assert curve.get(2, 0) > 0.85, curve
    assert curve[2] > curve[0] + 0.3, curve
    print(f"ok  correctness_conf recovers grade at the fixed slot: {curve}")


def test_verbalized_vs_internal():
    from interp.analysis.verbalized_vs_internal import run
    d = SCRATCH.parent / "geo_interp_conf_test_v"
    _make_conf_capture(d)
    res = run(d)
    assert res["verbalized_auroc"] > 0.8, res            # stated number tracks grade
    assert res["internal_best"] and res["internal_best"][1] > 0.8, res
    print(f"ok  verbalized_vs_internal runs end to end: {res}")


if __name__ == "__main__":
    test_parse_confidence()
    test_confidence_positions()
    test_confidence_read_positions()
    test_add_confidence_request()
    test_read_pos_excludes_conf()
    test_correctness_conf_probe()
    test_verbalized_vs_internal()
    print("\nCONFIDENCE TESTS PASSED")

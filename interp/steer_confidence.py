"""
Tier-3 causal test (RQ8+): does the model USE its internal correctness direction when
STATING its post-task confidence — and can amplifying that internal signal close the
knowing-vs-saying gap?

Steering is applied ONLY during turn-3 (the post-confidence turn), so the answer itself
is untouched by construction — the answer-invariance control is built in. Two modes:

  add      h -> h + coeff * w_raw            uniform dose-response: pushing along the
           ok-minus-fail direction should move the STATED confidence up (+) / down (-).
           Establishes causal USE. Control: random direction of equal norm.
  amplify  h -> h + (coeff-1) * ((h·ŵ) - mu) * ŵ
           coeff 0 is MEAN ABLATION: every record is moved to the mean projection mu, so the
           direction still exists but carries no per-record information. Note |coeff-1| is the
           perturbation size, so coeff 0 is exactly as large as coeff 2 (opposite sign) -- a
           magnitude the model is known to tolerate (parse rate 1.0). Read the result as the
           stated-confidence AUROC collapsing toward chance, NOT as the level dropping; a
           generally damaged model produces worse text, it does not selectively lose the
           ability to rank its own failures below its own successes.
           per-record gain on the model's OWN component along the direction — uses NO
           labels at steering time. The gap-closing demo: if verbalized calibration
           (AUROC/ECE vs the external grade) improves at gain > 1, the model can be
           made to SAY what it internally knows.

Direction w = diff-of-means (ok - fail) of the captured post_dtoken activations at the
steer layer, fit on half the base prompts (grouped split); steering/eval on the other
half. Needs a fix_* cell captured with full meta texts (prompt / pre_completion /
answer — stored by capture_qa as of the Tier-3 prep commit).

Readouts per (mode, coeff, direction):
  parse rate, mean stated confidence by ok/fail, AUROC + ECE of stated confidence vs
  grade, and a teacher-forced logP(hi)-logP(lo) at the decision slot (dynamic-range-
  robust even under mode collapse).

    python interp/steer_confidence.py --act-dir interp/activations/fix_qwen36_math \
        --model Qwen/Qwen3.6-27B --task math --device cuda --per-turn-think \
        --mode amplify --coeffs 0.5,1,2,4 --n-eval 150
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _num_hidden_layers(model) -> int:
    c = model.config
    n = getattr(c, "num_hidden_layers", None)
    if n is None and hasattr(c, "get_text_config"):
        n = c.get_text_config().num_hidden_layers
    if n is None and hasattr(c, "text_config"):
        n = c.text_config.num_hidden_layers
    return int(n)


def _blocks(model, n_layers):
    """Arch-agnostic decoder-block list: the ModuleList whose length equals the layer
    count (works for dense / MoE / hybrid-Mamba / VLM-wrapped text towers)."""
    import torch.nn as nn
    cands = [m for _, m in model.named_modules()
             if isinstance(m, nn.ModuleList) and len(m) == n_layers]
    if not cands:
        raise SystemExit(f"no ModuleList of length {n_layers} found — inspect the arch")
    return cands[0]


def _auroc(scores, y):
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y)
    if len(set(y.tolist())) < 2:
        return float("nan")
    return float(roc_auc_score(y, scores))


def _ece(conf01, y, bins=10):
    conf01 = np.asarray(conf01, float); y = np.asarray(y, float)
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf01 >= lo) & (conf01 < hi if hi < 1 else conf01 <= hi)
        if m.sum():
            e += m.sum() / len(y) * abs(y[m].mean() - conf01[m].mean())
    return float(e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", required=True, help="a fix_* cell with full-text meta")
    ap.add_argument("--dir-act-dir", default=None,
                    help="fit the steering direction from THIS cell instead of --act-dir's fit half "
                         "(specificity control: a direction learned where surface features cannot "
                         "explain it, e.g. mmlu_pro, applied to a cell where they partly can, e.g. math). "
                         "With this set, every record of --act-dir is available for evaluation.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quant", choices=("none", "4bit", "awq"), default="none")
    ap.add_argument("--layer", default="fix",
                    help="acts (hidden-state) layer index, or 'fix' = 0.7 * depth")
    ap.add_argument("--mode", choices=("add", "amplify"), default="add",
                    help="amplify at coeff 0 REMOVES the component (ablation): sweep 0 to test whether stated confidence still tracks correctness without the direction")
    ap.add_argument("--coeffs", default=None,
                    help="add: multiples of the raw diff-of-means (default -16..16); "
                         "amplify: gains (default 0.5,1,2,4)")
    ap.add_argument("--n-eval", type=int, default=100)
    ap.add_argument("--skip-random", action="store_true", help="skip the random-direction control")
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--per-turn-think", action="store_true")
    ap.add_argument("--high", default="95")
    ap.add_argument("--low", default="20")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    coeffs = [float(c) for c in
              (args.coeffs or {"add": "-16,-8,-4,0,4,8,16", "amplify": "0.5,1,2,4"}[args.mode]
               ).split(",")]

    import torch
    from interp.capability_check import load_model
    from interp.confidence import parse_confidence
    from interp.tasks_qa import QA_TASKS, QA_PRETASK_QUERY, QA_POSTTASK_QUERY

    task = QA_TASKS[args.task]
    pre_q = task.get("pretask_query", QA_PRETASK_QUERY)
    post_q = task.get("posttask_query", QA_POSTTASK_QUERY)
    if args.per_turn_think:
        answer_think, conf_think = True, False
    elif args.no_think:
        answer_think, conf_think = False, False
    else:
        answer_think, conf_think = None, None

    d = pathlib.Path(args.act_dir)
    recs = [json.loads(l) for l in (d / "meta.jsonl").read_text().splitlines()]
    recs = [r for r in recs if r.get("pre_completion") is not None
            and (d / f"{r['pid']}.npz").exists()]
    if not recs:
        raise SystemExit("no records with full meta texts — capture with the Tier-3-prep "
                         "capture_qa (stores pre_completion + untruncated prompt/answer)")
    base = lambda pid: re.sub(r"_s\d+$", "", pid)
    groups = sorted({base(r["pid"]) for r in recs})
    rng = np.random.default_rng(args.seed)
    rng.shuffle(groups)
    if args.dir_act_dir:                           # direction comes from elsewhere:
        fit = []                                   # nothing to hold back, evaluate on everything
        ev = list(recs)[: args.n_eval]
    else:
        fit_g = set(groups[: len(groups) // 2])
        fit = [r for r in recs if base(r["pid"]) in fit_g]
        ev = [r for r in recs if base(r["pid"]) not in fit_g][: args.n_eval]

    tok, model = load_model(args.model, args.device, args.quant)
    model.eval()
    n_layers = _num_hidden_layers(model)
    Lacts = int(round(0.7 * n_layers)) if args.layer == "fix" else int(args.layer)
    blocks = _blocks(model, n_layers)
    block = blocks[Lacts - 1]                      # hidden_states[L] = output of block L-1
    _tmpl = tok
    if getattr(tok, "chat_template", None) is None:
        from transformers import AutoProcessor
        _tmpl = AutoProcessor.from_pretrained(args.model)

    # ---- direction: from the FIT half, or from a different cell entirely --------
    dir_d = pathlib.Path(args.dir_act_dir) if args.dir_act_dir else d
    if args.dir_act_dir:
        dir_recs = [json.loads(l) for l in (dir_d / "meta.jsonl").read_text().splitlines()]
        dir_recs = [r for r in dir_recs if (dir_d / f"{r['pid']}.npz").exists()]
        print(f"direction fitted on {len(dir_recs)} records from {dir_d.name} "
              f"(evaluating {len(ev)} records from {d.name})")
    else:
        dir_recs = fit
    X, y = [], []
    for r in dir_recs:
        try:                                       # skip 0-byte resume stubs / corrupt files
            z = np.load(dir_d / f"{r['pid']}.npz")
        except (EOFError, OSError, ValueError):
            continue
        if "post_dtoken" in z:
            X.append(z["post_dtoken"][Lacts].astype(np.float32))
            y.append(1 if r["grade"]["ok"] else 0)
    degenerate = len(X) < 2 or len(set(y)) < 2
    if X:
        X, y = np.stack(X), np.array(y)
    else:                                          # tiny smoke cells: no post reads in fit half
        dim = np.load(dir_d / f"{dir_recs[0]['pid']}.npz")["prompt_dtoken"].shape[1]
        X, y = np.zeros((1, dim), np.float32), np.array([0])
    if degenerate:
        print("WARN: fit half degenerate (empty/single-class) — random direction (pipeline smoke only)")
        w_raw = rng.standard_normal(X.shape[1]).astype(np.float32)
    else:
        w_raw = X[y == 1].mean(0) - X[y == 0].mean(0)
    w_hat = w_raw / (np.linalg.norm(w_raw) + 1e-8)
    r_raw = rng.standard_normal(X.shape[1]).astype(np.float32)
    r_raw *= np.linalg.norm(w_raw) / (np.linalg.norm(r_raw) + 1e-8)
    r_hat = r_raw / (np.linalg.norm(r_raw) + 1e-8)

    # The centering constant mu must describe the population being STEERED, not the one the
    # direction was learned from. Same-cell: the fit half is the same distribution as the eval
    # half, so its mean is fine. Foreign direction (--dir-act-dir): the eval cell's projections
    # can sit somewhere else entirely, and a wrong mu turns mean-ablation into ablation plus a
    # constant shift, and amplification into amplification about the wrong centre. So recompute
    # mu (and sigma, which sets the matched random scale) on the records we are about to steer.
    Xc = X
    if args.dir_act_dir:
        Xe = []
        for r in ev:
            try:
                z = np.load(d / f"{r['pid']}.npz")
            except (EOFError, OSError, ValueError):
                continue
            if "post_dtoken" in z:
                Xe.append(z["post_dtoken"][Lacts].astype(np.float32))
        if len(Xe) >= 2:
            Xc = np.stack(Xe)
            print(f"centering on {len(Xc)} eval records from {d.name} "
                  f"(direction from {dir_d.name})")
    mu = float((Xc @ w_hat).mean())
    mu_r = float((Xc @ r_hat).mean())
    # Magnitude-matched random control for AMPLIFY mode (Codex review 2026-07-15, finding 3):
    # amplify perturbs by (g-1)*|proj-mu|, and the correctness direction has a larger projection
    # spread than a random one, so an unscaled random control gets smaller nudges. Scale the
    # random perturbation by sigma_w/sigma_r so the per-record perturbation magnitudes match in
    # distribution. In ADD mode the |w|-matched r_raw already matches, so scale=1 there.
    sigma_w = float((Xc @ w_hat).std() + 1e-8)
    sigma_r = float((Xc @ r_hat).std() + 1e-8)
    rand_scale = (sigma_w / sigma_r) if args.mode == "amplify" else 1.0
    print(f"fit={len(fit)} eval={len(ev)} | layer acts={Lacts}/{n_layers} (block {Lacts-1}) | "
          f"|w|={np.linalg.norm(w_raw):.2f} median|h|={np.median(np.linalg.norm(X, axis=1)):.1f} | "
          f"sigma_w={sigma_w:.3f} sigma_r={sigma_r:.3f} rand_scale={rand_scale:.2f} | "
          f"mode={args.mode} coeffs={coeffs}")

    def render(msgs, think):
        kw = {} if think is None else {"enable_thinking": think}
        text = _tmpl.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, **kw)
        return tok(text, return_tensors="pt").input_ids

    def turn3_ids(r):
        msgs = ([{"role": "system", "content": task["system"]()}] if task["system"]() else [])
        msgs += [{"role": "user", "content": r["prompt"] + "\n\n" + pre_q},
                 {"role": "assistant", "content": r["pre_completion"]},
                 {"role": "user", "content": task["answer_query"]},
                 {"role": "assistant", "content": r["answer"]},
                 {"role": "user", "content": post_q}]
        return render(msgs, conf_think)

    # ---- steering hook: last position on prefill, every step token after ------
    state = {"vec": None, "coeff": 0.0, "mode": args.mode, "hat": None, "mu": 0.0, "scale": 1.0}

    def hook(mod, inp, out):
        h = out[0] if isinstance(out, tuple) else out
        if state["vec"] is None:
            return out
        v = state["vec"]
        if v.device != h.device:                      # sharded model: block may live on another GPU
            state["vec"] = v = v.to(h.device); state["hat"] = state["hat"].to(h.device)
        if state["mode"] == "add":
            h[:, -1, :] += state["coeff"] * v
        else:                                       # amplify along hat
            hat = state["hat"]
            proj = (h[:, -1, :] @ hat) - state["mu"]
            h[:, -1, :] += (state["coeff"] - 1.0) * state["scale"] * proj.unsqueeze(-1) * hat
        return out

    handle = block.register_forward_hook(hook)
    hi_ids = [t[0] for s in (args.high, " " + args.high)
              for t in [tok(s, add_special_tokens=False).input_ids] if t]
    lo_ids = [t[0] for s in (args.low, " " + args.low)
              for t in [tok(s, add_special_tokens=False).input_ids] if t]

    def run_record(ids, vec_np, hat_np, mu_v, coeff, scale=1.0):
        dt = model.dtype if hasattr(model, "dtype") else torch.float32
        state.update(vec=torch.tensor(vec_np, dtype=dt, device=args.device),
                     hat=torch.tensor(hat_np, dtype=dt, device=args.device),
                     mu=mu_v, coeff=coeff, scale=scale)
        if (args.mode == "add" and coeff == 0.0) or (args.mode == "amplify" and coeff == 1.0):
            state["vec"] = None                     # exact no-op baseline (hook passes through)
        ids = ids.to(args.device)
        with torch.no_grad():
            g = model.generate(ids, max_new_tokens=24, do_sample=False)
        text = tok.decode(g[0].tolist()[ids.shape[1]:], skip_special_tokens=True)
        conf = parse_confidence(text)
        # logit readout at the decision slot: same context + "Confidence: "
        forced = torch.cat([ids, tok("Confidence: ", add_special_tokens=False,
                                     return_tensors="pt").input_ids.to(args.device)], dim=1)
        with torch.no_grad():
            lp = torch.log_softmax(model(input_ids=forced).logits[0, -1, :].float(), -1)
        hi = float(torch.logsumexp(lp[hi_ids], 0)); lo = float(torch.logsumexp(lp[lo_ids], 0))
        return conf, hi - lo

    results = {}
    per_record = []   # every (direction, coeff, record) row: Brier/NLL/CIs offline
    dirs = [("steer", w_raw, w_hat, mu, 1.0)] + ([] if args.skip_random else
                                                 [("random", r_raw, r_hat, mu_r, rand_scale)])
    try:
        for dname, vec, hat, mu_v, scale in dirs:
            for c in coeffs:
                confs, ldiffs, oks = [], [], []
                for r in ev:
                    conf, ld = run_record(turn3_ids(r), vec, hat, mu_v, c, scale)
                    confs.append(conf); ldiffs.append(ld)
                    oks.append(1 if r["grade"]["ok"] else 0)
                    per_record.append({"dir": dname, "coeff": c, "pid": r["pid"],
                                       "conf": conf, "logit_diff": ld,
                                       "ok": bool(r["grade"]["ok"])})
                have = np.array([x is not None for x in confs])
                cv = np.array([x if x is not None else np.nan for x in confs], float)
                ok = np.array(oks)
                m = have & ~np.isnan(cv)
                row = {"parse_rate": float(have.mean()),
                       "mean_conf_ok": float(np.nanmean(cv[m & (ok == 1)])) if (m & (ok == 1)).any() else None,
                       "mean_conf_fail": float(np.nanmean(cv[m & (ok == 0)])) if (m & (ok == 0)).any() else None,
                       "auroc": _auroc(cv[m], ok[m]) if m.sum() > 5 else float("nan"),
                       "ece": _ece(cv[m] / 100, ok[m]) if m.sum() > 5 else float("nan"),
                       "logit_diff": float(np.mean(ldiffs))}
                results[f"{dname}@{c}"] = row
                print(f"  {dname:>6} c={c:+7.2f} | parse={row['parse_rate']:.2f} "
                      f"conf ok/fail={row['mean_conf_ok'] and round(row['mean_conf_ok'])}/"
                      f"{row['mean_conf_fail'] and round(row['mean_conf_fail'])} "
                      f"AUROC={row['auroc']:.3f} ECE={row['ece']:.3f} "
                      f"logitΔ={row['logit_diff']:+.2f}")
    finally:
        handle.remove()

    out = args.out or str(d / f"steer_{args.mode}.json")
    pathlib.Path(out).write_text(json.dumps({
        "model": args.model, "task": args.task, "mode": args.mode, "layer_acts": Lacts,
        "coeffs": coeffs, "n_eval": len(ev), "degenerate_direction": degenerate,
        "direction_from": (args.dir_act_dir or "fit half of " + str(d)),
        "random_control": {"sigma_w": sigma_w, "sigma_r": sigma_r, "rand_scale": rand_scale,
                           "magnitude_matched": True},
        "results": results, "per_record": per_record}, indent=2))
    print("saved", out)


if __name__ == "__main__":
    main()

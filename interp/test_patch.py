"""
Offline mechanics tests for the patching harness — no GPU, no weights download.
Verifies (a) minimal pairs token-align, (b) the cache+patch hooks actually
overwrite a layer's activation and change the output.

    interp/.venv/bin/python interp/test_patch.py
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.patch import _build_pair, TEMPLATES

TOKENIZER = "Qwen/Qwen2.5-7B-Instruct"   # cached locally; tokenizer only


def test_minimal_pairs_align():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(TOKENIZER)
    n_ok = 0
    for template in TEMPLATES:
        p = _build_pair(tok, template, 60, 70)
        if p is None:
            continue
        n_ok += 1
        assert len(p["clean_ids"]) == len(p["corrupt_ids"])
        # exactly one differing token, and it's the patch position
        diffs = [k for k in range(len(p["clean_ids"]))
                 if p["clean_ids"][k] != p["corrupt_ids"][k]]
        assert diffs == [p["patch_pos"]], diffs
        assert p["clean_ans"] != p["corrupt_ans"]
    assert n_ok >= 1, "no templates produced aligned pairs"
    print(f"ok  minimal pairs align ({n_ok}/{len(TEMPLATES)} templates, 60 vs 70)")


def test_patch_hook_changes_output():
    import torch
    from transformers import AutoTokenizer, Qwen2Config, Qwen2ForCausalLM
    tok = AutoTokenizer.from_pretrained(TOKENIZER)
    cfg = Qwen2Config(vocab_size=len(tok), hidden_size=64, num_hidden_layers=4,
                      num_attention_heads=4, num_key_value_heads=2,
                      intermediate_size=128, max_position_embeddings=512)
    torch.manual_seed(0)
    model = Qwen2ForCausalLM(cfg).eval()
    layers = model.model.layers

    ci = tok("angle A = 60 degrees", add_special_tokens=False).input_ids
    di = tok("angle A = 70 degrees", add_special_tokens=False).input_ids
    clean = torch.tensor([ci]); corrupt = torch.tensor([di])
    pos = next(k for k in range(len(ci)) if ci[k] != di[k])   # the differing token
    L = 2

    # cache corrupt's layer-L output at pos
    cache = {}
    def cache_hook(mod, inp, out):
        hs = out[0] if isinstance(out, tuple) else out
        cache["v"] = hs[:, pos, :].detach().clone()
    h = layers[L].register_forward_hook(cache_hook)
    with torch.no_grad():
        model(corrupt)
    h.remove()

    with torch.no_grad():
        base = model(clean).logits[0, -1].clone()

    def patch_hook(mod, inp, out):
        hs = out[0] if isinstance(out, tuple) else out
        hs[:, pos, :] = cache["v"]
        return (hs,) + tuple(out[1:]) if isinstance(out, tuple) else hs
    h = layers[L].register_forward_hook(patch_hook)
    with torch.no_grad():
        patched = model(clean).logits[0, -1]
    h.remove()

    assert not torch.allclose(base, patched), "patch did not change the output"
    print("ok  patch hook overwrites activation and changes logits")


if __name__ == "__main__":
    test_minimal_pairs_align()
    test_patch_hook_changes_output()
    print("\nPATCH MECHANICS TESTS PASSED")

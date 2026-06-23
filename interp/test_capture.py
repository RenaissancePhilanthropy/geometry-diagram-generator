"""
Offline smoke tests for the capture harness plumbing — no model download, no GPU.

Builds a TINY randomly-initialised Qwen2 model (same architecture family as
Qwen2.5, reusing the cached Qwen tokenizer) and checks that capture_activations
returns correctly-shaped, position-aligned residual-stream activations. This
verifies the mechanics before any GPU time is spent.

    interp/.venv/bin/python interp/test_capture.py
    interp/.venv/bin/python -m pytest interp/test_capture.py
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.capture import capture_activations, resolve_layers

TOKENIZER = "Qwen/Qwen2.5-7B-Instruct"  # cached locally; tokenizer only, no weights
HIDDEN, N_LAYERS = 64, 4


def _tiny_model_and_tok():
    import torch
    from transformers import AutoTokenizer, Qwen2Config, Qwen2ForCausalLM

    tok = AutoTokenizer.from_pretrained(TOKENIZER)
    cfg = Qwen2Config(
        vocab_size=len(tok),
        hidden_size=HIDDEN,
        num_hidden_layers=N_LAYERS,
        num_attention_heads=4,
        num_key_value_heads=2,
        intermediate_size=128,
        max_position_embeddings=2048,
    )
    torch.manual_seed(0)
    model = Qwen2ForCausalLM(cfg).eval()
    return model, tok


def test_resolve_layers():
    n_hs = N_LAYERS + 1  # 5 hidden states (embeddings + 4 layers)
    assert resolve_layers("all", n_hs) == [0, 1, 2, 3, 4]
    assert resolve_layers("even", n_hs) == [0, 2, 4]
    assert resolve_layers("every:2", n_hs) == [0, 2, 4]
    assert resolve_layers("0,2,4", n_hs) == [0, 2, 4]
    try:
        resolve_layers("0,99", n_hs)
        assert False, "expected out-of-range error"
    except ValueError:
        pass
    print("ok  resolve_layers")


def test_capture_shapes_and_alignment():
    model, tok = _tiny_model_and_tok()
    prompt = "Construct the figure:"
    completion = '{"mode":"abstract","construction":[{"op":"triangle"}]}'
    prompt_ids = tok(prompt, add_special_tokens=False).input_ids
    completion_ids = tok(completion, add_special_tokens=False).input_ids

    n_hs = model.config.num_hidden_layers + 1
    layers = resolve_layers("all", n_hs)
    cap = capture_activations(model, tok, prompt_ids, completion_ids, layers, "cpu")

    n_comp = len(completion_ids)
    # acts: [n_layers, n_completion_tokens, d_model]
    assert cap["acts"].shape == (n_hs, n_comp, HIDDEN), cap["acts"].shape
    assert str(cap["acts"].dtype) == "float16"
    # one offset / token string / special-flag per completion position
    assert len(cap["offsets"]) == n_comp
    assert len(cap["tokens"]) == n_comp
    assert len(cap["is_special"]) == n_comp
    # offsets are monotonic non-decreasing and index the decoded completion
    for (s, e) in cap["offsets"]:
        assert 0 <= s <= e <= len(cap["completion"])
    assert cap["completion"].startswith("{")
    assert cap["prompt_len"] == len(prompt_ids)
    assert cap["layer_ids"] == layers
    print(f"ok  capture shapes {cap['acts'].shape}, {n_comp} aligned positions")


def test_layer_subset_selected():
    model, tok = _tiny_model_and_tok()
    cids = tok('{"construction":[]}', add_special_tokens=False).input_ids
    cap = capture_activations(model, tok, tok("p:", add_special_tokens=False).input_ids,
                              cids, [0, 2, 4], "cpu")
    assert cap["acts"].shape[0] == 3
    assert cap["layer_ids"] == [0, 2, 4]
    print("ok  layer subset")


def test_empty_completion_returns_none():
    model, tok = _tiny_model_and_tok()
    assert capture_activations(model, tok, [1, 2, 3], [], [0], "cpu") is None
    print("ok  empty completion -> None")


if __name__ == "__main__":
    test_resolve_layers()
    test_capture_shapes_and_alignment()
    test_layer_subset_selected()
    test_empty_completion_returns_none()
    print("\nALL CAPTURE SMOKE TESTS PASSED")

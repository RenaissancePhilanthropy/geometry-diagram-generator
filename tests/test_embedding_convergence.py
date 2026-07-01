"""Tests for evals/embedding_convergence.py (reconstruction + convergence metrics)."""
from __future__ import annotations

import array
import math

import pytest

from evals import embedding_convergence as ec
from util.embeddings import chunk_text, text_hash


def _cache_for(texts: list[str], dim: int = 4) -> dict[str, array.array]:
    """Build a fake cache mapping each text's hash to a deterministic vector."""
    out = {}
    for i, t in enumerate(texts):
        v = array.array("f", [float((i + 1) ** (k + 1) % 7) for k in range(dim)])
        out[text_hash(t)] = v
    return out


def test_reconstruct_short_single_chunk():
    text = "short stage text"
    cache = _cache_for([text])
    vecs, found, total = ec.reconstruct(text, 4000, 400, True, cache)
    assert total == 1 and found == 1
    assert vecs is not None and len(vecs) == 1


def test_reconstruct_empty():
    assert ec.reconstruct(None, 4000, 400, True, {}) == (None, 0, 0)
    assert ec.reconstruct("", 4000, 400, True, {}) == (None, 0, 0)


def test_reconstruct_long_all_chunks_cached():
    text = " ".join(f"w{i}" for i in range(3000))  # >4000 chars -> multiple chunks
    chunks = chunk_text(text, 4000, 400)
    cache = _cache_for(chunks)
    vecs, found, total = ec.reconstruct(text, 4000, 400, True, cache)
    assert total == len(chunks)
    assert found == len(chunks)
    assert len(vecs) == len(chunks)


def test_reconstruct_halves_missing_chunk():
    # A long text whose first chunk is NOT in the cache (simulating over-cap ->
    # the run halved it); the halves ARE in the cache. reconstruct should recover
    # the halves' vectors.
    text = " ".join(f"w{i}" for i in range(3000))
    chunks = chunk_text(text, 4000, 400)
    from util.embeddings import _halve
    halves = _halve(chunks[0])
    cache = _cache_for(list(chunks[1:]) + halves)  # first chunk missing, its halves present
    vecs, found, total = ec.reconstruct(text, 4000, 400, True, cache)
    assert vecs is not None
    # recovered the other chunks + the two halves of the missing one
    assert len(vecs) == (len(chunks) - 1) + 2


def test_reconstruct_no_halve_missing_skipped():
    text = " ".join(f"w{i}" for i in range(3000))
    chunks = chunk_text(text, 4000, 400)
    cache = _cache_for(chunks[1:])  # first chunk missing, no halving
    vecs, found, total = ec.reconstruct(text, 4000, 400, False, cache)
    assert found == len(chunks) - 1
    assert len(vecs) == len(chunks) - 1  # missing one skipped


def test_doc_vector_normalized_and_none():
    cache = _cache_for(["x"])
    dv = ec.doc_vector("x", 4000, 400, True, cache)
    assert dv is not None
    assert math.isclose(math.sqrt(sum(c * c for c in dv)), 1.0, abs_tol=1e-5)
    assert ec.doc_vector("", 4000, 400, True, cache) is None
    assert ec.doc_vector("not-in-cache-at-all " * 1000, 4000, 400, False, {}) is None


def test_mean_pairwise_cos():
    assert ec.mean_pairwise_cos([[1.0, 0.0], [1.0, 0.0]]) == pytest.approx(1.0)
    assert ec.mean_pairwise_cos([[1.0, 0.0], [0.0, 1.0]]) == pytest.approx(0.0)
    # three: two identical + one orthogonal -> (1 + 0 + 0)/3
    assert ec.mean_pairwise_cos([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]) == pytest.approx(1 / 3)
    assert ec.mean_pairwise_cos([[1.0, 0.0]]) == 1.0  # single -> defined as 1


def test_mean_centroid_cos():
    assert ec.mean_centroid_cos([[1.0, 0.0], [1.0, 0.0]]) == pytest.approx(1.0)
    # one of two identical -> 1.0; orthogonal pair -> each ~0.707 to centroid
    c = ec.mean_centroid_cos([[1.0, 0.0], [0.0, 1.0]])
    assert c == pytest.approx(1 / math.sqrt(2), rel=1e-3)
    assert ec.mean_centroid_cos([[1.0, 0.0]]) is None  # need >=2


def test_spearman():
    assert ec.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert ec.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert ec.spearman([1, 2], [1, 2]) is None  # need >=3
    assert ec.spearman([1, 1, 1], [1, 2, 3]) is None  # zero variance in a
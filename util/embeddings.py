"""OpenAI-compatible embeddings client: chunking, disk cache, cosine, pooling.

Sends text to an OpenAI ``/v1/embeddings`` endpoint (e.g. an ollama-served
``embeddinggemma`` model on the LAN). The served model has a **hard 2048-token
input cap**: over-cap inputs are silently truncated to ~the first 2048 tokens
(and sometimes stall). To embed long texts (our CoTs run up to ~32k chars) we
**chunk** the text into ≤~1400-token windows (boundary-aware, with overlap),
embed each chunk, and either pool the chunk vectors into one document vector or
combine per-chunk cosine *scores* (max / mean). A halve-on-stall fallback splits
any chunk that still exceeds the cap (token-dense text) and retries.

No third-party deps beyond the already-present ``openai`` SDK; the cache, cosine,
chunking, and pooling are stdlib + sqlite only.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
import threading
from typing import Callable, Sequence

# Chunk size calibrated to the 2048-token cap. ~6000 chars of prose ≈ 2048
# embeddinggemma tokens, but TOKEN-DENSE content (code, coordinate lists, LaTeX)
# can be ~2x denser, so a 4000-char chunk of dense text can itself exceed the
# cap. 3000 chars keeps dense chunks ~1500 tokens (under cap with margin); any
# rare over-cap chunk is caught by halve-on-stall (and now halves immediately,
# no pointless retries).
DEFAULT_MAX_CHARS = 3000
DEFAULT_OVERLAP = 300
# A chunk below this size that still fails to embed is abandoned (extremely
# token-dense; rare). ~200 chars ≈ ~70 tokens — anything that stalls here is
# pathological.
MIN_HALVE_CHARS = 200
# Per-request timeout. Generous: a single small chunk embeds in ~3s, but a
# single ollama server under concurrency can take much longer, and a too-tight
# timeout makes the client close the connection mid-request (ollama logs
# "aborting embedding request due to client closing the connection") and kicks
# off a retry cascade. Better to let a slow request finish than to abort it.
DEFAULT_PER_CALL_TIMEOUT = 90.0
# Retries we do ourselves (with backoff) before giving up on a batch/chunk.
# The openai SDK's own retries are disabled (max_retries=0) to avoid its
# abort-and-retry churn compounding the cascade.
DEFAULT_BATCH_RETRIES = 2


def text_hash(text: str) -> str:
    """Stable content key for caching (sha256 of the UTF-8 bytes)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length vectors.

    Returns 0.0 for empty/zero-norm/mismatched-length vectors (no exceptions).
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    """Split ``text`` into ≤``max_chars`` chunks on whitespace/paragraph boundaries
    with ``overlap`` chars of overlap between consecutive chunks.

    Short text (≤ max_chars) returns a single chunk. Chunks are never cut
    mid-word, and (except possibly the final chunk) are ≥ 60% of max_chars so
    pooling isn't dominated by a tiny tail.
    """
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    min_keep = int(max_chars * 0.6)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            window = text[start:end]
            # minimum chunk length measured from the window start (not absolute
            # position) so progress always exceeds the overlap — prevents an early
            # separator in the window from producing a tiny chunk that walks back.
            lo_rel = min_keep
            cut_rel = -1
            for sep in ("\n\n", "\n", " "):
                idx = window.rfind(sep)
                if idx >= 0 and idx >= lo_rel:
                    cut_rel = idx
                    break
            if cut_rel >= 0:
                end = start + cut_rel + 1  # include the separator
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def _halve(text: str) -> list[str]:
    """Split ``text`` into two pieces on the whitespace boundary nearest the middle."""
    mid = len(text) // 2
    for delta in range(0, max(mid, len(text) - mid) + 1):
        for cand in (mid + delta, mid - delta):
            if 0 < cand < len(text) and text[cand] in " \n\t":
                return [text[:cand], text[cand + 1 :]]
    return [text[:mid], text[mid:]]


def is_overcap_error(exc: BaseException) -> bool:
    """True if the endpoint rejected the input for exceeding its context length.

    Such a chunk will *never* embed at its current size — retrying it is pointless
    (just log spam); the caller should halve it instead. ollama logs this server-
    side as "llm embedding error: the input length exceeds the context length".
    """
    msg = str(exc).lower()
    return any(s in msg for s in ("context length", "exceeds the context", "maximum context length", "input length"))


def pool(vecs: list[list[float]], weights: list[float] | None = None) -> list[float] | None:
    """Token-count-weighted mean of chunk vectors, L2-normalized.

    L2-normalize each chunk first (so high-norm chunks don't dominate), take the
    weighted mean (weights default to equal; pass chunk char/token counts for
    the standard vLLM/OpenAI weighting), then L2-normalize the result. Returns
    None for empty input.
    """
    if not vecs:
        return None
    dim = len(vecs[0])
    if weights is None:
        weights = [1.0] * len(vecs)
    wsum = sum(weights) or 1.0
    normed: list[list[float]] = []
    for v in vecs:
        nm = math.sqrt(sum(x * x for x in v))
        normed.append([x / nm for x in v] if nm > 0 else [0.0] * dim)
    acc = [
        sum(normed[i][k] * weights[i] for i in range(len(vecs))) / wsum
        for k in range(dim)
    ]
    na = math.sqrt(sum(x * x for x in acc))
    return [x / na for x in acc] if na > 0 else [0.0] * dim


class EmbeddingClient:
    """Async OpenAI-compatible embeddings client with a sqlite disk cache.

    ``embed_texts`` is the bulk batched/cached API (no chunking, no truncation;
    returns None for texts that fail even individually). ``embed_document`` chunks
    a long text, embeds the chunks, and halves any that still exceed the cap.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "ollama",
        batch_size: int = 32,
        concurrency: int = 4,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap: int = DEFAULT_OVERLAP,
        per_call_timeout: float = DEFAULT_PER_CALL_TIMEOUT,
        batch_retries: int = DEFAULT_BATCH_RETRIES,
        retry_backoff: float = 2.0,
        cache_path: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.batch_size = max(1, batch_size)
        self.concurrency = max(1, concurrency)
        self.max_chars = max_chars
        self.overlap = overlap
        self.per_call_timeout = per_call_timeout
        self.batch_retries = max(0, batch_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self.cache_path = cache_path
        self._client = None
        self._conn: sqlite3.Connection | None = None
        self._cache_lock = threading.Lock()
        self._semaphore = asyncio.Semaphore(self.concurrency)
        if cache_path:
            self._open_cache()

    # -- cache --------------------------------------------------------------

    def _open_cache(self) -> None:
        assert self.cache_path is not None
        self._conn = sqlite3.connect(self.cache_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS embeddings ("
            "  model TEXT NOT NULL,"
            "  content_hash TEXT NOT NULL,"
            "  dim INTEGER NOT NULL,"
            "  vec_json TEXT NOT NULL,"
            "  PRIMARY KEY (model, content_hash)"
            ")"
        )
        self._conn.commit()

    def _cache_get(self, h: str) -> list[float] | None:
        if self._conn is None:
            return None
        with self._cache_lock:
            row = self._conn.execute(
                "SELECT vec_json FROM embeddings WHERE model=? AND content_hash=?",
                (self.model, h),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _cache_put(self, h: str, vec: list[float]) -> None:
        if self._conn is None:
            return
        with self._cache_lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO embeddings (model, content_hash, dim, vec_json)"
                " VALUES (?, ?, ?, ?)",
                (self.model, h, len(vec), json.dumps(vec)),
            )
            self._conn.commit()

    # -- endpoint -----------------------------------------------------------

    def _ensure_client(self):  # pragma: no cover - thin wrapper over SDK
        if self._client is None:
            from openai import AsyncOpenAI

            # max_retries=0: we do our own retries (with backoff). The SDK's
            # built-in abort-and-retry churn compounds the connection-close
            # cascade that overloads a single ollama server.
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.per_call_timeout,
                max_retries=0,
            )
        return self._client

    async def aclose(self) -> None:
        """Close the underlying httpx pool cleanly (avoids abrupt connection drops)."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        """Direct endpoint call, no semaphore. Raises on timeout/error."""
        client = self._ensure_client()
        resp = await client.embeddings.create(model=self.model, input=texts)
        data = sorted(resp.data, key=lambda d: getattr(d, "index", 0))
        return [list(d.embedding) for d in data]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with self._semaphore:
            return await self._embed_raw(texts)

    # -- public -------------------------------------------------------------

    async def embed_texts(
        self,
        texts: Iterable[str],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[list[float] | None]:
        """Embed texts in batched, cached, concurrent passes. No truncation.

        Returns vectors in input order; None for texts that fail even when retried
        individually (e.g. a token-dense chunk still over the cap — the caller
        should halve those via ``resolve_chunk``). Successful vectors are cached.
        ``on_progress(done, total)`` is called after each batch completes (total =
        number of uncached texts) so the caller can print progress.
        """
        texts = list(texts)
        hashes = [text_hash(t) for t in texts]
        results: list[list[float] | None] = [None] * len(hashes)
        miss_h2t: dict[str, str] = {}
        for i, (h, t) in enumerate(zip(hashes, texts)):
            cached = self._cache_get(h)
            if cached is not None:
                results[i] = cached
            else:
                miss_h2t.setdefault(h, t)
        if not miss_h2t:
            if on_progress:
                on_progress(0, 0)
            return results

        miss_hashes = list(miss_h2t.keys())
        miss_texts = [miss_h2t[h] for h in miss_hashes]
        total = len(miss_texts)
        fetched: dict[str, list[float] | None] = {}
        done = [0]

        async def _one(t: str) -> list[float] | None:
            # Retry a single text with backoff before giving up — but an over-cap
            # text will never embed, so return None immediately (let resolve_chunk
            # halve it). Most other failures are transient server slowness.
            for attempt in range(self.batch_retries + 1):
                try:
                    v = await self._embed_raw([t])
                    return v[0] if v else None
                except Exception as e:
                    if is_overcap_error(e):
                        return None
                    if attempt < self.batch_retries:
                        await asyncio.sleep(self.retry_backoff * (attempt + 1))
            return None

        async def _batch(bh: list[str], bt: list[str]) -> None:
            vecs = None
            overcap = False
            # Retry the whole batch a few times first — fanning out to per-text
            # calls on a transient timeout multiplies in-flight requests and
            # overloads the server (the abort cascade). An over-cap batch is NOT
            # retried (it will always fail); we go straight to isolating per-text.
            for attempt in range(self.batch_retries + 1):
                try:
                    vecs = await self._embed_batch(bt)
                    break
                except Exception as e:
                    if is_overcap_error(e):
                        overcap = True
                        break
                    if attempt < self.batch_retries:
                        await asyncio.sleep(self.retry_backoff * (attempt + 1))
            if vecs is None:
                if overcap and len(bt) == 1:
                    vecs = [None]  # the lone text is over-cap; resolve_chunk halves it
                else:
                    # isolate per-text: the fine texts succeed, the over-cap one None
                    vecs = await asyncio.gather(*[_one(t) for t in bt])
            for h, v in zip(bh, vecs):
                if v is not None:
                    self._cache_put(h, v)
                fetched[h] = v
            done[0] += len(bt)
            if on_progress:
                on_progress(done[0], total)

        tasks: list[asyncio.Task] = []
        for s in range(0, len(miss_texts), self.batch_size):
            bh = miss_hashes[s : s + self.batch_size]
            bt = miss_texts[s : s + self.batch_size]
            tasks.append(asyncio.create_task(_batch(bh, bt)))
        # return_exceptions so one batch's failure doesn't cancel (and abort) the
        # others — cancellation closes in-flight connections => ollama abort storm.
        await asyncio.gather(*tasks, return_exceptions=True)

        for i, h in enumerate(hashes):
            if results[i] is None and h in fetched:
                results[i] = fetched[h]
        return results

    async def resolve_chunk(self, text: str, depth: int = 0) -> list[tuple[list[float], int]]:
        """Recover a chunk that failed to embed (over-cap or persistent failure).

        ``embed_texts`` already retries transient slowness internally and returns
        None immediately for an over-cap chunk, so one attempt here is enough.
        If it failed, halve on a whitespace boundary and recurse — the halves are
        smaller and embed. Returns ``[(vector, char_len), ...]``; empty if a
        sub-min-size chunk still fails (pathological). No retry loop: retrying an
        over-cap chunk is pointless (it will always fail) and just spams the log.
        """
        if not text:
            return []
        v = (await self.embed_texts([text]))[0]
        if v is not None:
            return [(v, len(text))]
        if depth > 6 or len(text) < MIN_HALVE_CHARS:
            return []
        halves = _halve(text)
        out: list[tuple[list[float], int]] = []
        for h in halves:
            out.extend(await self.resolve_chunk(h, depth + 1))
        return out

    async def embed_document(self, text: str) -> list[tuple[list[float], int]]:
        """Chunk ``text``, embed the chunks (bulk), and halve any that fail.

        Returns ``[(vector, char_len), ...]`` one per (sub)chunk. Short text
        yields a single entry. Used by tests; the judge does its own bulk pass.
        """
        chunks = chunk_text(text, self.max_chars, self.overlap)
        vecs = await self.embed_texts(chunks)
        out: list[tuple[list[float], int]] = []
        for ch, v in zip(chunks, vecs):
            if v is not None:
                out.append((v, len(ch)))
            else:
                out.extend(await self.resolve_chunk(ch))
        return out
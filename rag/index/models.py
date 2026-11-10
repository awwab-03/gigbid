"""Open CPU models for retrieval: embeddings and cross-encoder reranker (fastembed / ONNX)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
CACHE = os.getenv("FASTEMBED_CACHE_PATH", str(ROOT / "data" / "processed" / "models"))
CFG = yaml.safe_load(open(os.getenv("GIGBID_CONFIG", ROOT / "agent" / "config.yaml"), encoding="utf-8"))


@lru_cache(maxsize=2)
def embedder(name: str | None = None):
    from fastembed import TextEmbedding

    return TextEmbedding(name or CFG["embeddings"]["model"], cache_dir=CACHE)


@lru_cache(maxsize=2)
def reranker(name: str | None = None):
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(name or CFG["reranker"]["model"], cache_dir=CACHE)


def embed(texts: list[str], query: bool = False) -> np.ndarray:
    e = embedder()
    if query and hasattr(e, "query_embed"):
        vecs = list(e.query_embed(texts))
    else:
        vecs = list(e.embed(texts, batch_size=64))
    m = np.asarray(vecs, dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
    return m


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    if not passages:
        return []
    return [float(s) for s in reranker().rerank(query, passages, batch_size=32)]


def sigmoid(x: float) -> float:
    return float(1 / (1 + np.exp(-x)))

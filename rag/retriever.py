"""Retriever factory: the deployed variant is chosen in config (rag.variant), set from the eval."""

from __future__ import annotations

import importlib

from rag.index.models import CFG
from rag.index.store import get_index
from rag.variants.base import RetrievalResult

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v5_multivector", "v8_crag"]


def get_variant(name: str | None = None):
    name = name or CFG["rag"]["variant"]
    if name not in VARIANTS:
        raise ValueError(f"unknown RAG variant {name}; choose from {VARIANTS}")
    return importlib.import_module(f"rag.variants.{name}")


def retrieve(job: dict, persona: str, variant: str | None = None, k: int | None = None,
             requirements: list[str] | None = None) -> RetrievalResult:
    mod = get_variant(variant)
    return mod.retrieve(job, get_index(persona), k=k or CFG["rag"]["k"], requirements=requirements)

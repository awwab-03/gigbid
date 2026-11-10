"""V0 baseline (required): fixed chunks, top-k cosine on the whole job post."""

from __future__ import annotations

from rag.index.models import embed
from rag.index.store import PortfolioIndex
from rag.variants.base import RetrievalResult, job_text, project_order

NAME = "v0_naive"


def retrieve(job: dict, index: PortfolioIndex, k: int = 10, requirements: list[str] | None = None) -> RetrievalResult:
    q = embed([job_text(job)], query=True)[0]
    hits = index.fixed.dense(q, k * 4)
    projects = project_order(hits)
    ranked = [(p, 1.0 / (i + 1)) for i, p in enumerate(projects)]
    # V0 has no per-requirement view; every requirement sees the same top chunks
    per_req = {r: hits[:3] for r in (requirements or [])}
    return RetrievalResult(NAME, ranked, hits[:k], per_req)

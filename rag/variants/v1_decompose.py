"""V1 requirement decomposition (Query group): one dense retrieval per requirement, then merge."""

from __future__ import annotations

from rag.index.models import embed
from rag.index.store import PortfolioIndex
from rag.variants.base import RetrievalResult, extract_requirements, merge_requirements

NAME = "v1_decompose"


def retrieve(job: dict, index: PortfolioIndex, k: int = 10, requirements: list[str] | None = None) -> RetrievalResult:
    reqs = requirements or extract_requirements(job)
    qv = embed(reqs, query=True)
    per_req = {r: index.struct.dense(qv[i], 8) for i, r in enumerate(reqs)}
    ranked, flat = merge_requirements(per_req, index, k)
    return RetrievalResult(NAME, ranked, flat, per_req)

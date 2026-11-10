"""V3 cross-encoder reranking (Retrieval group): hybrid candidates reranked per requirement."""

from __future__ import annotations

from rag.index.models import embed, rerank_scores
from rag.index.store import Hit, PortfolioIndex
from rag.variants.base import RetrievalResult, extract_requirements, merge_requirements
from rag.variants.v2_hybrid import hybrid

NAME = "v3_rerank"


def rerank(req: str, cands: list[Hit], n: int = 8) -> list[Hit]:
    s = rerank_scores(req, [c.text[:1500] for c in cands])
    out = [Hit(c.chunk_id, sc, c.text, c.meta) for c, sc in zip(cands, s, strict=False)]
    return sorted(out, key=lambda h: -h.score)[:n]


def retrieve(job: dict, index: PortfolioIndex, k: int = 10, requirements: list[str] | None = None) -> RetrievalResult:
    reqs = requirements or extract_requirements(job)
    qv = embed(reqs, query=True)
    per_req = {r: rerank(r, hybrid(index, r, qv[i], n=20)) for i, r in enumerate(reqs)}
    ranked, flat = merge_requirements(per_req, index, k)
    return RetrievalResult(NAME, ranked, flat, per_req)

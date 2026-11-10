"""V2 hybrid retrieval (Retrieval group): BM25 + dense with reciprocal rank fusion, per requirement.

Exact tool names ("Celery", "dbt", "Pinecone") that embeddings blur are caught by BM25, which
also sees code files where the prose only paraphrases the skill.
"""

from __future__ import annotations

from rag.index.models import embed
from rag.index.store import Hit, PortfolioIndex
from rag.variants.base import RetrievalResult, extract_requirements, merge_requirements, rrf

NAME = "v2_hybrid"


def hybrid(index: PortfolioIndex, req: str, qvec, n: int = 10, pool: int = 25, where=None) -> list[Hit]:
    d = index.struct.dense(qvec, pool, where)
    b = index.struct.lexical(req, pool, where)
    fused = rrf([[h.chunk_id for h in d], [h.chunk_id for h in b]])
    by = {h.chunk_id: h for h in d + b}
    order = sorted(fused, key=lambda c: -fused[c])[:n]
    return [Hit(c, fused[c], by[c].text, by[c].meta) for c in order]


def retrieve(job: dict, index: PortfolioIndex, k: int = 10, requirements: list[str] | None = None) -> RetrievalResult:
    reqs = requirements or extract_requirements(job)
    qv = embed(reqs, query=True)
    per_req = {r: hybrid(index, r, qv[i]) for i, r in enumerate(reqs)}
    ranked, flat = merge_requirements(per_req, index, k)
    return RetrievalResult(NAME, ranked, flat, per_req)

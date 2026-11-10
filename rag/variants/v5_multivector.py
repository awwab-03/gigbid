"""V5 multi-vector items (Indexing group): summary, README, code and reviews are indexed separately
and returned as ONE project. A project scores on the best chunk of each type, so a repo whose
README looks irrelevant can still win on its code."""

from __future__ import annotations

from collections import defaultdict

from rag.index.models import embed
from rag.index.store import Hit, PortfolioIndex
from rag.variants.base import RetrievalResult, extract_requirements, rrf

NAME = "v5_multivector"
TYPE_W = {"case_study": 1.0, "profile_item": 0.8, "code": 0.8, "readme": 0.6, "review": 0.5, "proposal": 0.4, "cv": 0.3}


def retrieve(job: dict, index: PortfolioIndex, k: int = 10, requirements: list[str] | None = None) -> RetrievalResult:
    reqs = requirements or extract_requirements(job)
    qv = embed(reqs, query=True)
    per_req: dict[str, list[Hit]] = {}
    rank_lists = []
    for i, r in enumerate(reqs):
        d = index.struct.dense(qv[i], 40)
        b = index.struct.lexical(r, 40)
        bmax = max((h.score for h in b), default=1.0) or 1.0
        best: dict[tuple[str, str], float] = defaultdict(float)
        for h in d:
            for p in h.projects:
                best[(p, h.meta["type"])] = max(best[(p, h.meta["type"])], h.score)
        for h in b:
            for p in h.projects:
                best[(p, h.meta["type"])] = max(best[(p, h.meta["type"])], 0.5 + 0.5 * h.score / bmax)
        proj: dict[str, float] = defaultdict(float)
        for (p, t), s in best.items():
            proj[p] = max(proj[p], s * TYPE_W.get(t, 0.5)) + 0.05 * s
        order = sorted(proj, key=lambda p: -proj[p])
        rank_lists.append(order)
        per_req[r] = sorted(d + b, key=lambda h: order.index(h.projects[0]) if h.projects and h.projects[0] in order else 999)[:6]
    fused = rrf(rank_lists)
    ranked = sorted(fused.items(), key=lambda x: -x[1])
    flat = [h for hs in per_req.values() for h in hs]
    return RetrievalResult(NAME, ranked, flat[: k * 3], per_req)

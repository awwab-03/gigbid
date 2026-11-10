"""V8 corrective RAG loop in LangGraph (Agentic group).

Per requirement:  retrieve (hybrid + rerank) -> grade (cross-encoder score of best chunk)
  -> strong: keep evidence
  -> weak and attempts left: rewrite the query and retrieve again
  -> still weak: REFUSE to claim (requirement marked unsupported, no evidence passed to the Writer)

The rewrite uses an LLM when one is injected (`set_rewriter`), otherwise a deterministic broadening
(keyword-only BM25 over the bare requirement plus a larger candidate pool). Thresholds live in
agent/config.yaml (rag.crag_*).
"""

from __future__ import annotations

from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from rag.index.models import CFG, embed
from rag.index.store import Hit, PortfolioIndex
from rag.variants.base import RetrievalResult, extract_requirements, merge_requirements
from rag.variants.v2_hybrid import hybrid
from rag.variants.v3_rerank import rerank

NAME = "v8_crag"
_rewriter: Callable[[str, str], str] | None = None


def set_rewriter(fn: Callable[[str, str], str] | None) -> None:
    """fn(requirement, job_title) -> rewritten query (e.g. an LLM call)."""
    global _rewriter
    _rewriter = fn


class CragState(TypedDict, total=False):
    requirement: str
    query: str
    job_title: str
    attempts: int
    hits: list
    top_score: float
    verdict: str


def build_crag_graph(index: PortfolioIndex):
    good = float(CFG["rag"].get("crag_good_logit", 0.0))
    max_attempts = int(CFG["rag"].get("crag_max_attempts", 2))

    def retrieve_node(s: CragState) -> CragState:
        q = s.get("query") or s["requirement"]
        qv = embed([q], query=True)[0]
        cands = hybrid(index, q, qv, n=20, pool=25 + 15 * s.get("attempts", 0))
        hits = rerank(s["requirement"], cands)
        return {"hits": hits, "attempts": s.get("attempts", 0) + 1}

    def grade_node(s: CragState) -> CragState:
        top = s["hits"][0].score if s["hits"] else -99.0
        return {"top_score": top}

    def route(s: CragState) -> str:
        if s["top_score"] >= good:
            return "accept"
        return "rewrite" if s["attempts"] < max_attempts else "refuse"

    def rewrite_node(s: CragState) -> CragState:
        if _rewriter:
            q = _rewriter(s["requirement"], s.get("job_title", ""))
        else:
            q = f"{s['requirement']} project delivered for a client"
        return {"query": q}

    def accept_node(s: CragState) -> CragState:
        return {"verdict": "supported", "hits": [h for h in s["hits"] if h.score >= good - 2.0][:6]}

    def refuse_node(s: CragState) -> CragState:
        return {"verdict": "unsupported", "hits": []}

    g = StateGraph(CragState)
    g.add_node("retrieve", retrieve_node)
    g.add_node("grade", grade_node)
    g.add_node("rewrite", rewrite_node)
    g.add_node("accept", accept_node)
    g.add_node("refuse", refuse_node)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route, {"accept": "accept", "rewrite": "rewrite", "refuse": "refuse"})
    g.add_edge("rewrite", "retrieve")
    g.add_edge("accept", END)
    g.add_edge("refuse", END)
    return g.compile()


_graphs: dict[str, object] = {}


def retrieve(job: dict, index: PortfolioIndex, k: int = 10, requirements: list[str] | None = None) -> RetrievalResult:
    reqs = requirements or extract_requirements(job)
    if index.persona not in _graphs:
        _graphs[index.persona] = build_crag_graph(index)
    graph = _graphs[index.persona]
    per_req: dict[str, list[Hit]] = {}
    unsupported, attempts = [], {}
    for r in reqs:
        out = graph.invoke({"requirement": r, "job_title": job.get("title", "")})
        attempts[r] = out["attempts"]
        if out["verdict"] == "unsupported":
            unsupported.append(r)
            per_req[r] = []
        else:
            per_req[r] = out["hits"]
    ranked, flat = merge_requirements({r: h for r, h in per_req.items() if h}, index, k)
    return RetrievalResult(NAME, ranked, flat, per_req, unsupported_requirements=unsupported, debug={"attempts": attempts})

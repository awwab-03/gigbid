"""Regression: a job seen in an earlier scout must not come back as a "duplicate of itself" (13 Nov 2026 bug that
overwrote analysed inbox rows with status=skipped), while real reposts are still caught."""
import asyncio

from langgraph.store.memory import InMemoryStore

from agent.nodes import scout as sc

DESC = "We need a Python developer to build a retrieval augmented generation pipeline over our support tickets."
JOBS = [{"job_id": "j-1", "client_id": "c-1", "description": DESC, "title": "RAG"}]


class FakeToolbox:
    def __init__(self, *a, **k):
        pass

    async def call(self, name, args):
        return {"jobs": JOBS}


def test_rescout_is_not_a_self_duplicate_but_repost_is(monkeypatch):
    store = InMemoryStore()
    monkeypatch.setattr(sc, "get_store", lambda: store)
    monkeypatch.setattr(sc, "Toolbox", FakeToolbox)
    first = asyncio.run(sc.scout("u", "ml_engineer", [{"query": ""}]))
    assert [j["job_id"] for j in first["new"]] == ["j-1"] and first["duplicates"] == []
    again = asyncio.run(sc.scout("u", "ml_engineer", [{"query": ""}]))
    assert again == {"new": [], "duplicates": []}
    JOBS.append({"job_id": "j-2", "client_id": "c-1", "description": DESC + " Budget 500.", "title": "RAG again"})
    try:
        third = asyncio.run(sc.scout("u", "ml_engineer", [{"query": ""}]))
    finally:
        JOBS.pop()
    assert third["duplicates"] == [{"job_id": "j-2", "duplicate_of": "j-1"}]

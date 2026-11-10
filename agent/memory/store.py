"""Long-term memory on a LangGraph store (PostgresStore in deployment, InMemoryStore in tests).

Namespaces (per user = tenant)
  ("style_obs", user)              observations from edits        (staging, not memory)
  ("style", user)                  promoted style rules            (memory, user-deletable)
  ("outcome_obs", user)            confirmed outcome observations  (staging, not memory)
  ("outcome", user, category)      promoted outcome insights       (memory, user-deletable)
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from agent.memory.promotion_rules import observe_edit, outcome_promotions, style_promotions

_store: BaseStore | None = None


def get_store() -> BaseStore:
    global _store
    if _store is None:
        url = os.getenv("DATABASE_URL", "")
        if url.startswith("postgres"):
            from langgraph.store.postgres import PostgresStore
            from psycopg import Connection
            from psycopg.rows import dict_row

            conn = Connection.connect(url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True, row_factory=dict_row)
            _store = PostgresStore(conn)
            _store.setup()
        else:
            _store = InMemoryStore()
    return _store


def set_store(store: BaseStore) -> None:
    global _store
    _store = store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_edit(user: str, job_id: str, original: str, edited: str) -> list[dict]:
    """Store an edit observation, then re-run RULE S1 and sync the promoted style rules."""
    s = get_store()
    obs = observe_edit(original, edited)
    key = hashlib.sha256(f"{job_id}|{edited}".encode()).hexdigest()[:16]
    s.put(("style_obs", user), key, {**obs, "job_id": job_id, "at": _now()})
    all_obs = [i.value for i in s.search(("style_obs", user), limit=1000)]
    deleted = {i.key for i in s.search(("style_deleted", user), limit=1000)}
    promoted = [p for p in style_promotions(all_obs) if p["pattern"] not in deleted]
    for p in promoted:
        s.put(("style", user), p["pattern"], {**p, "at": _now()})
    return promoted


def style_rules(user: str) -> list[str]:
    return [i.value["rule"] for i in get_store().search(("style", user), limit=50)]


def record_outcome(user: str, *, proposal_id: str, category: str, outcome: str, cited_projects: list[str],
                   generic_opening: bool) -> list[dict]:
    """Called ONLY for confirmed marketplace events (proposal.replied / hired / lost)."""
    s = get_store()
    s.put(("outcome_obs", user), proposal_id, {"category": category, "outcome": outcome, "cited_projects": cited_projects,
                                               "generic_opening": generic_opening, "at": _now()})
    obs = [i.value for i in s.search(("outcome_obs", user), limit=5000)]
    promoted = outcome_promotions(obs)
    for p in promoted:
        key = p.get("project") or p["promoted_by"]
        s.put(("outcome", user, p["category"]), key, {**p, "at": _now()})
    return promoted


def outcome_insights(user: str, category: str) -> list[str]:
    return [i.value["insight"] for i in get_store().search(("outcome", user, category), limit=20)]


def list_memory(user: str) -> dict:
    s = get_store()
    style = [{"key": i.key, **i.value} for i in s.search(("style", user), limit=100)]
    outcome = [{"key": i.key, "namespace": list(i.namespace), **i.value} for i in s.search(("outcome", user), limit=200)]
    return {"style": style, "outcome": outcome,
            "observations": {"edits": len(s.search(("style_obs", user), limit=1000)),
                             "outcomes": len(s.search(("outcome_obs", user), limit=5000))}}


def delete_memory(user: str, kind: str, key: str, category: str | None = None) -> None:
    """User-initiated delete from the memory viewer. A deleted style rule is tombstoned so the
    same old observations cannot immediately re-promote it."""
    s = get_store()
    if kind == "style":
        s.delete(("style", user), key)
        s.put(("style_deleted", user), key, {"at": _now()})
    else:
        s.delete(("outcome", user, category or ""), key)

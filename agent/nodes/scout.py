"""Scout: run saved searches through the marketplace port, de-duplicate, queue new jobs.

De-duplication: exact job_id, plus near-duplicate reposts (same client and >= 0.8 Jaccard
similarity of word 3-shingles over the description with numbers removed). Seen signatures are
kept per user in the LangGraph store namespace ("seen_jobs", user).
"""

from __future__ import annotations

import re

from agent.mcp_client import Toolbox
from agent.memory.store import get_store
from agent.nodes._runtime import node

DUP_JACCARD = 0.8


def shingles(text: str, n: int = 3) -> set[str]:
    words = re.findall(r"[a-z]+", re.sub(r"\d+", " ", text.lower()))
    return {" ".join(words[i: i + n]) for i in range(max(0, len(words) - n + 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def find_duplicate(user: str, job: dict) -> str | None:
    s = get_store()
    ns = ("seen_jobs", user)
    if s.get(ns, job["job_id"]):
        return job["job_id"]
    sh = shingles(job.get("description", ""))
    for item in s.search(ns, filter={"client_id": job.get("client_id")}, limit=200):
        if jaccard(sh, set(item.value["shingles"])) >= DUP_JACCARD:
            return item.key
    return None


def remember_job(user: str, job: dict) -> None:
    get_store().put(("seen_jobs", user), job["job_id"], {"client_id": job.get("client_id"),
                                                         "shingles": sorted(shingles(job.get("description", "")))})


async def scout(user_id: str, account: str, searches: list[dict], posted_after: str | None = None) -> dict:
    """Run every saved search once (called by the worker on its schedule)."""
    tb = Toolbox("scout", user_id, account)
    new, dups, seen_ids = [], [], set()
    for s in searches:
        res = await tb.call("marketplace.search_jobs", {k: v for k, v in {**s, "posted_after": posted_after}.items() if v is not None})
        for job in res["jobs"]:
            if job["job_id"] in seen_ids:
                continue
            seen_ids.add(job["job_id"])
            dup = find_duplicate(user_id, job)
            if dup:
                dups.append({"job_id": job["job_id"], "duplicate_of": dup})
                continue
            remember_job(user_id, job)
            new.append(job)
    return {"new": new, "duplicates": dups}


@node("intake")
async def intake(state: dict) -> dict:
    """Graph entry: make sure we have the full job, then check it is not a repost."""
    job = state.get("job") or {}
    if "description" not in job:
        tb = Toolbox("scout", state.get("user_id", "local"), state.get("account", "ml_engineer"))
        job = await tb.call("marketplace.get_job", {"job_id": job["job_id"]})
    dup = None if state.get("skip_dedup") else find_duplicate(state.get("user_id", "local"), job)
    if dup and dup != job["job_id"]:
        return {"job": job, "status": "skipped", "status_reason": f"duplicate of {dup}",
                "decision": {"action": "skip", "reasons": [f"duplicate repost of {dup}"], "confidence": 0.95},
                "_summary": f"duplicate of {dup}"}
    if not state.get("skip_dedup"):
        remember_job(state.get("user_id", "local"), job)
    return {"job": job, "status": "analysing", "_summary": job.get("title", "")}

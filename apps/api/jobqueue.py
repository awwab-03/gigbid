"""Enqueue long work. Production: Arq jobs on Redis executed by the worker (never inside a web
request). Dev without Redis: an in-process asyncio task (WORKER_MODE=inline).

Arq job ids are deterministic (e.g. analyze:<user>:<job>), so double-clicks, retries and worker
restarts never run the same work twice concurrently (E1)."""

from __future__ import annotations

import asyncio
import logging
import os

from apps.api import db

log = logging.getLogger("gigbid.queue")
_pool = None
_tasks: set = set()


def mode() -> str:
    return os.getenv("WORKER_MODE", "arq" if os.getenv("REDIS_URL") else "inline")


async def _arq():
    global _pool
    if _pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
    return _pool


async def enqueue(fn: str, queue_id: str, **kwargs) -> dict:
    if mode() == "arq":
        pool = await _arq()
        j = await pool.enqueue_job(fn, _job_id=queue_id, **kwargs)
        return {"queued": True, "job_id": queue_id, "duplicate": j is None, "mode": "arq"}
    from worker import tasks

    async def run():
        try:
            await getattr(tasks, fn)({}, **kwargs)
        except Exception as e:  # noqa: BLE001
            log.exception("inline task %s failed: %s", fn, e)

    t = asyncio.create_task(run())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return {"queued": True, "job_id": queue_id, "mode": "inline"}


def user(user_id: str) -> dict:
    u = db.get_user(user_id)
    if not u:
        raise ValueError(f"unknown user {user_id}")
    return u

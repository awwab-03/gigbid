"""Checkpointer factory (C6): AsyncPostgresSaver in deployment, in-memory for tests and evals."""

from __future__ import annotations

import os

from langgraph.checkpoint.memory import InMemorySaver

_saver = None
_pool = None


async def get_checkpointer():
    global _saver, _pool
    if _saver is not None:
        return _saver
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres") and os.getenv("CHECKPOINTER", "postgres") == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        _pool = AsyncConnectionPool(url.replace("postgresql+psycopg://", "postgresql://"), max_size=10, open=False,
                                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
        await _pool.open()
        _saver = AsyncPostgresSaver(_pool)
        await _saver.setup()
    else:
        _saver = InMemorySaver()
    return _saver


def set_checkpointer(saver) -> None:
    global _saver
    _saver = saver

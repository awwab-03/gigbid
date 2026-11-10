"""Relational store for the web app (users, settings, job inbox index, runs, run events).

Postgres in deployment (DATABASE_URL), SQLite file for local development. Graph state itself lives
in the LangGraph checkpointer; these tables index it for the UI. Every query is tenant-scoped by
user_id (E4).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)

ROOT = Path(__file__).resolve().parents[2]
url = os.getenv("DATABASE_URL", "")
if url.startswith("postgres"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1) if "+psycopg" not in url else url
else:
    (ROOT / "logs").mkdir(exist_ok=True)
    url = f"sqlite:///{ROOT / 'logs' / 'gigbid_app.sqlite'}"
engine = create_engine(url, pool_pre_ping=True, future=True)
meta = MetaData()


def now() -> datetime:
    return datetime.now(timezone.utc)


users = Table("users", meta,
              Column("id", String(64), primary_key=True), Column("email", String(255), unique=True, nullable=False),
              Column("password_hash", String(255), nullable=False), Column("name", String(255)),
              Column("account", String(64), nullable=False),          # marketplace account / persona
              Column("settings", JSON, nullable=False, default=dict), Column("created_at", DateTime(timezone=True), default=now))

jobs = Table("jobs", meta,
             Column("user_id", String(64), primary_key=True), Column("job_id", String(64), primary_key=True),
             Column("thread_id", String(128)), Column("title", Text), Column("category", String(32)),
             Column("status", String(32), default="new"), Column("action", String(16)), Column("fit", Float), Column("risk", Float),
             Column("scam", Integer, default=0), Column("price", Float), Column("bid_type", String(16)), Column("connects", Integer),
             Column("flags", JSON, default=list), Column("reason", Text), Column("job", JSON), Column("proposal_id", String(64)),
             Column("pipeline", String(32)), Column("posted_at", String(32)), Column("updated_at", DateTime(timezone=True), default=now))

runs = Table("runs", meta,
             Column("thread_id", String(128), primary_key=True), Column("user_id", String(64), nullable=False, index=True),
             Column("kind", String(16)), Column("ref", String(64)), Column("status", String(32)), Column("trace_id", String(64)),
             Column("trace_url", Text), Column("pending", JSON), Column("tokens", Integer, default=0), Column("cost_usd", Float, default=0),
             Column("latency_s", Float, default=0), Column("node_latency", JSON), Column("error", Text),
             Column("started_at", DateTime(timezone=True), default=now), Column("updated_at", DateTime(timezone=True), default=now))

run_events = Table("run_events", meta,
                   Column("id", Integer, primary_key=True, autoincrement=True), Column("thread_id", String(128), index=True),
                   Column("user_id", String(64), index=True), Column("type", String(32)), Column("node", String(64)),
                   Column("data", JSON), Column("at", DateTime(timezone=True), default=now))

meta.create_all(engine)


def row(r) -> dict | None:
    return dict(r._mapping) if r is not None else None


def get_user(user_id: str) -> dict | None:
    with engine.begin() as c:
        return row(c.execute(select(users).where(users.c.id == user_id)).first())


def get_user_by_email(email: str) -> dict | None:
    with engine.begin() as c:
        return row(c.execute(select(users).where(users.c.email == email.lower())).first())


def upsert_job(user_id: str, job_id: str, **fields) -> None:
    fields["updated_at"] = now()
    with engine.begin() as c:
        exists = c.execute(select(jobs.c.job_id).where(jobs.c.user_id == user_id, jobs.c.job_id == job_id)).first()
        if exists:
            c.execute(update(jobs).where(jobs.c.user_id == user_id, jobs.c.job_id == job_id).values(**fields))
        else:
            c.execute(insert(jobs).values(user_id=user_id, job_id=job_id, **fields))


def upsert_run(thread_id: str, user_id: str, **fields) -> None:
    fields["updated_at"] = now()
    with engine.begin() as c:
        exists = c.execute(select(runs.c.thread_id).where(runs.c.thread_id == thread_id)).first()
        if exists:
            c.execute(update(runs).where(runs.c.thread_id == thread_id, runs.c.user_id == user_id).values(**fields))
        else:
            c.execute(insert(runs).values(thread_id=thread_id, user_id=user_id, **fields))


def add_event(thread_id: str, user_id: str, typ: str, node: str | None, data: dict) -> int:
    with engine.begin() as c:
        r = c.execute(insert(run_events).values(thread_id=thread_id, user_id=user_id, type=typ, node=node,
                                                data=json.loads(json.dumps(data, default=str))))
        return int(r.inserted_primary_key[0])


def events_after(thread_id: str, user_id: str, after: int) -> list[dict]:
    with engine.begin() as c:
        rs = c.execute(select(run_events).where(run_events.c.thread_id == thread_id, run_events.c.user_id == user_id,
                                                run_events.c.id > after).order_by(run_events.c.id)).all()
    return [row(r) for r in rs]

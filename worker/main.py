"""Arq worker settings.  Run:  arq worker.main.WorkerSettings

Schedules (justified in docs/RUNBOOK.md):
  * pipeline sync + degraded retries: every 2 minutes (GigSim) - cheap reads of the event feed
  * scouting: every `marketplace.gigsim_scout_interval_minutes` (30) in GigSim mode and
    `marketplace.live_scout_interval_minutes` (240) in live Upwork mode, never more often
"""

from __future__ import annotations

import os

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from agent.llm import CFG
from apps.api import db
from worker import tasks

LIVE = os.getenv("MARKETPLACE_MODE", CFG["marketplace"]["mode"]) == "upwork_live"
SCOUT_EVERY = CFG["marketplace"]["live_scout_interval_minutes" if LIVE else "gigsim_scout_interval_minutes"]


async def scout_all(ctx):
    with db.engine.begin() as c:
        ids = [r[0] for r in c.execute(select(db.users.c.id)).all()]
    return {uid: await tasks.scout_user(ctx, uid) for uid in ids}


class WorkerSettings:
    functions = [tasks.analyze_job, tasks.resume_thread, tasks.run_conversation, tasks.scout_user, tasks.sync_pipeline,
                 tasks.retry_degraded, tasks.replay_thread]
    cron_jobs = [
        cron(tasks.tick_all, minute=set(range(0, 60, 2)), run_at_startup=False, unique=True),
        cron(scout_all, minute=set(range(0, 60, min(60, SCOUT_EVERY))), hour=None if SCOUT_EVERY < 60 else set(range(0, 24, SCOUT_EVERY // 60)),
             unique=True),
    ]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = int(os.getenv("WORKER_CONCURRENCY", "4"))
    job_timeout = 900
    keep_result = 3600

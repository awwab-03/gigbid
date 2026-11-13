"""One-off repair for the scout bug fixed on 13 Nov 2026.

Before the fix, every scheduled scout re-marked already-seen jobs as "duplicate of <itself>" and overwrote their inbox
row with status=skipped. This restores each affected row from its run's checkpointed state (the source of truth), or
resets it to "new" when the job was never analysed. Runs and approvals were never touched.

  python scripts/repair_self_duplicates.py          # report only
  python scripts/repair_self_duplicates.py --apply
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from apps.api import db, runner


async def main(apply: bool) -> None:
    g = await runner.graph("bid")
    with db.engine.begin() as c:
        rows = c.execute(select(db.jobs.c.user_id, db.jobs.c.job_id, db.jobs.c.thread_id)
                         .where(db.jobs.c.reason == "duplicate of " + db.jobs.c.job_id)).all()
    restored = reset = 0
    for user_id, job_id, thread_id in rows:
        state = (await g.aget_state({"configurable": {"thread_id": thread_id}})).values if thread_id else {}
        if state.get("job"):
            restored += 1
            if apply:
                runner._index_job(user_id, state)
        else:
            reset += 1
            if apply:
                db.upsert_job(user_id, job_id, status="new", action=None, reason=None)
    print(f"affected {len(rows)}: restored from run state {restored}, reset to new {reset}, applied={apply}")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))

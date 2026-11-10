"""Node runtime: budgets, timeouts, bounded retries, dead-letter and degraded mode, usage + trace.

Every graph node is wrapped by @node(name):
  * step budget and token budget per thread -> status "needs_attention" when exceeded (C4)
  * per-node timeout and up to N attempts with backoff (C7); a final failure -> "dead_letter"
  * ToolUnavailable (marketplace down / rate-limited) -> "queued_degraded" so the worker retries
    later and the UI shows the marketplace-unavailable banner (A6)
  * tokens, cost and latency per node from the UsageLedger; an execution-trace entry per node,
    PII-masked, kept separate from long-term memory
"""

from __future__ import annotations

import asyncio
import functools
import os
import time
from typing import Any, Awaitable, Callable

from langgraph.errors import GraphBubbleUp

from agent.llm import CFG, UsageLedger, ledger_var
from agent.mcp_client import Toolbox, ToolUnavailable
from shared.pii import mask_obj
from shared.security import trace_id_var

TIMEOUT_SCALE = float(os.getenv("GIGBID_TIMEOUT_SCALE", "1"))  # e.g. 6 for CPU-only local models
NODE_TIMEOUT_S = {"writer": 120, "critic": 90, "fit_matcher": 90, "client_liaison": 90, "analyst": 60}
NODE_ATTEMPTS = 2
TERMINAL = {"skipped", "watching", "blocked", "needs_attention", "queued_degraded", "dead_letter", "rejected", "submitted"}


def toolbox(state: dict, agent: str) -> Toolbox:
    return Toolbox(agent, state.get("user_id", "local"), state.get("account", "ml_engineer"))


def over_budget(state: dict) -> str | None:
    b = CFG["budgets"]
    if (state.get("steps") or 0) >= b["max_graph_steps"]:
        return f"step budget exceeded ({state.get('steps')} >= {b['max_graph_steps']})"
    if (state.get("tokens") or 0) >= b["max_tokens_per_job"]:
        return f"token budget exceeded ({state.get('tokens')} >= {b['max_tokens_per_job']})"
    return None


def node(name: str):
    def deco(fn: Callable[[dict], Awaitable[dict]]):
        @functools.wraps(fn)
        async def wrapper(state: dict, *args: Any, **kwargs: Any) -> dict:
            if state.get("status") in TERMINAL - {"submitted"} and name not in ("finalize",):
                return {}
            reason = over_budget(state)
            if reason:
                return {"status": "needs_attention", "status_reason": reason, "steps": 1,
                        "trace": [{"node": name, "event": "budget_exceeded", "detail": reason}]}
            if state.get("trace_id"):
                trace_id_var.set(state["trace_id"])
            ledger = UsageLedger()
            token = ledger_var.set(ledger)
            t0 = time.perf_counter()
            err = ""
            try:
                for attempt in range(NODE_ATTEMPTS):
                    try:
                        out = await asyncio.wait_for(fn(state), timeout=NODE_TIMEOUT_S.get(name, 60) * TIMEOUT_SCALE)
                        break
                    except GraphBubbleUp:  # interrupt() for human approval must propagate
                        raise
                    except ToolUnavailable as e:
                        return {"status": "queued_degraded", "status_reason": str(e), "steps": 1, "errors": [f"{name}: {e}"],
                                "trace": [{"node": name, "event": "degraded", "detail": str(e)}]}
                    except Exception as e:  # noqa: BLE001
                        err = f"{type(e).__name__}: {e}"
                        if attempt + 1 >= NODE_ATTEMPTS:
                            return {"status": "dead_letter", "status_reason": f"{name} failed: {err}"[:500], "steps": 1,
                                    "errors": [f"{name}: {err}"[:500]],
                                    "trace": [{"node": name, "event": "dead_letter", "detail": err[:500]}]}
                        await asyncio.sleep(0.5 * (attempt + 1))
            finally:
                ledger_var.reset(token)
            dt = time.perf_counter() - t0
            out = dict(out or {})
            out["steps"] = 1
            out["tokens"] = ledger.tokens
            out["cost_usd"] = ledger.cost
            out["node_latency"] = {name: round(dt, 3)}
            out.setdefault("trace", [])
            out["trace"] = [{"node": name, "event": "done", "latency_s": round(dt, 3), "tokens": ledger.tokens,
                             "cost_usd": ledger.cost, "models": sorted({r.model for r in ledger.records}),
                             "summary": mask_obj(out.pop("_summary", ""))}] + out["trace"]
            return out

        wrapper.__node_name__ = name
        return wrapper

    return deco

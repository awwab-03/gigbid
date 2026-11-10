"""Decision evaluation (B4): bid-or-skip F1, scam precision/recall, price inside the fair band,
injection flagging, latency and cost per job analysed. Runs the real bid graph (analysis, decision,
pricing) against an in-process GigSim, stopping before the Writer.

  python -m evals.runners.decision_eval --limit 50          # per persona
  MODEL_PROFILE=open python -m evals.runners.decision_eval  # record which profile produced the numbers
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

os.environ.setdefault("MCP_TRANSPORT", "inproc")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_RATE_LIMIT", "100000")
os.environ.setdefault("MARKETPLACE_RPM", "100000")  # offline eval against an in-process simulator only

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "evals" / "results"
PERSONAS = ["ml_engineer", "fullstack_dev", "data_analyst"]


def setup_inprocess_gigsim():
    import tempfile

    os.environ.setdefault("GIGSIM_DB", os.path.join(tempfile.mkdtemp(), "gigsim_eval.sqlite"))
    import httpx

    from gigsim.app import app as gs_app
    from mcp_servers.marketplace import server
    from mcp_servers.marketplace.adapters.gigsim import GigSimBackend

    server.backend = GigSimBackend(client=httpx.AsyncClient(transport=httpx.ASGITransport(app=gs_app), base_url="http://gigsim"),
                                   max_retries=1)
    return gs_app


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return round(xs[max(0, int(len(xs) * 0.95) - 1)], 3) if xs else 0.0


async def eval_job(graph, persona: str, g: dict, profile: dict, sem) -> dict:
    from langgraph.types import Command  # noqa: F401

    async with sem:
        tid = f"eval:{persona}:{g['job_id']}"
        cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 40}
        t0 = time.perf_counter()
        async for _ in graph.astream({"thread_id": tid, "user_id": f"eval-{persona}", "account": persona, "job": {"job_id": g["job_id"]},
                                      "profile": profile}, cfg, stream_mode="updates"):
            pass
        st = (await graph.aget_state(cfg)).values
        dt = time.perf_counter() - t0
    dec = (st.get("decision") or {}).get("action", "error")
    price = (st.get("price") or {}).get("amount")
    lo, hi = g["fair_price_band"]
    return {"job_id": g["job_id"], "persona": persona, "gold": g["decision"], "pred": dec, "skip_reasons": g["skip_reasons"],
            "pred_reasons": (st.get("decision") or {}).get("reasons", []), "is_scam": g["is_scam"],
            "pred_scam": bool((st.get("risk_report") or {}).get("scam_likely")), "has_injection": g["has_injection"],
            "pred_injection": bool((st.get("risk_report") or {}).get("injection_detected")), "fit": (st.get("fit_report") or {}).get("score"),
            "coverage": g["coverage"], "price": price, "band": [lo, hi], "in_band": (lo <= price <= hi) if price else None,
            "status": st.get("status"), "errors": (st.get("errors") or [])[:2], "latency_s": round(dt, 3), "tokens": st.get("tokens", 0), "cost_usd": st.get("cost_usd", 0.0)}


def summarize(rows: list[dict]) -> dict:
    tp = sum(r["gold"] == "bid" and r["pred"] == "bid" for r in rows)
    fp = sum(r["gold"] != "bid" and r["pred"] == "bid" for r in rows)
    fn = sum(r["gold"] == "bid" and r["pred"] != "bid" for r in rows)
    stp = sum(r["is_scam"] and r["pred_scam"] for r in rows)
    sfp = sum((not r["is_scam"]) and r["pred_scam"] for r in rows)
    sfn = sum(r["is_scam"] and not r["pred_scam"] for r in rows)
    priced = [r for r in rows if r["gold"] == "bid" and r["pred"] == "bid" and r["in_band"] is not None]
    inj = [r for r in rows if r["has_injection"]]
    return {"n": len(rows), "bid_skip": prf(tp, fp, fn), "accuracy": round(sum((r["gold"] == "bid") == (r["pred"] == "bid") for r in rows) / max(1, len(rows)), 4),
            "scam": prf(stp, sfp, sfn), "price_in_band": round(sum(r["in_band"] for r in priced) / len(priced), 4) if priced else None,
            "injection_flag_recall": round(sum(r["pred_injection"] for r in inj) / len(inj), 4) if inj else None,
            "latency_p50_s": round(sorted(r["latency_s"] for r in rows)[len(rows) // 2], 3) if rows else 0, "latency_p95_s": p95([r["latency_s"] for r in rows]),
            "tokens_per_job": round(sum(r["tokens"] for r in rows) / max(1, len(rows)), 1),
            "cost_per_job_usd": round(sum(r["cost_usd"] for r in rows) / max(1, len(rows)), 6),
            "errors": sum(r["pred"] == "error" for r in rows)}


async def main(limit: int | None, personas: list[str], concurrency: int, tag: str) -> dict:
    from langgraph.checkpoint.memory import InMemorySaver

    from agent.graphs.bid_graph import build_bid_graph
    from agent.llm import profile_name

    setup_inprocess_gigsim()
    graph = build_bid_graph(checkpointer=InMemorySaver(), stop_before=["writer"])
    sem = asyncio.Semaphore(concurrency)
    rows: list[dict] = []
    for p in personas:
        gold = [json.loads(x) for x in (ROOT / f"evals/datasets/dev/{p}.jsonl").read_text().splitlines() if x.strip()]
        gold = [g for g in gold if not g["is_duplicate"]][:limit] if limit else [g for g in gold if not g["is_duplicate"]]
        profile = json.loads((ROOT / f"data/personas/{p}/profile.json").read_text())
        rows += await asyncio.gather(*(eval_job(graph, p, g, profile, sem) for g in gold))
    from agent.llm import CFG

    out = {"profile": profile_name(), "rag_variant": CFG["rag"]["variant"], "limit_per_persona": limit,
           "overall": summarize(rows), "by_persona": {p: summarize([r for r in rows if r["persona"] == p]) for p in personas}}
    RES.mkdir(parents=True, exist_ok=True)
    name = f"decision_eval_{tag or profile_name()}{'_limit' + str(limit) if limit else ''}"
    (RES / f"{name}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (RES / f"{name}_rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    o = out["overall"]
    print(f"[{out['profile']}/{out['rag_variant']}] n={o['n']} bid-F1={o['bid_skip']['f1']} acc={o['accuracy']} scam P/R={o['scam']['precision']}/"
          f"{o['scam']['recall']} price-in-band={o['price_in_band']} inj-flag={o['injection_flag_recall']} p95={o['latency_p95_s']}s "
          f"cost/job=${o['cost_per_job_usd']}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--personas", nargs="*", default=PERSONAS)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.personas, a.concurrency, a.tag))

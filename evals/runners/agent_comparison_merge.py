"""Merge R&D C arms run separately into one matched comparison.

The graph arm ran on 17 jobs per persona (agent_comparison_graph_rows.jsonl); the single-agent and supervisor arms
were rerun later on the first 6 of those same jobs (agent_comparison_baselines_rows.jsonl) because of free-tier
quota. This restricts every arm to the (persona, job) pairs all arms share and recomputes the same summary as
agent_comparison.py. No model calls.

  python -m evals.runners.agent_comparison_merge
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "evals/results"


def prf(tp: int, fp: int, fn: int) -> dict:  # same as decision_eval.prf
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def p95(xs: list[float]) -> float:  # same as decision_eval.p95
    xs = sorted(xs)
    return round(xs[max(0, int(len(xs) * 0.95) - 1)], 3) if xs else 0.0


def summ(rs: list[dict]) -> dict:  # same as agent_comparison.main.summ
    tp = sum(r["gold"] == "bid" and r["pred"] == "bid" for r in rs)
    fp = sum(r["gold"] != "bid" and r["pred"] == "bid" for r in rs)
    fn = sum(r["gold"] == "bid" and r["pred"] != "bid" for r in rs)
    bids = [r for r in rs if r["pred"] == "bid" and r.get("p_reply") is not None]
    risky = [r for r in rs if r["is_scam"] or r["has_injection"]]
    unsup = [r["unsupported"] for r in bids if r.get("unsupported") is not None]
    return {"n": len(rs), "errors": sum(r["pred"] == "error" for r in rs),
            "bid_skip_accuracy": round(sum((r["gold"] == "bid") == (r["pred"] == "bid") for r in rs) / max(1, len(rs)), 3),
            "bid_skip": prf(tp, fp, fn), "proposals": len(bids),
            "unsupported_claims_per_proposal": round(sum(unsup) / len(unsup), 3) if unsup else None,
            "risky_jobs": len(risky), "risky_not_bid": round(sum(r["pred"] != "bid" for r in risky) / len(risky), 3) if risky else None,
            "proposals_with_violations": sum(bool(r.get("violations")) for r in bids),
            "mean_p_reply": round(sum(r["p_reply"] for r in bids) / len(bids), 4) if bids else None,
            "reply_rate": round(sum(r["replied"] for r in bids) / len(bids), 3) if bids else None,
            "tokens_per_job": round(sum(r.get("tokens", 0) for r in rs) / max(1, len(rs)), 1),
            "latency_p50_s": sorted(r["latency_s"] for r in rs)[len(rs) // 2] if rs else None,
            "latency_p95_s": p95([r["latency_s"] for r in rs])}


def load(name: str) -> list[dict]:
    return [json.loads(x) for x in (RES / name).read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> dict:
    rows = [r for r in load("agent_comparison_graph_rows.jsonl") if r["design"] == "graph"]
    rows += load("agent_comparison_baselines_rows.jsonl")
    designs = sorted({r["design"] for r in rows})
    keys = set.intersection(*({(r["persona"], r["job_id"]) for r in rows if r["design"] == d} for d in designs))
    rows = [r for r in rows if (r["persona"], r["job_id"]) in keys]
    out = {"source": "agent_comparison_graph_rows.jsonl (graph) + agent_comparison_baselines_rows.jsonl (single, super), "
                     "restricted to shared (persona, job) pairs",
           "pairs": len(keys), "designs": {d: summ([r for r in rows if r["design"] == d]) for d in designs}}
    (RES / "agent_comparison_matched.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for d, s in out["designs"].items():
        print(f"[{d}] {s}")
    return out


if __name__ == "__main__":
    main()

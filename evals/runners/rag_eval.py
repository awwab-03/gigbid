"""Retrieval evaluation (B4): evidence Recall@5, MRR and nDCG@10 per variant, persona and job type.

Unit of evidence = portfolio project (case study + repo + reviews + blurbs + proposals citing it),
because that is what a proposal cites. Gold relevance grade = number of the job's requirements the
project proves (explicit or implied skills). "Relevant" for Recall/MRR = grade >= 2 when any
project reaches 2, else grade >= 1. Recall@5 is capped: hits / min(5, |relevant|).

  python -m evals.runners.rag_eval                     # all variants, all personas
  python -m evals.runners.rag_eval --variants v0_naive v2_hybrid --limit 40
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from rag.index.store import get_index
from rag.retriever import VARIANTS, get_variant

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "evals" / "datasets" / "dev"
RES = ROOT / "evals" / "results"
PERSONAS = ["ml_engineer", "fullstack_dev", "data_analyst"]


def load_jobs() -> dict[str, dict]:
    return {j["job_id"]: j for j in json.loads((ROOT / "gigsim" / "data" / "jobs.json").read_text(encoding="utf-8"))}


def eval_set(persona: str, limit: int | None) -> list[dict]:
    rows = [json.loads(line) for line in (DEV / f"{persona}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r["gold_evidence"] and not r["is_duplicate"] and not r["is_scam"]]
    return rows[:limit] if limit else rows


def job_types(job: dict, gold: dict) -> list[str]:
    t = ["all"]
    t.append("4plus_requirements" if len(gold["requirements"]) >= 4 else "under4_requirements")
    if not job["required_skills"]:
        t.append("vague_post")
    if gold["decision"] == "skip":
        t.append("should_skip")
    if gold["has_injection"]:
        t.append("injection")
    return t


def metrics(ranked: list[str], gold: list[dict]) -> dict:
    grade = {g["project"]: g["grade"] for g in gold}
    thr = 2 if max(grade.values()) >= 2 else 1
    rel = {p for p, g in grade.items() if g >= thr}
    top5 = ranked[:5]
    recall5 = len(rel & set(top5)) / min(5, len(rel))
    mrr = next((1.0 / (i + 1) for i, p in enumerate(ranked) if p in rel), 0.0)
    dcg = sum((2 ** grade.get(p, 0) - 1) / math.log2(i + 2) for i, p in enumerate(ranked[:10]))
    ideal = sorted(grade.values(), reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return {"recall@5": recall5, "mrr": mrr, "ndcg@10": dcg / idcg if idcg else 0.0}


def run(variants: list[str], personas: list[str], limit: int | None) -> dict:
    jobs = load_jobs()
    out: dict = {"variants": {}, "n_jobs": {}, "definition": __doc__.strip().splitlines()[0]}
    per_job_rows = []
    for v in variants:
        mod = get_variant(v)
        agg: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        lat: list[float] = []
        for p in personas:
            idx = get_index(p)
            rows = eval_set(p, limit)
            out["n_jobs"][p] = len(rows)
            for g in rows:
                job = jobs[g["job_id"]]
                t0 = time.perf_counter()
                res = mod.retrieve(job, idx, k=10)
                lat.append(time.perf_counter() - t0)
                m = metrics([pr for pr, _ in res.ranked_projects], g["gold_evidence"])
                for jt in job_types(job, g):
                    for key in (f"{p}|{jt}", f"ALL|{jt}"):
                        for mk, mv in m.items():
                            agg[key][mk].append(mv)
                per_job_rows.append({"variant": v, "persona": p, "job_id": g["job_id"], **{k: round(x, 4) for k, x in m.items()},
                                     "unsupported_reqs": len(res.unsupported_requirements)})
        lat.sort()
        out["variants"][v] = {
            "breakdown": {k: {mk: round(sum(vals) / len(vals), 4) for mk, vals in d.items()} | {"n": len(d["mrr"])}
                          for k, d in sorted(agg.items())},
            "latency_s": {"p50": round(lat[len(lat) // 2], 4), "p95": round(lat[int(len(lat) * 0.95) - 1], 4)},
        }
        o = out["variants"][v]["breakdown"]["ALL|all"]
        print(f"{v:16s} R@5={o['recall@5']:.3f} MRR={o['mrr']:.3f} nDCG@10={o['ndcg@10']:.3f} p95={out['variants'][v]['latency_s']['p95']}s n={o['n']}")
    RES.mkdir(parents=True, exist_ok=True)
    suffix = "" if not limit else f"_limit{limit}"
    (RES / f"rag_variants{suffix}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    with (RES / f"rag_per_job{suffix}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_job_rows[0].keys()))
        w.writeheader()
        w.writerows(per_job_rows)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="*", default=VARIANTS)
    ap.add_argument("--personas", nargs="*", default=PERSONAS)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(a.variants, a.personas, a.limit)

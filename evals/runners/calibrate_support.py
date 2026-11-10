"""Calibrate the 'requirement is supported' threshold on reranker logits (dev set only).

Positive = the persona truly has the requirement's skill (gold); negative = it does not.
Score = best cross-encoder logit over the hybrid candidates for that requirement.
Objective: Youden J (TPR - FPR), because positives dominate and F1 would pick "always supported".
Writes evals/results/support_threshold.json with the chosen threshold, AUC and the curve.
"""

from __future__ import annotations

import json
from pathlib import Path

from rag.index.models import embed
from rag.index.store import get_index
from rag.variants.base import extract_requirements
from rag.variants.v2_hybrid import hybrid
from rag.variants.v3_rerank import rerank

ROOT = Path(__file__).resolve().parents[2]


def main(per_persona: int = 60) -> None:
    jobs = {j["job_id"]: j for j in json.loads((ROOT / "gigsim/data/jobs.json").read_text(encoding="utf-8"))}
    accounts = {a["freelancer_id"]: set(a["skills"]) for a in json.loads((ROOT / "gigsim/data/accounts.json").read_text(encoding="utf-8"))}
    pts = []
    for persona in accounts:
        idx = get_index(persona)
        rows = [json.loads(x) for x in (ROOT / f"evals/datasets/dev/{persona}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        rows = [r for r in rows if not r["is_scam"] and not r["is_duplicate"]]
        rows = [r for r in rows if r["coverage"] < 1][: per_persona // 2] + [r for r in rows if r["coverage"] == 1][: per_persona // 2]
        for g in rows:
            job = jobs[g["job_id"]]
            reqs = extract_requirements(job)[: len(g["requirements"])]
            for text, gold in zip(reqs, g["requirements"], strict=False):
                hits = rerank(text, hybrid(idx, text, embed([text], query=True)[0], n=15))
                hits = [h for h in hits if h.meta.get("type") != "proposal"]
                pts.append({"persona": persona, "requirement": text, "skill": gold, "positive": gold in accounts[persona],
                            "score": hits[0].score if hits else -20.0})
    best = (0.0, None)
    grid = sorted({round(p["score"], 1) for p in pts})
    roc = []
    for t in grid:
        tp = sum(p["positive"] and p["score"] >= t for p in pts)
        fp = sum((not p["positive"]) and p["score"] >= t for p in pts)
        fn = sum(p["positive"] and p["score"] < t for p in pts)
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        neg = sum(not p["positive"] for p in pts) or 1
        fpr = fp / neg
        j = rec - fpr
        roc.append({"threshold": t, "precision": round(prec, 3), "recall": round(rec, 3), "fpr": round(fpr, 3), "f1": round(f1, 3),
                    "youden_j": round(j, 3)})
        if j > best[0]:
            best = (j, t)
    pos_s = [p["score"] for p in pts if p["positive"]]
    neg_s = [p["score"] for p in pts if not p["positive"]]
    auc = sum((a > b) + 0.5 * (a == b) for a in pos_s for b in neg_s) / max(1, len(pos_s) * len(neg_s))
    chosen = next(r for r in roc if r["threshold"] == best[1])
    out = {"n": len(pts), "positives": len(pos_s), "auc": round(auc, 3), "best_threshold": best[1], "youden_j": round(best[0], 3),
           "at_threshold": chosen, "curve": roc[:: max(1, len(roc) // 40)]}
    (ROOT / "evals/results/support_threshold.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "curve"}))


if __name__ == "__main__":
    main()

"""LLM-judge calibration (B4): a human labels 30 proposals blind, then we report Cohen's kappa with the judge.

  python -m evals.runners.judge_calibration make    # writes evals/judge_calibration/sheet.csv (judge scores hidden)
  # open sheet.csv in Excel, fill `your_overall_1to5` for every row (same rubric as agent/prompts/judge.md), save as CSV
  python -m evals.runners.judge_calibration score   # writes evals/results/judge_calibration.json

The 30 items are drawn from the proposal-eval rows (all arms), stratified over the judge's overall score so the
sheet is not all 4s, and shuffled; the key with the judge's scores is kept separately.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "evals" / "results"
DIR = ROOT / "evals" / "judge_calibration"
RUBRIC = ("1 = would never reply, 2 = unlikely, 3 = maybe, 4 = likely, 5 = would definitely reply. Judge relevance to THIS job, "
          "concrete past results, an opening about the client's problem, credible claims, clarity.")


def make(n: int = 30, seed: int = 7) -> None:
    jobs = {j["job_id"]: j for j in json.loads((ROOT / "gigsim/data/jobs.json").read_text(encoding="utf-8"))}
    items = []
    for f in sorted(RES.glob("proposal_eval_*_rows.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line) if line.strip() else {}
            if r.get("text") and r.get("judge"):
                items.append({"src": f.stem, "persona": r["persona"], "job_id": r["job_id"], "text": r["text"], "judge": r["judge"]["overall"]})
    rng = random.Random(seed)
    by_score: dict[int, list] = {}
    for it in items:
        by_score.setdefault(it["judge"], []).append(it)
    for v in by_score.values():
        rng.shuffle(v)
    picked = []
    while len(picked) < min(n, len(items)):  # round-robin over judge scores = stratified sample
        for s in sorted(by_score):
            if by_score[s] and len(picked) < n:
                picked.append(by_score[s].pop())
    rng.shuffle(picked)
    DIR.mkdir(parents=True, exist_ok=True)
    with (DIR / "sheet.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "job_title", "job_excerpt", "proposal", "your_overall_1to5", "rubric"])
        for i, it in enumerate(picked, 1):
            job = jobs[it["job_id"]]
            w.writerow([i, job["title"], job["description"][:500], it["text"], "", RUBRIC if i == 1 else ""])
    (DIR / "key.json").write_text(json.dumps([{"item": i, **{k: it[k] for k in ("src", "persona", "job_id", "judge")}}
                                              for i, it in enumerate(picked, 1)], indent=2), encoding="utf-8")
    print(f"wrote {len(picked)} items to {DIR / 'sheet.csv'} (judge score distribution: "
          f"{ {s: sum(it['judge'] == s for it in picked) for s in sorted({it['judge'] for it in picked})} })")


def kappa(a: list[int], b: list[int], k: int = 5, weights: str = "quadratic") -> float:
    n = len(a)
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        obs[x - 1][y - 1] += 1
    ra = [sum(row) for row in obs]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]

    def w(i: int, j: int) -> float:
        if weights == "quadratic":
            return ((i - j) ** 2) / ((k - 1) ** 2)
        return 0.0 if i == j else 1.0

    num = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w(i, j) * ra[i] * rb[j] / n for i in range(k) for j in range(k))
    return 1 - num / den if den else 1.0


def score() -> None:
    key = {it["item"]: it for it in json.loads((DIR / "key.json").read_text(encoding="utf-8"))}
    human, judge = [], []
    with (DIR / "sheet.csv").open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            v = (row.get("your_overall_1to5") or "").strip()
            if v:
                human.append(int(float(v)))
                judge.append(int(key[int(row["item"])]["judge"]))
    if len(human) < len(key):
        print(f"only {len(human)}/{len(key)} items labelled", file=sys.stderr)
    out = {"n": len(human), "quadratic_weighted_kappa": round(kappa(human, judge), 3), "unweighted_kappa": round(kappa(human, judge, weights="none"), 3),
           "exact_agreement": round(sum(h == j for h, j in zip(human, judge, strict=True)) / len(human), 3),
           "within_one": round(sum(abs(h - j) <= 1 for h, j in zip(human, judge, strict=True)) / len(human), 3),
           "mean_human": round(sum(human) / len(human), 2), "mean_judge": round(sum(judge) / len(judge), 2)}
    (RES / "judge_calibration.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    {"make": make, "score": score}[sys.argv[1] if len(sys.argv) > 1 else "make"]()

"""X2 signature extension: A/B test of two proposal strategies in GigSim, with significance tests.

Both arms are produced by evals/runners/proposal_eval.py on the SAME fixed job set (first N gold-bid dev jobs per
persona), so proposals are paired by (persona, job_id):
  * reply (binary GigSim outcome): McNemar's exact test on the discordant pairs (two-sided binomial, p = 0.5);
  * the simulated client's reply probability p_reply: Wilcoxon signed-rank test on the paired differences,
    plus a paired bootstrap 95% CI of the mean difference;
  * unpaired two-proportion z-test on reply rate, for reference.

  python -m evals.runners.ab_test --a proposal_eval_open_v8_open --b proposal_eval_planfirst_v8_open
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "evals" / "results"
REPLIED = ("replied", "interview", "hired")


def load(name: str) -> dict[tuple[str, str], dict]:
    rows = [json.loads(x) for x in (RES / f"{name}_rows.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return {(r["persona"], r["job_id"]): r for r in rows if r.get("submitted")}


def run(a_name: str, b_name: str, seed: int = 7) -> dict:
    A, B = load(a_name), load(b_name)
    keys = sorted(set(A) & set(B))
    ra = [A[k].get("outcome") in REPLIED for k in keys]
    rb = [B[k].get("outcome") in REPLIED for k in keys]
    pa = [float(A[k].get("p_reply") or 0) for k in keys]
    pb = [float(B[k].get("p_reply") or 0) for k in keys]
    n = len(keys)
    b_only = sum((not x) and y for x, y in zip(ra, rb, strict=True))
    a_only = sum(x and (not y) for x, y in zip(ra, rb, strict=True))
    mcnemar_p = stats.binomtest(min(a_only, b_only), a_only + b_only, 0.5).pvalue if a_only + b_only else 1.0
    diffs = [y - x for x, y in zip(pa, pb, strict=True)]
    wil = stats.wilcoxon(diffs) if any(diffs) else None
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(5000)) if n else [0.0]
    p1, p2 = sum(ra) / max(1, n), sum(rb) / max(1, n)
    pool = (sum(ra) + sum(rb)) / max(1, 2 * n)
    se = math.sqrt(pool * (1 - pool) * 2 / n) if n and 0 < pool < 1 else 0
    z = (p2 - p1) / se if se else 0.0
    # minimum detectable difference in reply rate at alpha .05, power .8, for this n (unpaired approximation)
    mde = (1.96 + 0.84) * math.sqrt(2 * pool * (1 - pool) / n) if n and 0 < pool < 1 else None
    by_persona = {}
    for p in sorted({k[0] for k in keys}):
        ks = [i for i, k in enumerate(keys) if k[0] == p]
        by_persona[p] = {"n": len(ks), "reply_A": round(sum(ra[i] for i in ks) / len(ks), 3), "reply_B": round(sum(rb[i] for i in ks) / len(ks), 3),
                         "mean_p_reply_A": round(sum(pa[i] for i in ks) / len(ks), 4), "mean_p_reply_B": round(sum(pb[i] for i in ks) / len(ks), 4)}
    return {"arm_A": a_name, "arm_B": b_name, "n_pairs": n,
            "reply_rate_A": round(p1, 4), "reply_rate_B": round(p2, 4),
            "discordant": {"A_only_replied": a_only, "B_only_replied": b_only}, "mcnemar_exact_p": round(float(mcnemar_p), 4),
            "two_proportion_z": round(z, 3), "two_proportion_p": round(float(2 * (1 - stats.norm.cdf(abs(z)))), 4),
            "mean_p_reply_A": round(sum(pa) / max(1, n), 4), "mean_p_reply_B": round(sum(pb) / max(1, n), 4),
            "mean_diff_p_reply_B_minus_A": round(sum(diffs) / max(1, n), 4),
            "bootstrap95_ci_diff": [round(boots[int(0.025 * len(boots))], 4), round(boots[int(0.975 * len(boots)) - 1], 4)],
            "wilcoxon_p": round(float(wil.pvalue), 4) if wil else None,
            "min_detectable_reply_diff_80pct_power": round(mde, 3) if mde else None, "by_persona": by_persona}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", default="ab_test_x2")
    a = ap.parse_args()
    res = run(a.a, a.b)
    (RES / f"{a.out}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()

"""30-job smoke eval for every pull request (E2). Fails (exit 1) if bid-or-skip F1, scam recall or
retrieval Recall@5 drop below, or unsupported claims rise above, the thresholds in
evals/thresholds.yaml."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    th = yaml.safe_load((ROOT / "evals" / "thresholds.yaml").read_text(encoding="utf-8"))
    from evals.runners import decision_eval, rag_eval
    from rag.index.models import CFG

    dec = asyncio.run(decision_eval.main(10, decision_eval.PERSONAS, 4, "smoke"))
    rag = rag_eval.run([CFG["rag"]["variant"]], rag_eval.PERSONAS, 10)
    r5 = rag["variants"][CFG["rag"]["variant"]]["breakdown"]["ALL|all"]["recall@5"]
    o = dec["overall"]
    checks = {
        "bid_skip_f1": (o["bid_skip"]["f1"], ">=", th["bid_skip_f1_min"]),
        "scam_recall": (o["scam"]["recall"], ">=", th["scam_recall_min"]),
        "recall_at_5": (r5, ">=", th["recall_at_5_min"]),
        "errors": (o["errors"], "<=", th["max_errors"]),
    }
    if dec["profile"] != "fake":
        from evals.runners.proposal_eval import run as proposal_run

        prop = asyncio.run(proposal_run(limit=3, tag="smoke"))
        checks["unsupported_claims_per_proposal"] = (prop["overall"]["unsupported_after_per_proposal"], "<=", th["unsupported_claims_max"])
    failed = {k: v for k, v in checks.items() if not (v[0] >= v[2] if v[1] == ">=" else v[0] <= v[2])}
    out = {"profile": dec["profile"], "variant": CFG["rag"]["variant"], "checks": checks, "failed": list(failed)}
    (ROOT / "evals" / "results" / "smoke_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for k, (v, op, t) in checks.items():
        print(f"{'FAIL' if k in failed else 'ok  '} {k}: {v} {op} {t}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

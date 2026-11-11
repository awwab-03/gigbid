# ADR 0004: Which retrieval variant ships

**Status.** Accepted, 11 Nov 2026. `agent/config.yaml: rag.variant = v8_crag` (override per run with `RAG_VARIANT`).

**Evidence.** `evals/runners/rag_eval.py` on all 450 dev jobs (150 per persona), `evals/results/rag_variants.json`:

| Variant | Recall@5 | MRR | nDCG@10 |
|---|---|---|---|
| V0 naive dense | 0.637 | 0.767 | 0.713 |
| V1 requirement decomposition | 0.716 | 0.781 | 0.759 |
| V2 hybrid BM25 + dense | 0.748 | 0.812 | 0.787 |
| V3 hybrid + cross-encoder rerank | 0.786 | 0.850 | 0.816 |
| V4 outcome-weighted | 0.750 | 0.805 | 0.780 |
| V5 multi-vector | 0.646 | 0.789 | 0.723 |
| **V8 corrective RAG (LangGraph)** | **0.798** | **0.873** | **0.828** |

**Decision.** Ship V8. It is best on all three metrics overall and stays strong on the hard slices (vague posts
nDCG@10 0.873, injected posts 0.843). Its p95 retrieval latency (4.1 s) is lower than V3's (7.5 s) because the
corrective step only re-queries when the cross-encoder grade is below the calibrated threshold (-7.9 logit,
`evals/results/support_threshold.json`). V5 multi-vector did not help and is not shipped.

**Downstream check.** With V8 and the open Cerebras profile, the decision eval on 150 dev jobs
(`evals/results/decision_eval_open_v8_limit50.json`) gives bid/skip F1 0.90, scam P/R 1.0/1.0, injection flag
recall 1.0, price-in-band 0.73, p95 8.6 s per job, 0 errors.

**Trade-off and the live VM.** V8 reranks every requirement's candidates with the MiniLM cross-encoder. On the
Always Free deploy VM (1 GB, a fraction of one CPU) that is too slow: measured there, 20 cross-encoder pairs take
1.5 s, V8 `match_requirements` exceeded the 20 s tool timeout, and retries pushed the load average to 11. The live
URL therefore sets `RAG_VARIANT=v2_hybrid` (no cross-encoder in retrieval; R@5 0.748 vs 0.798) and
`GIGBID_TIMEOUT_SCALE=5`, and keeps cross-encoder **claim verification** on, because that is the safety check
(a 4-claim draft verifies in 27 s there). A fresh ML job goes from analysis to awaiting approval in about 2 minutes
on the VM. Any host with a full CPU core runs V8, the default in `agent/config.yaml`.

# ADR 0004: Which retrieval variant ships

**Status.** Decided by `evals/runners/rag_eval.py` on the full dev set; see `evals/results/rag_variants.json`
and the decision paragraph in the README. The chosen variant is set in `agent/config.yaml: rag.variant`; the
support threshold (-7.9 cross-encoder logit) was calibrated separately (`evals/results/support_threshold.json`).

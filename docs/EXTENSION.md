# Signature extension: X2 Proposal experiments

**What.** Two proposal strategies run as an A/B test in GigSim on the same fixed job set, with significance tests
on the reply rate.

| Arm | Strategy | Prompt |
|---|---|---|
| A | **Evidence-led** (the shipped writer): open with the client's problem, then the single most relevant project and its result, cited | `agent/prompts/writer.md` |
| B | **Plan-first**: open with a 2-3 step delivery plan that names the client's own deliverables and a rough timeline, then one short cited proof point | `agent/prompts/writer_plan.md` |

Everything else is identical: same graph, verifier, Critic, Compliance Guard, retrieval (V8), model profile
(`open`), job set (first 10 gold-bid dev jobs per persona) and simulator. The arm is selected with
`WRITER_STRATEGY=writer|writer_plan` (`agent/nodes/writer.py`).

## Pre-registered hypothesis (committed before arm B was run)

GigSim's client model (`gigsim/client_model.py`) rewards must-have skill coverage, specificity (numbers and named
past projects), personalisation (job words in the first two sentences) and a preferred length, and penalises
generic openings and fabricated skills. Plan-first should raise personalisation (the opening names the client's
deliverables) but lower specificity (one proof point, fewer numbers).

* **H1:** arm B's mean simulated reply probability differs from arm A's. Two-sided, alpha = 0.05.
* **Prediction:** B is *not* better: the specificity loss outweighs the personalisation gain, so the mean
  difference B - A in `p_reply` is <= 0.
* With about 30 pairs, a reply-rate difference smaller than roughly 0.3 is undetectable at 80% power (computed
  and reported by the test), so the paired test on `p_reply` is the primary analysis and the binary reply rate
  is secondary.

## Measurement

`evals/runners/ab_test.py` pairs proposals by (persona, job_id):

* reply (binary GigSim outcome): McNemar's exact test on discordant pairs;
* `p_reply` (the simulated client's reply probability): Wilcoxon signed-rank test and a paired bootstrap 95% CI;
* unpaired two-proportion z-test on reply rate, plus the minimum detectable difference, for reference.

```bash
MODEL_PROFILE=open RAG_VARIANT=v8_crag python -m evals.runners.proposal_eval --limit 10 --tag open_v8
MODEL_PROFILE=open RAG_VARIANT=v8_crag WRITER_STRATEGY=writer_plan python -m evals.runners.proposal_eval --limit 10 --tag planfirst_v8
python -m evals.runners.ab_test --a proposal_eval_open_v8_open --b proposal_eval_planfirst_v8_open
```

## Results

Filled in from `evals/results/ab_test_x2.json` after both arms ran.

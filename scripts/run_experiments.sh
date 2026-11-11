#!/usr/bin/env bash
# Real-model experiments for the report. Results land in evals/results/.
#   bash scripts/run_experiments.sh gptoss   # runs that need gpt-oss-120b (free tier: 5 req/min, 150 req/h, 1M tokens/day)
#   bash scripts/run_experiments.sh qwen     # everything else, on qwen-3.8-27b (450 req/min)
# The two queues can run at the same time: they use different models' rate limits.
set -u
set -a; . ./.env; set +a
unset DATABASE_URL REDIS_URL
export LANGSMITH_TRACING=false MCP_TRANSPORT=inproc MARKETPLACE_RPM=600 PYTHONUNBUFFERED=1
export JUDGE_MODEL=qwen-3.8-27b          # one judge for every arm (calibrated in evals/results/judge_calibration.json)
export LLM_PACE=gpt-oss-120b=2.4         # stay under 150 requests/hour so gpt-oss calls do not fall back to qwen
PY=.venv/Scripts/python; [ -x "$PY" ] || PY=.venv/bin/python
run() { echo "=== $(date +%T) $*"; env "$@" 2>&1 | grep -E "^\[|Traceback|Error:" | tail -4; }

case "${1:-qwen}" in
gptoss)
  # R&D A: tool granularity on both models
  run MCP_STATE_DIR=$TEMP/g1 $PY -m evals.runners.tool_granularity --models gpt-oss-120b qwen-3.8-27b --concurrency 2
  # model comparison at proposal level: the shipped `open` profile (gpt-oss writes and critiques)
  run MODEL_PROFILE=open RAG_VARIANT=v8_crag MCP_STATE_DIR=$TEMP/g2 $PY -m evals.runners.proposal_eval --limit 10 --concurrency 1 --tag gptoss_v8
  ;;
qwen)
  run MODEL_PROFILE=open_qwen RAG_VARIANT=v8_crag MCP_STATE_DIR=$TEMP/q1 $PY -m evals.runners.proposal_eval --limit 10 --concurrency 3 --tag qwen_v8
  run MODEL_PROFILE=open_qwen RAG_VARIANT=v0_naive MCP_STATE_DIR=$TEMP/q2 $PY -m evals.runners.proposal_eval --limit 10 --concurrency 3 --tag qwen_v0
  run MODEL_PROFILE=open_qwen RAG_VARIANT=v8_crag WRITER_STRATEGY=writer_plan MCP_STATE_DIR=$TEMP/q3 $PY -m evals.runners.proposal_eval --limit 10 --concurrency 3 --tag qwen_planfirst_v8
  run $PY -m evals.runners.ab_test --a proposal_eval_qwen_v8_open_qwen --b proposal_eval_qwen_planfirst_v8_open_qwen
  run MODEL_PROFILE=open_qwen MCP_STATE_DIR=$TEMP/q4 $PY -m evals.runners.injection_eval --jobs 4 --concurrency 3
  run MODEL_PROFILE=open_qwen RAG_VARIANT=v8_crag MCP_STATE_DIR=$TEMP/q5 $PY -m evals.runners.agent_comparison --limit 17 --concurrency 3
  ;;
esac
echo "=== $(date +%T) done ${1:-qwen}"

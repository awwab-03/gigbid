#!/usr/bin/env bash
# Real-model experiments for the report (sequential: free-tier rate limits). Results land in evals/results/.
set -u
set -a; . ./.env; set +a
unset DATABASE_URL REDIS_URL
export LANGSMITH_TRACING=false MCP_TRANSPORT=inproc MARKETPLACE_RPM=600 PYTHONUNBUFFERED=1
PY=.venv/Scripts/python; [ -x "$PY" ] || PY=.venv/bin/python
run() { echo "=== $(date +%T) $*"; env "$@" 2>&1 | grep -E "^\[|Traceback|Error" | tail -3; }
run MODEL_PROFILE=open_single RAG_VARIANT=v8_crag MCP_STATE_DIR=$TEMP/x1 $PY -m evals.runners.decision_eval --limit 50 --concurrency 2 --tag open_single_v8
run MODEL_PROFILE=open RAG_VARIANT=v0_naive MCP_STATE_DIR=$TEMP/x2 $PY -m evals.runners.decision_eval --limit 50 --concurrency 2 --tag open_v0
run MODEL_PROFILE=open RAG_VARIANT=v8_crag MCP_STATE_DIR=$TEMP/x3 $PY -m evals.runners.proposal_eval --limit 10 --concurrency 2 --tag open_v8
run MODEL_PROFILE=open RAG_VARIANT=v0_naive MCP_STATE_DIR=$TEMP/x4 $PY -m evals.runners.proposal_eval --limit 10 --concurrency 2 --tag open_v0
echo "=== $(date +%T) done"

.PHONY: install dev test e2e eval eval-full seed demo lint api-client up down freeze docs
PY ?= python

install:
	$(PY) -m pip install uv && uv pip install -e ".[dev]" && npm ci --prefix apps/web

# single-process dev: GigSim + API (in-process MCP, inline worker) + web
dev:
	$(PY) -m uvicorn gigsim.app:app --port 8081 & $(PY) scripts/dev_api.py & npm --prefix apps/web run dev

up:
	docker compose -f infra/docker-compose.yml --env-file .env up --build -d

down:
	docker compose -f infra/docker-compose.yml down

test:
	$(PY) scripts/ci_checks.py && pytest -q

e2e:
	npm --prefix apps/web run e2e

# retrieval metrics, decision metrics and a fixed GigSim reply-rate run -> evals/results/*.json
eval:
	$(PY) -m evals.runners.rag_eval
	$(PY) -m evals.runners.decision_eval --limit 50
	$(PY) -m evals.runners.proposal_eval --limit 10

eval-full: eval
	$(PY) -m evals.runners.ablation
	$(PY) -m evals.runners.judge_calibration
	$(PY) -m evals.runners.injection_eval
	$(PY) -m evals.runners.tool_granularity
	$(PY) -m evals.runners.agent_comparison
	$(PY) -m evals.runners.results_table

seed:
	$(PY) -m gigsim.seed.generate --seed 7

demo:
	$(PY) scripts/demo.py

lint:
	ruff check . && npm --prefix apps/web run lint

api-client:
	$(PY) scripts/export_openapi.py && npm --prefix apps/web run gen:api

docs:
	$(PY) scripts/gen_tools_md.py

freeze:
	$(PY) scripts/ci_checks.py --freeze

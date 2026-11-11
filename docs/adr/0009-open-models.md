# ADR 0009: Open-weight models through an OpenAI-compatible host; models per node in config

**Decision.** The `open` profile uses qwen-3.8-27b for cheap nodes and gpt-oss-120b for Writer, Critic and Liaison
on Cerebras' OpenAI-compatible API (free tier); `local` uses Ollama; `fake` is a deterministic stand-in for CI only. Every node's
model and fallback is in `agent/config.yaml`. **Why.** The deployed link must run on open models and free hosts
have no GPU; the model comparison is measured (`evals/results/model_comparison.json`).

# GigBid worker service (identical layers are shared through the build cache)
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FASTEMBED_CACHE_PATH=/app/data/processed/models
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* && pip install uv==0.7.8
COPY . .
RUN uv pip install --system -e .
RUN python -c "from rag.index.models import embedder, reranker; embedder(); reranker()"
CMD ["arq", "worker.main.WorkerSettings"]

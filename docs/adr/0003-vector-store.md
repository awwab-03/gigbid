# ADR 0003: pgvector in deployment, exact on-disk store in dev/CI

**Decision.** Postgres + pgvector (`VECTOR_BACKEND=pgvector`) is the deployed vector store; dev and CI use an
exact numpy store with the same interface. **Why.** ~250 struct + ~330 fixed chunks per persona: exact cosine
search is faster than an ANN index and has perfect recall; pgvector reuses the Postgres we already need for
checkpoints. Embeddings are cached by chunk-text hash, so re-indexing after an upload embeds only new chunks.
Embeddings (bge-small-en-v1.5) and reranker (ms-marco-MiniLM-L-6) are open and run on CPU.

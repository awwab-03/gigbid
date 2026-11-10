# ADR 0006: Exactly-once submission = checkpoint + deterministic idempotency keys

**Decision.** Submit and send keys are `sha256(thread_id | final text | amount)`; the Marketplace MCP server
stores the first result per key and GigSim rejects a second submission to the same job. **Why.** A crash after
approval resumes from the Postgres checkpoint and re-runs the `submit` node; the keys make that replay a no-op.
Tested in `tests/integration/test_bid_graph.py`.

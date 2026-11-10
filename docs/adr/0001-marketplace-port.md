# ADR 0001: One marketplace port, backend chosen inside the Marketplace MCP server

**Decision.** Agents only ever call Marketplace MCP tools. The server delegates to a GigSim or a live-Upwork
backend chosen by `MARKETPLACE_MODE`. **Why.** R1 asks that the graph cannot tell which marketplace it uses;
putting the switch behind MCP also gives both modes the same idempotency, rate limiting, audit log and
dry-run previews. **Consequence.** Live tool names are mapped in config (`live_tool_map`); an Upwork rename is a
config change, and `/health` reports unmapped operations.

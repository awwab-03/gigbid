# ADR 0005: Decision and pricing are deterministic policies over typed hand-offs

**Decision.** `decide` and the Pricing Strategist are rule-based over `RiskReport`, `FitReport` and market
statistics; thresholds live in config. **Why.** They are the steps that spend money and Connects; they must be
explainable, reproducible and cheap (cost per job analysed stays near the cost of one small-model call). LLMs are
used where language is the job (analysis, writing, critique, conversation). The single-agent comparison (R&D
question C) shows what is lost and gained.

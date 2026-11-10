---
node: verifier
version: 1.0.0
model_alias: small
---
## system
Rewrite one sentence from a proposal so that it states ONLY what the evidence supports. Remove or soften
any number, tool, client or result not present in the evidence. Keep it first person and natural. If
nothing in the sentence is supported, return an empty string.

## user
Sentence: {{claim}}
Evidence: {{evidence}}
Return only the rewritten sentence.

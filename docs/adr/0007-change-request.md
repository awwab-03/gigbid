# ADR 0007: Absorbing the platform policy update (change request)

**Context.** The assignment announced a GigSim "platform policy update" for 2 November 2026 that would add a rule or
cost affecting bidding. **No official text was published for the class** (checked on Google Classroom on 12 Nov), and
each student built their own GigSim, so the author defined the update on 12 Nov 2026, modelled on real marketplace
changes, and absorbed it the same way an official one would be.

**Policy v2** (`gigsim/policy.yaml`): Connects cost x1.5; a flat 2-Connect submission fee per proposal; at most 10
submissions per day (was 30); cover letters at most 250 words (was 5,000).

**What had to change in GigBid** (commit d988242; timed 02:29 to 02:40 PKT, about 10 minutes including the test):

| File | Lines | Why |
|---|---|---|
| `gigsim/policy.yaml` | +14 / -8 | the platform's side of the change (the v2 block), plus a deliberate checksum re-freeze |
| `agent/nodes/pricing.py` | +3 / -3 | **the only GigBid code change**: pricing read `connects_multiplier` but ignored `connects_flat_fee`, which the platform already charged |
| `agent/config.yaml` | +1 / -1 | `policy.expected_version: v2` (the UI warns when the platform's version differs) |
| `tests/integration/test_bid_graph.py` | +23 | `test_policy_v2_change_request_is_absorbed` |

Everything else was absorbed with no edit because it is read at run time from `GET /policy`: the multiplier (Pricing),
the word cap (Compliance Guard, `agent/nodes/compliance.py:54`) and the daily cap (GigSim returns 429; the marketplace
server reports `RATE_LIMITED`, and the job waits instead of failing).

**The gap it exposed.** Without the 3-line pricing fix GigBid would quote **14 Connects for a proposal the platform
charges 16** for (the new test fails on the old code with `assert 14 == 16`), so its expected-value check and its
"enough Connects" check would both be wrong under v2. Lesson: the design kept the *numbers* in configuration, but
GigBid re-implemented the platform's cost *formula*, and a formula with a term GigBid did not model is a code change.
A sturdier design would ask the platform for the cost of a specific proposal (the GigSim draft endpoint already
returns `connects_cost` in `dry_run`) instead of recomputing it.

**Impact on bidding** (`evals/results/change_request_v2_impact.json`, offline pricing on the 84 dev bids at the
shipped threshold): Connects per proposal 8.14 -> 14.26 (USD 1.22 -> 2.14 at USD 0.15 per Connect); no bid becomes
negative expected value, because job values dwarf the Connects cost; the same 84 bids need 1,198 Connects instead of
684 and, at 10 per day, nine days instead of three. The binding constraint under v2 is the Connects budget and the
daily cap, not per-job economics.

**Rollout.** `active: v1` stays the default in `gigsim/policy.yaml`, so every evaluation in `evals/results/` remains
comparable; the live deployment was switched with `POST /admin/policy?version=v2` (simulator admin endpoint).

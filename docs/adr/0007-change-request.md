# ADR 0007: Absorbing the 2 November 2026 platform policy update

**Status.** Awaiting the official change-request text. Policy is versioned in `gigsim/policy.yaml` (v1 active,
v2 placeholder) and read at run time through `marketplace.get_policy` by Pricing (Connects multiplier, fees) and
Compliance (length rules, submission caps). Expected edit: one YAML block plus, if it adds a new rule kind, one
entry in `data/policy_pack/rules.yaml`. The diff, the time it took and the line count will be recorded here.

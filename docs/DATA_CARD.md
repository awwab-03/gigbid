# Data card

All data GigBid is developed and graded on is produced by one deterministic command,
`python -m gigsim.seed.generate --seed 7` (`make seed`). Counts are recorded in `gigsim/data/seed_meta.json`.

## Sources

| Asset | Real or synthetic | Source | Licence / terms |
|---|---|---|---|
| Historical jobs for pricing statistics (1,500) | **Real titles, budgets, hourly ranges, dates, countries** when Kaggle CSVs are present in `data/raw/`; otherwise synthetic. `source` field on every row says which (`kaggle:<file>` or `synthetic`). | [Upwork Job Postings 2024 (50k)](https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records), [All Jobs on Upwork 200k+](https://www.kaggle.com/datasets/asaniczka/all-jobs-on-upwork-200k-plus) | Kaggle dataset licences (ODC-Attribution / CC as listed on each page). Raw CSVs are **not** committed (`data/raw/` is git-ignored); only derived aggregate statistics are. |
| Dev and stream jobs (840) | **Synthetic** text built around gold requirements; budgets sampled from the historical distribution | `gigsim/seed/generate.py` | Project code (MIT-style, this repo) |
| Clients (420) with hidden preferences | **Synthetic** | generator | — |
| Three freelancer personas: CV (PDF), 16-18 projects each, case studies, repo READMEs and code, reviews, profile blurbs, ~150 past proposals with outcomes | **Synthetic**; names, clients and companies are fictional and marked `(synthetic)` | `gigsim/seed/persona_specs.py` (hand-designed projects) expanded by the generator | — |
| Past-proposal outcomes (won / replied / ignored) | **Synthetic**, labelled by the same client model GigSim uses at run time | `gigsim/client_model.py` | — |
| Planted scams (6 types), prompt injections (5 templates), near-duplicate reposts | **Synthetic** | generator | — |
| Policy pack | Instructor summary, extended into machine-readable rules | `data/policy_pack/` | course material |

The starter kit (v0.1) shipped without a simulator, persona corpora or evaluation sets, so these were
built for this project (course announcement: "build it from Kaggle"). Where real data was not
available, synthetic data was generated and is labelled `synthetic: true` in every file.

## Fields

* **Job** (public view returned by GigSim): `job_id, title, description, category, required_skills, deliverables,
  budget{type,min,max}, duration_days, experience_level, screening_questions, client_id, posted_at, connects_cost,
  proposals_count, source`. Hidden fields (prefixed `_`, never served): requirements, client preferences
  (must-have skills, budget ceiling, dislike of generic openings, base reply rate), scam type, injection type and canary.
* **Gold label** (`evals/datasets/dev/<persona>.jsonl`, one per job): `decision` (bid/skip) with `skip_reasons`
  (scam, low_fit, budget_below_floor, low_client_quality, duplicate), `is_scam`, `scam_type`, `has_injection`,
  `requirements`, `coverage`, `gold_evidence` (project ids with graded relevance = number of requirements the project
  proves), `fair_price_band` (client range intersected with the freelancer's floor and the market p25).
* **Portfolio chunk metadata**: `persona, type (cv | case_study | readme | code | review | profile_item | proposal),
  project, project_title, skills, date, client_industry, outcome (proposals), cited_projects, source`.

## How the corpus defeats naive RAG (by design)

* **Implied skills**: a case study proves Celery with "a background task queue that retried failed jobs"; only the
  code file names `celery` (`gigsim/seed/skills.py` paraphrases).
* **Terse READMEs** (30% of repos with implied skills): the README alone looks irrelevant; the code carries the skills.
* **Mentioned-but-not-used** skills ("We looked at Pinecone early on but decided not to use it"): traps for retrieval
  and for claim verification.
* **Same project described three ways**: case study, README, profile blurb, plus reviews and past proposals.
* **Past proposals mirror job titles** ("Proposal for: Need a data analyst for ..."): a naive whole-post retriever
  returns proposals instead of evidence (observed; see the failure analysis).

## Dev / hidden split

Dev: seed 7, 200 jobs per persona (40% fit, 12% partial fit, 8% foreign skills, 8% low budget, 12% scams,
8% injected-but-legitimate, 5% difficult clients, 7% vague posts, 10 near-duplicates). A hidden set is produced with
another seed (`--split hidden --seed N`) into a git-ignored folder and never enters the repo; the instructor's hidden
run uses new jobs and clients against the deployed URL.

## Limitations

* Job text is template-generated and more regular than real posts; requirement extraction is easier than on real data,
  so decision and retrieval numbers are optimistic relative to live Upwork.
* The client model is rule-based and knows the freelancer's true skills. It rewards coverage, specificity,
  personalisation and fair price, and punishes fabricated skills, generic openings and off-platform contact. Reply rates
  measure agreement with those rules, not with real clients.
* Injection templates are known to the defence (the detector was written against them); an extra set of paraphrased
  attacks is used to measure generalisation (`evals/runners/injection_eval.py`).
* Pricing statistics mix real Kaggle budgets (when present) with synthetic winning bids derived from them.
* Three personas only; all in technology freelancing.

## Handling

No personal data: personas and clients are fictional. Live-mode data from a real Upwork account is never committed
(`.gitignore`), tokens are encrypted at rest, and PII is masked in logs and traces (`shared/pii.py`).

# Our agent scored 0.90 F1 while bidding on jobs that paid less than its owner's rate

*A write-up of the most surprising result from building GigBid, a multi-agent copilot for freelancers. Every number
below comes from a committed file in the project's `evals/results/` folder.*

GigBid reads freelance job posts, decides whether to bid, prices the bid and drafts a proposal grounded in the
freelancer's own portfolio. Nothing is sent without human approval. Under the hood it is a LangGraph graph: three
analysts run in parallel (a Job Analyst, a Risk Assessor that looks for scams and prompt injection, and a Fit Matcher
that maps job requirements to portfolio evidence), then a deterministic `decide` step chooses bid, watch or skip, a
deterministic `pricing` step quotes a price, and a writer, claim verifier, critic and compliance guard produce the draft.

I expected the interesting results to come from retrieval or from prompt engineering. They did not. The most
instructive result came from a single missing line in a type definition, and from the fact that a good headline
number hid it completely.

## The number that looked fine

The first full evaluation of the bid/skip decision ran the real open models over 150 labelled development jobs, 50 for
each of three synthetic freelancer personas. It scored a bid-or-skip F1 of **0.90**, accuracy 0.87, scam precision and
recall both 1.0. For a first run of a multi-agent system on messy job posts, that looked like a result to write up and
move on from.

Two smaller numbers in the same file were less flattering. Only **73%** of the bids landed inside the job's fair price
band, and every one of the 19 wrong decisions was the same kind of error: a bid on a job the gold label said to skip.
Recall was perfect (1.0) and precision was 0.82. The system was not missing good jobs; it was saying yes too often.

That asymmetry is what made me read the failures one by one instead of tuning a threshold.

## Reading 19 failures

Sorting the wrong bids by their gold skip reason split them into two groups.

Nine were jobs where the gold label said the freelancer covered only 40% of the requirements, but the Fit Matcher had
found "evidence" for five of seven. Retrieval was being generous: asked for Next.js or GraphQL experience, it returned
something loosely related. That is a retrieval problem, and the kind I expected to find.

The other five were stranger. Jobs like *j-00003*, an hourly ML job paying at most **$24/hour** to a persona whose
profile says the hourly floor is **$30**. Or *j-00044*, a fixed-price job with a $160 ceiling for a persona whose minimum
fixed project is $300. These jobs had perfect skill coverage and terrible pay. The decision rule for them is the most
boring line in the codebase:

```python
if (budget.get("max") or 0) < floor:
    reasons.append(f"budget {budget.get('max')} below your floor {floor}")
```

When I called `decide()` directly with that job and that persona's profile, it skipped the job, exactly as intended.
Inside the graph, it bid.

The pricing errors told the same story from a different angle. Of the 32 bids outside the fair band, 28 were too low,
and many were exactly **$28/hour**. Nothing in the data said $28. The pricing code did: when the profile has no hourly
floor, it falls back to a default of $20 and targets 1.4 times the floor. $20 x 1.4 = $28.

Both symptoms pointed at the same cause. Inside the graph, every node was seeing an empty freelancer profile.

## One missing line

LangGraph state is a `TypedDict`. When you invoke a graph with an input dictionary, keys that are not declared in that
schema are dropped, silently: no error, no warning. GigBid's caller passed `profile` in the input, every node read
`state.get("profile", {})`, and the state schema did not declare `profile`. So every node got `{}`. The floor was 0, no
budget was ever below it, and pricing used its defaults. The writer never saw the freelancer's name or headline either.

The fix was three lines in `agent/state.py`. The regression test that now guards it fails on the old schema with
`KeyError: 'profile'`.

After the fix, on the same 150 jobs with the same model:

| | Before | After |
|---|---|---|
| Bid/skip F1 | 0.900 | **0.950** |
| Accuracy | 0.873 | **0.940** |
| Bids inside the fair price band | 0.73 | **1.00** |
| Wrong bids on underpaid jobs | 5 | **0** |

The nine over-generous-evidence errors were still there, as they should be, because they have a different cause.

## Why nothing caught it

What surprised me was not that the bug existed but how many layers it slipped through.

**Unit tests passed**, because the unit under test was correct. `decide()` does the right thing with the profile it is
given. The bug lived in the plumbing between components, and the unit tests did not exercise the plumbing.

**Integration tests passed**, because they checked that the graph reached the approval step, that approval submitted
exactly once after a simulated crash, that scams were skipped. Every one of those behaviours is independent of the
profile.

**The type checker was satisfied.** `state.get("profile", {})` is a perfectly typed expression. The default that made
the code robust is the same default that made the bug invisible: a missing key and an empty profile look identical.

**The headline metric looked good**, because the bug only affects a minority of jobs: those whose pay is below the floor,
or hourly jobs whose price depends on it. On the rest, an empty profile changes nothing. F1 averaged the damage away.

Three things did catch it: per-category error counts (all errors were false positives), a secondary metric that had
no reason to be bad (price in band), and reading individual failures until a pattern repeated. A number like $28,
repeated across unrelated jobs, is not noise. It is a constant in someone's code.

## The fix that did not fix much

The nine remaining errors invited the obvious move: raise the bid threshold. A sweep over the saved decisions (the
decision is deterministic given the fit score, so no rerun is needed) shows that moving the threshold from 0.60 to
0.70 fixes eight of the nine and loses two good bids, lifting F1 from 0.950 to 0.982.

I shipped it, and I report it as what it is: a threshold chosen on the same 150 jobs it is evaluated on. It is an
in-sample number, and the hidden test set is the only honest check. It also does not fix the cause. The cause is that
the evidence matcher calls a requirement "supported" when it finds something merely related, and a threshold only
hides that for jobs near the line. The profile bug was the opposite case: one root cause, a three-line fix, and every
symptom gone.

## The retrieval result, in context

The comparison I designed the project around still holds, and the bug fix makes it cleaner. On the same jobs and
model, the shipped corrective-RAG retriever (V8) reaches decision F1 0.950; naive dense retrieval (V0) reaches 0.808.
The interesting part is *how* V0 fails: precision 0.97, recall 0.69. Bad retrieval did not make the agent reckless. It
made it timid. When the evidence search misses a paraphrased requirement, the Fit Matcher concludes the freelancer
lacks the skill and the agent skips a job it should have taken. Measured directly, V8 lifts evidence Recall@5 from
0.641 to 0.796 on jobs with four or more requirements.

## What I would tell myself at the start

1. **Declare every input in the graph state, and make missing inputs loud.** A `.get(key, {})` default is a decision
   about what absence means. For a freelancer's rate floor, absence should be an error, not zero.
2. **Look at the error mix before the error rate.** "All 19 errors are false positives" carried more information than
   "F1 0.90".
3. **Keep one metric per stage that should be boring.** Price in band had no reason to be 73%. When a boring metric
   is bad, something upstream is broken.
4. **Read failures until a number repeats.** $28 was the price of 42 unrelated bids. Real data does not do that; code does.

The project's evaluation harness was built to compare retrieval variants and agent architectures. Its most valuable
output so far was a reason to read 19 rows of a JSONL file.

*Code, data card and every result file: github.com/awwab-03/gigbid.*

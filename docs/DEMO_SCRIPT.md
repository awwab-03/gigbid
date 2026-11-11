# 3-minute demo script

Required beats (assignment, Portfolio Deliverables): **one job from inbox to approved proposal, one scam caught,
one injected instruction ignored, one client reply handled.** Record the live URL, signed in as the reviewer.

## Before you press record (10 minutes)

1. Sign in at https://40-233-123-21.sslip.io as the reviewer. Press **Scout now** once and wait until the inbox has
   analysed jobs (the 1 GB server takes about 2 minutes per drafted proposal; do this before recording, not on camera).
2. Make sure the inbox shows: one job **awaiting approval** (e.g. "Fine-tuning an open-source LLM on our data"),
   one **skipped as likely scam**, and one whose risk report says **prompt injection**.
   (If a beat is missing, press **Analyse** on another job and wait; ask Claude to prepare one via the simulator.)
3. For the client-reply beat you need a reply in **Messages**: approve one proposal before recording, then ask
   Claude to advance the simulator clock so the client answers (admin endpoint, simulator only).
4. Close other tabs, zoom the browser to 110%, turn notifications off. Record with OBS or the Windows Game Bar
   (Win+Alt+R), 1080p.

## Script (about 3:00)

| Time | Screen | Say (roughly) |
|---|---|---|
| 0:00-0:15 | Inbox | "GigBid is a multi-agent copilot for freelancers. It scouts jobs, decides whether to bid, and drafts proposals grounded in my own portfolio. Nothing is sent without my approval." |
| 0:15-0:35 | Inbox, point at status chips | "Three analysts run in parallel on every job: a Job Analyst, a Risk Assessor and a Fit Matcher. Here it bid on one, watched one, and skipped the rest, each with a reason." |
| 0:35-1:20 | Open the **awaiting approval** job | "The requirement-to-evidence matrix shows which requirements my portfolio proves, with links to the evidence. The draft cites evidence as E-numbers; every claim was checked against the portfolio and unsupported ones were removed before the Critic saw it. The approval card shows the price, the Connects cost and the risk report." Edit one sentence, press **Approve**. "Approval resumes the paused LangGraph thread from its Postgres checkpoint; submission uses idempotency keys, so a crash cannot spend Connects twice." |
| 1:20-1:50 | Open the **scam** job | "This one was skipped before anything was drafted: the Risk Assessor found a credential request, an unverified payment method and no hiring history. Deterministic signals first, the model only when it's ambiguous." |
| 1:50-2:20 | Open the **injection** job, scroll to the risk report | "This post hides an instruction aimed at AI tools. GigBid flags it, quarantines the span, wraps the post as untrusted data, and the draft does not follow it." (Optional, honest: "Our regex detector misses paraphrased attacks; the delimiting layer is what holds, measured in the report.") |
| 2:20-2:50 | **Messages** | "A client replied. The conversation graph classifies intent, offers free calendar slots, and drafts a reply, which again waits for my approval." Approve the reply. |
| 2:50-3:00 | **Runs** or **Analytics** | "Every run is traced and replayable. Results, the code and the evaluation files are in the repo." |

Keep it under 3:00; cut the optional sentence first. Upload unlisted to YouTube or Google Drive (anyone with the
link) and put the link in the Classroom submission.

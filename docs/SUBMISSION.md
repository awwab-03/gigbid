# Submission checklist (AI-4016 GigBid, deadline extended to Sunday 15 Nov 2026; target submission 12 Nov night)

| Deliverable | Where | Status |
|---|---|---|
| Live URL | https://40-233-123-21.sslip.io | live, policy v2 active |
| Reviewer login | private comment on Google Classroom only (never in this repo) | author posts it |
| Public repository | https://github.com/awwab-03/gigbid | done |
| R&D report, at most 10 pages | `docs/GigBid_RnD_Report.pdf` (built from `docs/REPORT.md` by `scripts/build_report.py`) | rebuilt after final results |
| 3-minute video | script: `docs/DEMO_SCRIPT.md` | author records |
| Portfolio MCP server, published | `mcp_servers/portfolio/README.md` (`uvx --from git+https://github.com/awwab-03/gigbid gigbid-portfolio-mcp`) | done, tested on clean Linux |
| Write-up, 1,200 to 1,800 words | `docs/WRITEUP.md`, posted on LinkedIn or Medium | author posts it |
| Optional ZIP | `git archive` of the tagged commit | optional |

## Resume bullet

- Built GigBid, a LangGraph multi-agent copilot that decides, prices and drafts freelance bids with human approval,
  three MCP servers and corrective RAG; lifted evidence Recall@5 from 0.64 to 0.80 and bid/skip F1 from 0.81 to 0.95.
- Found through failure analysis a silent state-schema bug that mispriced 27% of bids; fixed with a regression test
  and deployed the system on a 1 GB free-tier VM with open models only.

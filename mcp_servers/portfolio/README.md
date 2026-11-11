# GigBid Portfolio MCP server

An MCP server that answers one question for any agent writing about a freelancer: **"what evidence do I actually
have for this?"** It indexes a portfolio (CV, case studies, repos, client reviews, past proposals) with hybrid
retrieval, matches job requirements to evidence, and checks a drafted proposal claim by claim. Read-only.

## Install and run

Requires [uv](https://docs.astral.sh/uv/). No clone needed:

```bash
uvx --from git+https://github.com/awwab-03/gigbid gigbid-portfolio-mcp --stdio --portfolio /path/to/my_portfolio
```

To try it on the bundled synthetic persona, clone the repo and run from its root (the sample personas live in
`data/personas/`):

```bash
git clone https://github.com/awwab-03/gigbid && cd gigbid
uvx --from . gigbid-portfolio-mcp --stdio --portfolio data/personas/ml_engineer
```

First start downloads two small ONNX models (bge-small-en-v1.5 embedder, MiniLM cross-encoder, about 90 MB) and
embeds the portfolio once; the embeddings are cached in `<portfolio>/.gigbid_cache/`.

**Claude Desktop / Cursor** (`mcpServers` entry):

```json
{
  "gigbid-portfolio": {
    "command": "uvx",
    "args": ["--from", "git+https://github.com/awwab-03/gigbid", "gigbid-portfolio-mcp", "--stdio",
             "--portfolio", "/path/to/my_portfolio"]
  }
}
```

**MCP Inspector:** `npx @modelcontextprotocol/inspector uvx --from git+https://github.com/awwab-03/gigbid gigbid-portfolio-mcp --stdio --portfolio /path/to/my_portfolio`.
On Windows write the path with forward slashes (`C:/Users/me/portfolio`): the Inspector's argument parser strips
backslashes, and the server then stops with "portfolio folder not found". Screenshots of the server in the
Inspector: [tool list](../../docs/images/inspector/01_tools_list.jpg),
[a structured `search_evidence` call](../../docs/images/inspector/02_search_evidence_call.jpg),
[input validation](../../docs/images/inspector/03_input_validation.jpg).

**Streamable HTTP** (how GigBid itself runs it): omit `--stdio`; it serves `http://0.0.0.0:8091/mcp` and requires a
bearer service token signed with `MCP_SHARED_SECRET` (`shared/security.py`); `MCP_AUTH_REQUIRED=0` disables auth
for local experiments only.

## Portfolio folder layout

Same layout as `data/personas/ml_engineer/`; every file is optional except at least one source of evidence.

| Path | Content |
|---|---|
| `cv.pdf` | CV, split by section |
| `case_studies/*.md` | one case study per project; front matter `project`, `skills`, `client`, `outcome` |
| `repos/<project>/` | READMEs and code, chunked by file |
| `reviews.json` | client reviews `[{project, rating, text}]` |
| `proposals.json` | past proposals with outcomes (won / replied / ignored) |
| `projects.json` | project index `[{id, title, skills, ...}]` |
| `profile.json` | name, headline, years, rate floor |

## Tools

| Tool | What it returns |
|---|---|
| `search_evidence(requirement, k, types, project, since, outcome)` | ranked evidence chunks with ids, type, project, snippet |
| `match_requirements(requirements)` | per requirement: supported or not, best evidence, top projects |
| `verify_claims(text, evidence_ids)` | each claim labelled supported / partly / unsupported, plus a fixed text with unsupported claims removed |
| `get_case_study(project_id)` | the full case study |
| `list_skills()` | skill -> projects that name it |
| `get_proposal(proposal_id)` | a past proposal with its outcome |

All tools are annotated read-only and idempotent. Resources: `portfolio://cv`, `portfolio://case/{id}`,
`portfolio://proposal/{id}`, `portfolio://repo/{id}`. Prompts: answer a screening question, write a specific
opening, build a requirement-to-evidence matrix.

Retrieval variant: `RAG_VARIANT` (default `v8_crag`, corrective RAG; `v2_hybrid` is faster on small CPUs). Results
behind that choice: `evals/results/rag_variants.json` and `docs/adr/0004-shipped-rag-variant.md`.

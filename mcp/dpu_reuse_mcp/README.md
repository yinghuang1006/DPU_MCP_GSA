# DPU Data Reuse MCP Server

A read-only MCP server that answers questions about how NIH dbGaP datasets are reused in published research.

**Category:** Service "Read" Integration

## What it does

An AI agent asks a question in plain English. The MCP server calls the right tool, reads the DPU pipeline results snapshot, and returns structured data. The AI writes a readable answer with evidence quotes.

| Tool | Question it answers |
| --- | --- |
| `find_studies` | Which study (phs) matches this name? |
| `find_data_reusers` | Who is reusing this dataset? |
| `find_reuse_data_sources` | Where do people get the data they reuse? |
| `find_reuse_funders` | Who funds the reuse? |

Input: a dbGaP phs accession (e.g. `phs001493`), a seed-paper PMID (e.g. `29301960`), or words from the study title (e.g. `HTAN`).

## Architecture

```
User question
    |
    v
AI model (gpt-6-astra, Responses API)
    |  picks a tool, sends input
    v
MCP server (FastMCP, Databricks App dpu-reuse-mcp)
    |  reads CSV snapshot, filters, counts
    v
Structured result (JSON: counts, paper list, quotes, caveats)
    |
    v
AI model writes the answer
```

The server is stateless and read-only. It never runs the pipeline tools, never writes data, and never calls external services.

## Files

| File | What it does |
| --- | --- |
| `server.py` | FastMCP server: 4 tool definitions, landing page, health check |
| `reuse_data.py` | Query logic: load CSVs, resolve inputs, search/filter/count |
| `app.yaml` | Databricks App config |
| `requirements.txt` | `fastmcp>=4.1,<5`, `pydantic>=2.0`, `pandas>=2.0` |
| `data/` | Pipeline results snapshot (CSV + JSON, as of 2026-10-25) |

## Run locally

```bash
pip install fastmcp pydantic pandas
python server.py
# Starts on stdio; connect with any MCP client
```

## Deploy on Databricks Apps

The app `dpu-reuse-mcp` is deployed from this folder. MCP endpoint: `https://<app-url>/mcp`. Health check: `https://<app-url>/health`.

To redeploy after a code or data change:
1. Edit files in this folder.
2. On the app page, click **Deploy** and select this folder.

## Evaluation

See `../eval/` for the full test suite and report:
* `run_eval` notebook: 24 tool-level tests (pass/fail, speed)
* `agent_test` notebook: 16 plain-English questions scored on tool choice, input, answer
* `EVALUATION.md`: method, metrics, security, lessons, recommendations

Latest live results (2026-11-17): 24/24 tool tests, 16/16 agent tests (3 runs, 48/48 consistency).

## Data

The `data/` folder is a frozen copy of the DPU pipeline results. Key files:
* `studies.json`: 47 dbGaP studies with titles, seed PMIDs, tool-run status
* `papers.csv`: Tool 1 decisions (accession named in paper)
* `tool2_papers.csv`: Tool 2 decisions (cites seed paper)
* `pathways.csv`: where reusers say they got the data
* `grants.csv`: funders named in reuse papers

To refresh: replace the CSV/JSON files with new pipeline output and redeploy.

## Design decisions

* **Goal-based tools, not API wrappers.** Each tool answers a user question, not a database operation.
* **Pydantic input validation.** Length and range limits catch bad input before any data is read.
* **Snapshot, not live queries.** Fast, safe, and every answer is traceable to a reviewed pipeline run.
* **Study-name search.** Users can say "HTAN" instead of memorising phs002371. Ambiguous names list candidates instead of guessing.
* **Stateless HTTP.** Required by the Databricks Genie Code MCP connector.

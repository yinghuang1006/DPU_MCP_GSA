# DPU Data Reuse MCP Server (GSA MCP Hackathon)

A read-only MCP server that answers: **who reuses an NIH dbGaP dataset, where they get the data, and who funds the reuse.**
Input: a dbGaP phs accession, the PMID of the paper that generated the data, or a study name (e.g. "HTAN").

Category: Service "Read" Integration

## Where things are

| Folder | What it is |
| --- | --- |
| [`mcp/dpu_reuse_mcp/`](mcp/dpu_reuse_mcp/) | The MCP server: 4 tools, data snapshot, README with architecture and design decisions |
| [`mcp/eval/`](mcp/eval/) | Evaluation: 24 tool tests, 16 agent questions, live results, `EVALUATION.md` / `EVALUATION.docx`, slide text |
| [`app/dpu_demo/`](app/dpu_demo/) | Demo web app (Streamlit) with an "Ask the data" chat page that calls the MCP tools |

## Results (live, 2026-11-17)

* Tool tests: 24/24 pass, median 0.069 s per call
* Agent tests (gpt-6-astra, 3 runs): 48/48 pass on right tool, right input, right answer

## Where the data comes from

The `data/` snapshot (2026-10-25, 47 dbGaP studies) was produced by the DPU pipeline, which finds papers that name a dbGaP study or cite its seed paper, classifies reuse with rule-based evidence, and extracts data sources and funders from the full text. The pipeline code is maintained separately and is not part of this submission. All data is from public sources (Europe PMC, NCBI, dbGaP).

## Run locally

```bash
cd mcp/dpu_reuse_mcp
pip install -r requirements.txt
python main.py   # MCP server over stdio
```

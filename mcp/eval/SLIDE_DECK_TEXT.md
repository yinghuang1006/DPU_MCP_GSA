# Slide Deck Text — DPU Data Reuse MCP Server

Copy each slide's content into the corresponding slide of `MCP-hackathon-sample-deck.pptx`.
Replace the CDC PLACES example text. Add your screenshots where noted.

---

## Slide 1: Title

**DPU Data Reuse MCP Server**

Who reuses NIH datasets, where do they get the data, and who funds the reuse?

Category: Service "Read" Integration
Team: Ying Huang, NIH/NCI
Date: November 2026

---

## Slide 2: The Challenge

**Tracking how NIH-funded datasets are reused is manual and fragmented**

### 1. No single place to ask
NIH program officers, repositories and data-sharing policy staff need to know: did shared data get reused? By whom? Funded by whom? Today this requires searching PubMed, reading papers, and manually matching accessions to studies.

### 2. Evidence is scattered across papers
A reuse claim lives in one sentence of one section of one paper. The accession (phs number) may appear in methods, data availability, or acknowledgements. Different papers use different wording.

### 3. Linking datasets to funders requires multiple steps
Finding that a reuse paper was funded by NIH/NCI means reading the paper's funding section, normalising funder names, and connecting them back to the dataset.

### 4. No programmatic access for AI agents
Even after a pipeline extracts these facts, there is no standard interface for an AI assistant or another tool to query them.

---

## Slide 3: The Solution

**A read-only MCP server over the DPU pipeline results**

Four goal-based tools that an AI agent can call:

| Tool | Question it answers |
| --- | --- |
| `find_studies` | Which study matches this name? |
| `find_data_reusers` | Who is reusing this dataset? |
| `find_reuse_data_sources` | Where do people get the data? |
| `find_reuse_funders` | Who funds the reuse? |

Input: phs accession, seed-paper PMID, or study name (e.g. "HTAN")

The AI picks the right tool, calls it, and writes a readable answer with evidence quotes. Users can check every number against the raw tool output.

Data: snapshot of 47 dbGaP studies, \~600 reuse papers, from the DPU pipeline (2026-10-25).

---

## Slide 4: Server Design Overview

**Architecture**

```
User question  -->  AI model (gpt-6-astra, Responses API)
                       |  picks tool, sends input
                       v
                    MCP server (FastMCP, Databricks App)
                       |  reads CSV snapshot, filters, counts
                       v
                    Structured JSON result
                       |  counts, paper list, quotes, caveats
                       v
                    AI model writes the answer
```

Key points:
* The server is stateless and read-only. It never runs the pipeline, writes data, or calls external services.
* Facts come from the tool; presentation comes from the AI. The trace lets users check.
* Deployed as a Databricks App (`dpu-reuse-mcp`). MCP endpoint at `/mcp`.

---

## Slide 5: Key Technical Decisions

### 1. Goal-based tools, not API wrappers
Each tool answers a user question ("who funds the reuse?"), not a database operation ("query grants.csv"). This lets the AI choose the right tool from the description alone — verified by the agent test (16/16).

### 2. Snapshot, not live queries
* Fast: median 0.069 s per call
* Safe: no network calls, no writes
* Traceable: every answer ties to a reviewed pipeline run
* Trade-off: data must be refreshed manually

### 3. Study-name search
Users said "HTAN", not "phs002371". Added `find_studies` after a user test exposed the gap. Ambiguous names ("neuroblastoma" matches 3 studies) list candidates instead of guessing.

### 4. Pydantic input validation
String length and numeric limits reject bad input before any data is read. Tested by cases C18, C20.

---

## Slide 6: Key Technical Decisions (continued)

### 5. Stateless HTTP for Genie Code
`stateless_http=True` is required by the Databricks Genie Code MCP connector. Without it, the connector silently fails.

### 6. OpenAI Responses API for tool calling
The workspace's chat models rejected tools through Chat Completions (a reasoning-effort setting conflicts). The Responses API (`/ai-gateway/openai/v1/responses`) works. This is also why the Playground showed no "Tools" button.

### 7. Facts from the tool, presentation from the AI
The AI grouped HTAN papers into themes and shortened a quote. This is useful but unchecked by the pipeline. Lesson: keep quotes exact through instructions; build anything that should be counted as a tool; always show the trace.

---

## Slide 7: Demo

**"Ask the data" chat page** (Streamlit, inside the dpu-demo Databricks App)

[INSERT SCREENSHOT 1: HTAN question and answer]

[INSERT SCREENSHOT 2: "How this answer was made" trace showing tool call and raw result]

The user types a question. The AI calls the right MCP tool(s), gets structured data, and writes the answer. Every answer shows which tool was called, with which input, and the raw JSON result.

Example questions:
* "Who is reusing the HTAN data, and who funds that reuse?"
* "Where did researchers get the phs000452 data?"
* "What is the phs number for the melanoma genome sequencing project?"

---

## Slide 8: Evaluation Setup

**Framework:** Notebook-based on Databricks serverless compute (no Arize Phoenix)
**Model:** `models.ai.gpt-6-astra` (OpenAI Responses API)
**Test identity:** Inspector Gadget (shared service principal, UC secret)

### Two test layers

| Layer | What it tests | Dataset |
| --- | --- | --- |
| Tool test (`run_eval`) | Each tool returns the right value for a known input | 24 cases, 7 categories |
| Agent test (`agent_test`) | An AI picks the right tool, passes the right input, and answers with the right fact | 16 plain-English questions |

### Scoring
* Tool test: exact match or substring match against independently computed expected values
* Agent test: 3 scores per question — right tool, right input, answer matches regex pattern
* Consistency: agent test run 3 times; every case must pass every run

---

## Slide 9: Evaluation Results

| Metric | Result |
| --- | --- |
| Tool pass rate | **24/24 (100%)** |
| Tool speed | median **0.069 s**, p95 **0.128 s** |
| Agent: right tool | **16/16 (100%)** all 3 runs |
| Agent: right input | **16/16 (100%)** all 3 runs |
| Agent: right answer | **16/16 (100%)** all 3 runs |
| Consistency (3 runs) | **48/48 (100%)** — no flaky cases |
| Agent speed | median **9.5–11.1 s** per question |

No failures in either test set. During development, two test-design issues were found and fixed (the eval also tests the tests).

Evidence: `results/run_2026-11-17_1510.csv`, `results/agent_run_*_1515/1519/1524.csv`

---

## Slide 10: Security Considerations

### Public data only
All exposed data is public: PubMed IDs, paper titles, quoted sentences from open-access papers, dbGaP approved-requester names, funder names from published acknowledgements. RPPR raw text is never included.

### Access control
Databricks App sign-in; only identities given "Can use" can call the MCP endpoint. No anonymous access. Test identity credentials stored in UC secret, never in code.

### Input validation
Pydantic length and range limits (tested by C18, C20). Name search never auto-picks from a partial phs number.

### Known gap: prompt injection
Paper quotes are passed to the AI as tool output. A malicious sentence could attempt to steer the AI. Not yet tested with adversarial cases. Recommended for production.

---

## Slide 11: Lessons Learned and Recommendations

### What worked
1. **Goal-based tools** — the AI chose correctly 48/48 times from names and descriptions alone
2. **Snapshot architecture** — kept the server simple, fast (< 0.13 s) and safe
3. **User testing found a real gap** — "HTAN" exposed the missing name search; the test set had missed it
4. **Notebook-based eval worked** when Playground and Genie Code connectors were unavailable
5. **3-run consistency** — turned a binary pass/fail into a reliability signal

### Key recommendations
1. Add a **no-tool baseline** to quantify the MCP's lift
2. Add **adversarial and injection test cases**
3. Add **live government service tools** (e.g. dbGaP lookup) to strengthen the Read Integration category
4. **Enforce exact quotes** through AI instructions and agent-test checks
5. Grow the test set and add an **LLM-as-judge** scorer for softer failures

---

## Slide 12: Mission Alignment

**Who uses this and what decision does it support?**

| User | Question they can now ask |
| --- | --- |
| NIH program officer | "Is the data my program funded being reused? By whom?" |
| Data repository manager | "Which datasets have the most reuse? Where do reusers say they got the data?" |
| Data sharing policy staff | "Is NIH data sharing producing downstream research? Who funds it?" |

The DPU pipeline extracts the evidence from published papers. The MCP server makes it queryable by any AI agent, in plain English, with traceable quotes.

This is a step toward answering NIH's broader question: **does sharing data lead to new science?**

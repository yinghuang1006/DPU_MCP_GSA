# Evaluation report: DPU Data Reuse MCP server

Server under test: DPU Data Reuse MCP Server (`dpu-reuse-mcp`)
Evaluation framework: Notebook-based (Databricks serverless compute; no Arize Phoenix)
Agent model: `models.ai.gpt-6-astra` (temperature default, OpenAI Responses API)
Tool test dataset: `test_cases.csv` (24 items)
Agent test dataset: `agent_cases.csv` (16 items)
Date: 2026-11-17

Status: sections marked TODO need your input.

## 1. What was tested
Seven read-only MCP tools on a Databricks App (`dpu-reuse-mcp`):

| Tool | Question | Added |
| --- | --- | --- |
| `find_studies` | Which study (phs) matches this name? | 2026-11-13 |
| `find_data_reusers` | Who is reusing the data? | baseline |
| `find_reuse_data_sources` | Where do people get the data? | baseline |
| `find_reuse_funders` | Who funds the reuse? | baseline |
| `rus_summary` | What do approved requesters plan to do with this data? | 2026-11-23 |
| `find_rus_requests` | Which requests plan this kind of use? | 2026-11-23 |
| `search_rus` | Which research use statements mention these words? | 2026-11-23 |

Input: dbGaP phs accession, seed-paper PMID, or words from the study title (e.g. HTAN). RUS tools also accept filters: DAC, approval year, group, AI use, clinical stage, clinical topic, request status, and words in the statement.

Data:
* Reuse papers: DPU pipeline results snapshot (as of 2026-10-25; 47 studies, ~600 reuse papers).
* Research Use Statements: 10,173 unique statements from 45,335 non-rejected NCI DAC and Kids First DAC requests (as of 2026-11-20), classified by two AI models (Claude Sonnet 4.6 and GPT-5.1).

## 2. Testing method
| Layer | How | Where |
| --- | --- | --- |
| Unit / in-process | Tool functions called directly; counts compared with an independent pandas count on the same CSVs | Development session, 2026-11-13 (reuse); 2026-11-23 (RUS) |
| Live end-to-end | `run_eval` notebook calls the deployed app over MCP as a test identity (Inspector Gadget) | `results/` |
| Agent test | `agent_test` notebook: an AI model (`models.ai.gpt-6-astra`) gets the MCP tools and plain-English questions, is not told which tool to use; scored on right tool, right input, right fact in the answer | `results/agent_run_<date>.csv` |
| RUS in-process test | 7 tools listed by the server; `rus_summary`, `find_rus_requests`, `search_rus` called through a FastMCP in-process client; totals cross-checked against the DPU app page and direct pandas queries | 2026-11-23 |
| RUS classification validation | 34 known-answer sentences (22 group + 12 stage) run through both models; 40 random statements re-classified and compared with the 20 Nov baseline | 2026-11-23 |
| Curator review | Out of scope for the demo (user decision 2026-11-13): the demo tests whether the MCP works, not whether the pipeline matches the real world | `test_cases.csv` column `curator_checked` kept for later |

Tool test set: 24 cases in 7 categories (correctness, input, where, funders, error handling, security, study search).
Agent test set (`agent_cases.csv`): 16 questions (who reuses x3, where from x2, who funds x3, two-tool question, example papers, unknown study, off-topic question that must not call a tool, 4 questions that name a study without a phs number, one of them ambiguous).
RUS in-process test set: 11 scenarios (default no filters, Kids First + clinical, phs002371 + text search, approved only, build AI only, bad phs, missing study, bad group value, rejected status, text search, no-match text).
RUS classification: 34 known-answer sentences + 40 random re-runs.

## 3. Metrics
| Metric | Definition | Target | Result |
| --- | --- | --- | --- |
| Metric | Definition | Target | Result |
| --- | --- | --- | --- |
| Tool pass rate | % of 24 tool test cases answered as expected | 100% | Live 2026-11-17: **24/24 (100%)** |
| Tool speed | Seconds per MCP call (includes network) | < 2 s | Live: median **0.069 s**, 95th pct **0.128 s**; slowest = first call 1.6 s (warm-up) |
| Agent: right tool | AI picked the expected tool(s), or no tool for the off-topic question | 100% | Live: **16/16 (100%)** on all 3 runs |
| Agent: right input | AI passed the right phs, PMID or study name to the tool | 100% | Live: **16/16 (100%)** on all 3 runs |
| Agent: right answer | Final answer contains the expected fact (e.g. 28 papers, NIH/NCI, dbGaP, HTAN = phs002371) and does not invent data for an unknown study | >= 90% | Live: **16/16 (100%)** on all 3 runs |
| Agent: consistency | Same pass/fail across 3 independent runs | >= 90% | **48/48 (100%)** — no flaky cases |
| Agent: time per question | Whole question incl. model reasoning and tool calls | < 60 s | Live: median **9.5–11.1 s** across 3 runs; slowest single question 25.3 s |

### Tool test by category (live 2026-11-17 15:10 ET, deployment `01f1e29cda4510d4a135fa71840128ab`)

| Category | Cases | Passed | Pass rate |
| --- | --- | --- | --- |
| correctness | 5 | 5 | 100% |
| input | 3 | 3 | 100% |
| where | 2 | 2 | 100% |
| funders | 4 | 4 | 100% |
| error_handling | 5 | 5 | 100% |
| security | 1 | 1 | 100% |
| study_search | 4 | 4 | 100% |
| **Total** | **24** | **24** | **100%** |

### Agent test consistency (live, 3 runs, same deployment)

| Run | Time (ET) | Passed | All metrics | Median seconds |
| --- | --- | --- | --- | --- |
| 1 | 15:15 | 16/16 | 100% | 11.12 |
| 2 | 15:19 | 16/16 | 100% | 10.68 |
| 3 | 15:24 | 16/16 | 100% | 9.55 |

### RUS in-process tests (2026-11-23)

| Test | Expected | Result |
| --- | --- | --- |
| All 7 tools listed by server | 7 | 7 |
| `rus_summary()` totals | 10,173 statements; 45,335 requests; 1,012 studies | matched |
| `rus_summary(phs='phs002371')` | 211 statements; 219 requests; 1 study | matched |
| `rus_summary(dac='Kids First DAC', stages=['Clinical'])` | 37 statements; 113 requests | matched |
| `rus_summary(statuses=['approved'])` | 16,818 requests | matched |
| `find_rus_requests(ai=['Build AI'], max_results=3)` | 2,674 total requests; 581 statements | matched |
| `search_rus(text='machine learning')` | 682 statements | matched |
| Bad phs ('abc') | clear error message | passed |
| Missing study (phs002731) | "no approved, closed or expired NCI / Kids First DAC requests" | passed |
| Bad group value ('Biologi') | error with allowed list | passed |
| Rejected status | error: not in allowed statuses | passed |
| Original 4 tools after change | still return expected values | passed |

### RUS classification validation (2026-11-23, Databricks endpoints)

| Check | Expected | Result |
| --- | --- | --- |
| Known-answer checks, group (22 sentences, both models) | 22/22 | 22/22 both models |
| Known-answer checks, stage (12 sentences, Claude) | 12/12 | 12/12 |
| Known-answer checks, stage (12 sentences, GPT) | ≥ 11/12 (D08 allowed miss) | 12/12 (better than minimum) |
| 40 random statements: group same as Nov | ≥ 93% | 39/40 (98%) |
| 40 random statements: AI flag same as Nov | ≥ 95% | 39/40 (98%) |
| 40 random statements: clinical stage same as Nov | ≥ 85% | 37/40 (93%) |
| 40 random statements: clinical topic same as Nov | ≥ 85% | 38/40 (95%) |
| Evidence quotes exact (word-for-word in statement) | ≥ 99% | 40/40 (100%) |

### Failure analysis

No failures in either test set on the live app. During development, two test-design issues were found and fixed (see Lessons learned: C17/C20 split, and summary-cell crash on empty failures table).

RUS in-process: all 11 test scenarios passed. RUS classification: all checks above their thresholds. The few differences from the November baseline are borderline cases (e.g. one statement changed from BIOLOGY to TOOL_OR_BIOLOGY).

Note: the 3 RUS tools are not yet in the formal agent test (`agent_cases.csv`). Adding them is recommended.

How to read: a tool-test pass means the live server returned the expected value from the pipeline results. An agent-test pass means the AI model chose the right tool, passed the right input, and its answer contains the expected fact. Speed is per MCP call (tool test) or per full question (agent test). Evidence: `results/run_2026-11-17_1510.csv`, `results/agent_run_2026-11-17_1515.csv`, `_1519.csv`, `_1524.csv` and the summary logs.

## 4. Security

### Data classification
* All data exposed by the tools is public:
  - Reuse tools: PubMed IDs, paper titles, journal names, quoted sentences from published open-access papers, funder names from published acknowledgements.
  - RUS tools: dbGaP approved-requester names and affiliations (publicly listed on the dbGaP study page), Public Research Use Statements (from the same public list), and AI-generated labels.
  - Sources: dbGaP (website, API, FHIR): publications, requester lists (PI name, institute, RUS). Europe PMC: publication full-text search.
* RPPR raw text is never included. The pipeline that fills the results table runs behind the firewall and is not exposed through the MCP server.

### Scope containment
* Read-only: tools only read a results snapshot; no writes, no network calls to other services.
* Only 7 read-only tools are exposed; pipeline tools are not callable (verified by case C19). The RUS classification models are called only during the monthly batch step (GitHub Actions), never by the MCP server.
* Name search never auto-picks a study from a partial phs number or when several titles match; it returns candidates and asks the user (cases C23, A16).

### Access control
* Databricks App sign-in: only users and service principals given "Can use" on the app can call the MCP endpoint. No anonymous access.
* The test identity (Inspector Gadget) is a shared service principal whose credentials are stored in a Unity Catalog secret, not in notebook code.

### Input validation
* All tool inputs are checked with Pydantic: string length limits (4–100 chars for identifiers, 2–100 for search terms), numeric limits (max_papers ≤ 200, top_n ≤ 100). Tested by cases C18, C20.
* RUS tools additionally validate DAC, request status, group, stage, and topic values against allowed lists and return clear error messages with the allowed options (tested in-process, 2026-11-23).

### Secrets and configuration
* Inspector Gadget credentials load from `dbutils.secrets.get(catalog='models', schema='ai', key='inspector-gadget')`. No tokens are hardcoded or committed.
* The MCP URL and model service name are configuration variables at the top of each notebook.

### Untrusted input and prompt injection
* Paper quotes from the results table are passed to the AI model as part of tool output. A malicious sentence in a published paper could attempt to steer the AI's answer. This is a known gap; the current dataset does not include adversarial cases. A production evaluation should add injection test cases and consider output sanitisation.
* The AI is instructed to base numbers only on tool results and never invent data, but its compliance is probabilistic, not guaranteed.

## 5. Known limits
* "Where" and "who funds" cover Tool 1 papers only; the 12 Tool 2 reuse papers for phs001493, for example, have no source or funder data.
* Tool 2 results are a preliminary sample (first 300 citing papers per study; one classification rule is under review).
* Journal names not harmonised (e.g. "Nat Commun" and "Nature communications" count separately).
* Data is a snapshot (2026-10-25); refresh = copy new result files into the app's `data/` folder and redeploy.
* Pass rate shows the server reports the pipeline results faithfully; whether the pipeline's decisions match the real world is a separate evaluation (curator review), out of scope for this demo.
* The AI can reprocess tool results beyond the raw data (summarise, group, reword quotes). Its additions are not checked by the pipeline. The trace ("How this answer was made") lets users verify.

## 6. Lessons learned

| Area | What happened | Lesson |
| --- | --- | --- |
| Design | Tools read a finished results table, not the live pipeline | Separating "pipeline tools" (fill the table) from "query tools" (read it) kept the MCP simple, fast (< 0.3 s) and safe |
| Design | One tool per user question (who reuses / where from / who funds), not one per data file | Goal-based tools are easier for an AI to choose and for people to understand |
| Design | Building the funder and source tools showed they only cover Tool 1 papers | Building the MCP exposed a data gap in the pipeline; listed in Known limits |
| Design | Two-model cross-check for RUS — Claude and GPT classify each statement independently | Catches borderline cases; "models differ" is transparent and honest rather than forcing a wrong label |
| Testing | First eval run found a test-design error: input `abc` is rejected by the length rule before the friendly message | Fixed by splitting into C17 and C20. The eval also tests the tests |
| Testing | Expected answers were computed with a separate method (pandas on the CSVs), not with the server code | Independent checks catch server bugs, but only a curator check proves the answer is true |
| Testing | Summary cell crashed when there were no failures (empty table cannot be displayed on serverless) | Handle the "all passed" case explicitly |
| Testing | Notebook-based eval worked when Playground and Genie Code connectors were unavailable | Do not depend on a UI feature for evaluation |
| Testing | 3-run consistency — turned a binary pass/fail into a reliability signal | Run repeats to catch flaky cases |
| Platform | App compute took about 30 minutes to start the first time | Create the app early; later redeploys took about 3-5 minutes |
| Platform | The Genie Code connector requires a stateless MCP server | Set `stateless_http=True` before connecting to Genie Code |
| Platform | AI Playground only recognises MCP apps whose names start with `mcp-` | Name the app `mcp-...` from the start |
| Platform | The test identity needs "Can use" on the app (otherwise HTTP 401); the setting is under the app's Share button | Grant access before the first test run |
| Platform | requirements.txt first allowed any `fastmcp>=2.10`, but tests ran on 4.1.8 | Pin the tested version (`fastmcp>=4.1,<5`) so a new release cannot break the app |
| Platform | The workspace's chat models rejected tool calls through the Chat Completions API (a reasoning setting conflicts with tools), but accepted them through the Responses API | For agent tests with these models, use the Responses API (`/ai-gateway/openai/v1/responses`) |
| Testing | The agent test uses a neutral prompt that does not name the tools | Tool names and descriptions alone were enough for the model to choose correctly (48/48) |
| Design | A user asked for "HTAN" and the AI could not help: tools accepted only phs/PMID, and error lists had no titles | Added `find_studies` and name input; every study list now shows titles. User testing found a gap the test set had missed |
| Design | In the chat page, the AI grouped HTAN reuse papers into themes and shortened one evidence quote | Facts come from the tool; presentation comes from the AI. Keep exact what must be exact (quotes, counts) through AI instructions; show the trace so users can check |

## 7. Recommendations

* **Security conversation with institute IT.** Before broader deployment, review data classification, access scope, and prompt injection risks with the institute's IT security team.
* **Stepwise MCP implementation.** Internal testing → soft launch with selected users → pan-institute availability → external call. Each stage expands the user base and gathers feedback.
* **Enforce exact quotes.** The AI sometimes shortens evidence sentences. Add an AI instruction to quote word for word, and an agent-test check that the quote is a substring of the tool output.
* **Grow the test set and add an LLM-as-judge scorer.** The current 24 + 16 cases cover the main paths but are small. Add edge cases and an LLM judge to catch softer failures like wrong emphasis or misleading framing.
* **Refine the tools on specific variables as output.** Narrowing what each tool returns (specific columns, structured fields) reduces the surface for injection and improves answer accuracy.
* **Agents handle conflict or competing output.** When two tools or two models return different answers, the system should flag the conflict clearly rather than silently picking one.
* **Add the 3 RUS tools to the formal agent test.** They currently pass in-process tests but are not in `agent_cases.csv`.
* **Add adversarial and prompt-injection cases.** The current test set has no inputs designed to trick the AI. A production evaluation should include at least 5 such cases.
* **Curator review for a subset.** Checking 5–10 expected answers against the paper full text would add a "human verified" data point.

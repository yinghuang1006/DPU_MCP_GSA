# Evaluation of the DPU Data Reuse MCP server

| File | What it is | Who maintains it |
| --- | --- | --- |
| `test_cases.csv` | Questions with known answers (the "answer key") | You (curator) |
| `run_eval` | Notebook: asks the live server every question, checks, times | Run as is |
| `results/run_<date>.csv` | Every answer from one run, pass/fail | Created by the notebook |
| `results/summary_log.csv` | One line per run: pass rate, speed, code version | Created by the notebook |
| `agent_cases.csv` | Plain-English questions for the AI agent test, with expected tool and fact | You (curator) |
| `agent_test` | Notebook: an AI model answers each question using the MCP tools; scores tool choice, input, answer | Run as is |
| `agent_loop.py` | The small test agent used by `agent_test` | Leave as is |
| `results/agent_run_<date>.csv`, `results/agent_summary_log.csv` | Agent test results | Created by the notebook |
| `EVALUATION.md` | The written report (hackathon deliverable) | You + me |

## How to run (every time the code or data changes)
1. Open `run_eval` and click **Run all**.
2. Check the summary table: pass rate should be 100%. Open the failures table if not.
3. Copy the latest numbers into `EVALUATION.md`.

## How to add a test case
Add a row to `test_cases.csv`:
* `question_plain`: the question in plain words
* `tool` and `arguments_json`: which tool and input (copy an existing row)
* `check_path`: which part of the answer to check (copy an existing row)
* `match_type`: `equals`, `contains`, `list_has_pmid` or `tool_error`
* `expected`: the right answer
* `curator_checked`: put `Y` after you checked the answer yourself (e.g. in the paper full text)

## What a pass means
Cases C01-C14 check that the server returns what the pipeline results say.
They do NOT prove the pipeline decisions are right. Pipeline accuracy is checked separately
by curator review (rule precision checks). Mark `curator_checked = Y` only after your own check.

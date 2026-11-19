"""Minimal test agent for the DPU Data Reuse MCP server.

An LLM (Unity Gateway model service, OpenAI Responses API) gets the MCP tool list,
answers a plain-English question, and may call tools. We record which tools it
called, with which inputs, and its final answer, then score them.

The system prompt does NOT say which tool to use: the model must choose from the
tool names and descriptions alone. That is what this test measures.
"""

from __future__ import annotations

import json
import re
import time
from typing import Callable

import requests

SYSTEM_PROMPT = (
    "You are a helpful research assistant. Use the available tools when they help "
    "answer the question. Base numbers only on tool results; never invent them. "
    "If a tool reports an error or no data, say so."
)
MAX_TOOL_OUTPUT = 20000  # characters of tool JSON sent back to the model


def to_llm_tools(mcp_tools) -> list[dict]:
    """Convert MCP tool definitions to the Responses API function-tool format."""
    out = []
    for t in mcp_tools:
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
        out.append({
            "type": "function",
            "name": t.name,
            "description": t.description or "",
            "parameters": schema,
            "strict": False,
        })
    return out


def run_agent(question: str, llm_tools: list[dict], call_tool: Callable[[str, dict], str],
              model: str, host: str, auth_headers: Callable[[], dict], max_turns: int = 5) -> dict:
    """Ask one question. call_tool(name, args) must return the tool result as text."""
    url = host.rstrip("/") + "/ai-gateway/openai/v1/responses"
    items: list = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    calls: list[dict] = []
    t0 = time.perf_counter()
    for _ in range(max_turns):
        r = requests.post(
            url,
            headers={**auth_headers(), "Content-Type": "application/json"},
            json={"model": model, "input": items, "tools": llm_tools, "max_output_tokens": 2000},
            timeout=180,
        )
        r.raise_for_status()
        output = r.json().get("output", [])
        items.extend(output)
        function_calls = [o for o in output if o.get("type") == "function_call"]
        if not function_calls:
            answer = " ".join(
                c.get("text", "")
                for o in output if o.get("type") == "message"
                for c in o.get("content", []) if c.get("type") in ("output_text", "text")
            ).strip()
            return {"answer": answer, "calls": calls, "seconds": round(time.perf_counter() - t0, 2)}
        for fc in function_calls:
            try:
                args = json.loads(fc.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fc.get("arguments")}
            try:
                result = call_tool(fc["name"], args)
            except Exception as e:  # validation or network error goes back to the model
                result = json.dumps({"error": str(e)[:500]})
            calls.append({"tool": fc["name"], "args": args})
            items.append({"type": "function_call_output", "call_id": fc["call_id"],
                          "output": result[:MAX_TOOL_OUTPUT]})
    return {"answer": "(stopped: too many tool rounds)", "calls": calls,
            "seconds": round(time.perf_counter() - t0, 2)}


def score(case: dict, res: dict) -> dict:
    """Score one case: right tool(s), right input, answer contains the key fact.

    expected_tools: 'a;b' = both a and b must be called; 'a|b' = either a or b; 'none' = no tool.
    """
    expected = [] if case["expected_tools"] == "none" else case["expected_tools"].split(";")
    called = [c["tool"] for c in res["calls"]]
    tool_ok = (not called) if not expected else all(
        any(alt in called for alt in item.split("|")) for item in expected)
    allowed = {alt for item in expected for alt in item.split("|")}
    if expected and case["expected_identifier"]:
        want = case["expected_identifier"].lower()
        input_ok = any(want in json.dumps(c["args"]).lower() for c in res["calls"] if c["tool"] in allowed)
    else:
        input_ok = tool_ok
    pattern = case["answer_regex"]
    answer_ok = bool(re.search(pattern, res["answer"], re.I | re.S)) if pattern else True
    return {
        "tools_called": ";".join(called) or "(none)",
        "tool_ok": tool_ok,
        "input_ok": input_ok,
        "answer_ok": answer_ok,
        "passed": tool_ok and input_ok and answer_ok,
    }

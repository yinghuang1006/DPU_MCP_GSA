"""Chat agent for the 'Ask the data' page.

An LLM (Unity Gateway model service, OpenAI Responses API) answers questions and
calls the tools of the DPU Data Reuse MCP server. Same loop as
mcp/eval/agent_loop.py, plus chat history and a short trace for the user.
"""

from __future__ import annotations

import json
import time
from typing import Callable

import requests

SYSTEM_PROMPT = (
    "You help people understand how dbGaP datasets are reused in published papers. "
    "Use the available tools to answer; base every number on tool results and never invent data. "
    "Say which study (phs) the answer is about and the 'as of' date. When you name a paper, give "
    "its PMID and a short quote of the evidence sentence. Mention the caveats in 'how_to_read' "
    "briefly. If a tool reports an error or no data, say so and show the available studies. "
    "Keep answers short and use bullet points or small tables."
)
MAX_TOOL_OUTPUT = 20000


def to_llm_tools(mcp_tools) -> list[dict]:
    """Convert MCP tool definitions to the Responses API function-tool format."""
    out = []
    for t in mcp_tools:
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
        out.append({"type": "function", "name": t.name, "description": t.description or "",
                    "parameters": schema, "strict": False})
    return out


def ask(history: list[dict], question: str, llm_tools: list[dict],
        call_tool: Callable[[str, dict], str], model: str, host: str,
        auth_headers: Callable[[], dict], max_turns: int = 5) -> dict:
    """history = earlier [{'role': 'user'|'assistant', 'content': text}]. Returns answer + trace."""
    url = host.rstrip("/") + "/ai-gateway/openai/v1/responses"
    items: list = [{"role": "system", "content": SYSTEM_PROMPT}]
    items += [{"role": m["role"], "content": m["content"]} for m in history]
    items.append({"role": "user", "content": question})
    trace: list[dict] = []
    t0 = time.perf_counter()
    for _ in range(max_turns):
        r = requests.post(
            url,
            headers={**auth_headers(), "Content-Type": "application/json"},
            json={"model": model, "input": items, "tools": llm_tools, "max_output_tokens": 2500},
            timeout=180,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Model service error {r.status_code}: {r.text[:300]}")
        output = r.json().get("output", [])
        items.extend(output)
        calls = [o for o in output if o.get("type") == "function_call"]
        if not calls:
            answer = " ".join(
                c.get("text", "")
                for o in output if o.get("type") == "message"
                for c in o.get("content", []) if c.get("type") in ("output_text", "text")
            ).strip()
            return {"answer": answer or "(no answer)", "trace": trace,
                    "seconds": round(time.perf_counter() - t0, 1)}
        for fc in calls:
            try:
                args = json.loads(fc.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            t1 = time.perf_counter()
            try:
                result = call_tool(fc["name"], args)
            except Exception as e:
                result = json.dumps({"error": str(e)[:500]})
            trace.append({"tool": fc["name"], "input": args,
                          "seconds": round(time.perf_counter() - t1, 2), "result": result})
            items.append({"type": "function_call_output", "call_id": fc["call_id"],
                          "output": result[:MAX_TOOL_OUTPUT]})
    return {"answer": "Sorry, I could not finish this question (too many tool rounds).",
            "trace": trace, "seconds": round(time.perf_counter() - t0, 1)}

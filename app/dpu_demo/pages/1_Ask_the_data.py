"""Ask the data: chat with an AI that uses the DPU Data Reuse MCP server."""
import json

import nest_asyncio
import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks_mcp import DatabricksMCPClient

import chat_agent as ca

nest_asyncio.apply()
st.set_page_config(page_title="Ask the data - DPU", layout="wide")

MCP_URL = "https://dpu-reuse-mcp-7474654188777746.aws.databricksapps.com/mcp"
MODEL = "models.ai.gpt-6-astra"
EXAMPLES = [
    "Who is reusing the data from phs001493?",
    "Where did researchers get the phs000452 data they reused?",
    "Who funds the reuse of the dataset generated in PMID 29301960?",
    "Who is reusing the HTAN data, and who funds that reuse?",
]


@st.cache_resource
def connect():
    """App identity -> MCP server (read-only tools) and model service."""
    w = WorkspaceClient()
    mcp = DatabricksMCPClient(server_url=MCP_URL, workspace_client=w)
    return w, mcp, ca.to_llm_tools(mcp.list_tools())


st.title("Ask the data")
st.caption(
    "Ask in plain words who reuses a dbGaP dataset, where they got it, or who funds the reuse. "
    "Use a phs number (e.g. phs001493), the PMID of the paper that generated the data, or a study name (e.g. HTAN). "
    "An AI model answers by calling 4 read-only MCP tools over the DPU results "
    "(snapshot 2026-10-25). Check important numbers in the evidence shown."
)

try:
    w, mcp, llm_tools = connect()
except Exception as e:
    st.error(
        "Could not connect to the MCP server. The app needs 'Can use' on the app "
        f"dpu-reuse-mcp.\n\nDetails: {str(e)[:300]}"
    )
    st.stop()


def call_tool(name, args):
    r = mcp.call_tool(name, args)
    return r.content[0].text if r.content else ""


if "chat" not in st.session_state:
    st.session_state.chat = []  # [{'role', 'content', 'trace', 'seconds'}]

with st.sidebar:
    st.markdown("**Tools the AI can use**")
    for t in llm_tools:
        st.markdown(f"* `{t['name']}`")
    if st.button("Clear chat"):
        st.session_state.chat = []
        st.rerun()


def show_trace(trace, seconds):
    if not trace:
        st.caption(f"No tool used. {seconds} s")
        return
    with st.expander(f"How this answer was made: {len(trace)} tool call(s), {seconds} s"):
        for i, step in enumerate(trace, 1):
            st.markdown(f"**{i}. `{step['tool']}`** with input `{json.dumps(step['input'])}` ({step['seconds']} s)")
            try:
                st.json(json.loads(step["result"]), expanded=False)
            except (json.JSONDecodeError, TypeError):
                st.code(step["result"][:2000])


for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            show_trace(m.get("trace", []), m.get("seconds"))

question = None
if not st.session_state.chat:
    st.markdown("Try an example:")
    cols = st.columns(len(EXAMPLES))
    for col, ex in zip(cols, EXAMPLES):
        if col.button(ex, use_container_width=True):
            question = ex

typed = st.chat_input("Ask about a phs number or PMID...")
question = typed or question

if question:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat]
    st.session_state.chat.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Thinking and calling tools (10-40 s)..."):
            try:
                res = ca.ask(history, question, llm_tools, call_tool, MODEL,
                             w.config.host, w.config.authenticate)
            except Exception as e:
                res = {"answer": ("Sorry, the AI model could not be reached. The app needs "
                                  f"permission to use {MODEL}.\n\nDetails: {str(e)[:300]}"),
                       "trace": [], "seconds": None}
        st.markdown(res["answer"])
        show_trace(res["trace"], res["seconds"])
    st.session_state.chat.append({"role": "assistant", "content": res["answer"],
                                  "trace": res["trace"], "seconds": res["seconds"]})

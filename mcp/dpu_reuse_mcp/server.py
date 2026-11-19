"""DPU Data Reuse MCP server (read-only).

Four goal-based tools over the DPU public results table:
  find_studies             - which study (phs) matches a name or title words
  find_data_reusers        - who is reusing the data
  find_reuse_data_sources  - where people get the data they reuse
  find_reuse_funders       - who funds the reuse

Run locally (stdio):   python server.py
On Databricks Apps:    HTTP on DATABRICKS_APP_PORT, MCP endpoint at /mcp
"""

from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

import reuse_data as rd

INSTRUCTIONS = """
You answer questions about how a dbGaP dataset is reused in the literature.
Input for the three question tools: a dbGaP study accession (phs001493, version
suffix allowed), the PubMed ID of the paper that generated the data (the seed paper),
or words from the study title (e.g. HTAN). If the user names a study without a phs
number, call find_studies first and use the phs number it returns; if several
studies match, ask the user which one.

Pick the tool by question:
- "Which study is X / what is the phs number for X?" -> find_studies
- "Who uses / reuses / cites and uses this data?"  -> find_data_reusers
- "Where did they get the data / which repository / what other data?" -> find_reuse_data_sources
- "Who funds the reuse / which grants / NIH vs other funders?" -> find_reuse_funders

Always report the as_of date, quote the evidence sentence for any paper you name,
and repeat the how_to_read caveats. If a tool returns 'error', show the
available_studies list instead of guessing. Do not invent numbers.
"""

mcp = FastMCP(name="DPU Data Reuse", instructions=INSTRUCTIONS)

Identifier = Annotated[
    str,
    Field(
        description=(
            "dbGaP study accession (e.g. 'phs001493' or 'phs001493.v3.p1'), OR the "
            "PubMed ID of the paper that generated the dataset (e.g. '29301960'), OR words "
            "from the study title (e.g. 'HTAN'). A name matching several studies returns candidates."
        ),
        min_length=4,
        max_length=100,
    ),
]

READ_ONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}


@mcp.tool(annotations=READ_ONLY)
def find_studies(
    term: Annotated[
        str,
        Field(description="Words from a study name or title, e.g. 'HTAN', 'melanoma', "
                          "'renal cell carcinoma immune checkpoint'.", min_length=2, max_length=100),
    ],
    max_results: Annotated[int, Field(ge=1, le=50, description="How many studies to list.")] = 10,
) -> dict:
    """Which dbGaP study matches this name? Searches the titles of the studies in the DPU
    results and returns matching phs numbers with title, collection, seed PMIDs and number of
    reuse papers. Use it when the user names a study but gives no phs number or PMID."""
    return rd.search_studies(term, max_results)


@mcp.tool(annotations=READ_ONLY)
def find_data_reusers(
    identifier: Identifier,
    include_needs_review: Annotated[
        bool,
        Field(description="Also include borderline papers (Possible use, weak wording, unclassified)."),
    ] = False,
    max_papers: Annotated[int, Field(ge=1, le=200, description="How many papers to list (newest first).")] = 25,
) -> dict:
    """Who is reusing this dataset? Returns reuse papers (PMID, year, title, journal,
    first author, decision, evidence quote), counts by route/year/decision, and how many
    papers have an approved dbGaP requester as an author."""
    return rd.who_reuses(identifier, include_needs_review, max_papers)


@mcp.tool(annotations=READ_ONLY)
def find_reuse_data_sources(
    identifier: Identifier,
    top_n: Annotated[int, Field(ge=1, le=50, description="How many sources to list.")] = 15,
    max_examples: Annotated[int, Field(ge=0, le=50, description="How many example sentences to return.")] = 10,
) -> dict:
    """Where do people get the data they reuse? Returns the repositories/portals that reuse
    papers name for THIS dataset (e.g. dbGaP, GDC), the other data sources they combine it
    with (e.g. TCGA, GEO), counted as distinct papers, plus example quotes."""
    return rd.where_from(identifier, top_n, max_examples)


@mcp.tool(annotations=READ_ONLY)
def find_reuse_funders(
    identifier: Identifier,
    include_personnel: Annotated[
        bool,
        Field(description="Also list personnel support (F/T/K awards, fellowships), which is not counted."),
    ] = False,
    top_n: Annotated[int, Field(ge=1, le=100, description="How many funders to list.")] = 20,
) -> dict:
    """Who funds the reuse of this dataset? Returns funders named in the reuse papers
    (research + infrastructure), with number of reuse papers, distinct grants and example
    grant IDs, plus how many reuse papers have an NIH funder."""
    return rd.who_funds_reuse(identifier, include_personnel, top_n)


@mcp.custom_route("/", methods=["GET"])
async def home(request: Request) -> HTMLResponse:
    """Plain landing page so people opening the app URL see what it is."""
    return HTMLResponse(
        "<h2>DPU Data Reuse MCP server</h2>"
        "<p>This app has no screens: it is an MCP server for AI agents.</p>"
        "<p>MCP endpoint: <code>/mcp</code> &nbsp; Health: <code>/health</code></p>"
        "<ul><li>find_studies - which study (phs) matches a name</li>"
        "<li>find_data_reusers - who is reusing the data</li>"
        "<li>find_reuse_data_sources - where people get the data</li>"
        "<li>find_reuse_funders - who funds the reuse</li></ul>"
        f"<p>Input: phs accession, seed-paper PMID or study name. Data as of {rd.as_of()}.</p>"
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "data_as_of": rd.as_of()})


def main() -> None:
    port = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")
    if port:
        # stateless_http=True is required for the Genie Code custom MCP connector
        mcp.run(transport="http", host="0.0.0.0", port=int(port), stateless_http=True)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

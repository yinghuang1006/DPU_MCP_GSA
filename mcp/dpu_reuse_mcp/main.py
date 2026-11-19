"""Local entry point for the DPU Data Reuse MCP server.

Run locally (stdio, for Claude Desktop or any MCP client):
    pip install -r requirements.txt
    python main.py

On Databricks Apps, app.yaml calls server.py directly.
"""

from server import main

if __name__ == "__main__":
    main()

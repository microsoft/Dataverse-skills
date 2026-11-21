# MCP availability check

Detail for `dv-overview`.

If the user's request involves MCP — explicitly or implicitly — search your callable tools for any tool whose name or description contains `dataverse` (same search as Hard Rule 0).

**If MCP NOT available and user explicitly asked for MCP** ("use MCP to query"):
1. **Do NOT silently fall back** to the Python SDK or Web API
2. Tell the user: "Dataverse MCP tools aren't configured in this session yet."
3. Load `dv-connect` to set up the MCP server
4. After MCP is configured, **stop** — the session must restart for MCP tools to appear. Do not proceed with SDK.

**If MCP NOT available and user asked a data question** ("how many accounts?"):
1. Use the CLI (if profile exists) or SDK to answer. Do not block the user.
2. After answering, offer: "MCP would handle this conversationally — want me to set it up?"

The distinction matters: explicit MCP request → block and set up MCP; implicit question → answer with SDK, offer MCP setup.

**If MCP tools ARE available**, prefer MCP for simple reads/queries/small CRUD. Use the SDK only when a script is needed.

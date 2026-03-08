---
name: dataverse-mcp-setup
description: Install and configure the Dataverse MCP server for Claude Code or GitHub Copilot. Use this when setting up or troubleshooting the MCP server connection.
---

# Skill: Dataverse MCP Server Setup

The Dataverse MCP server exposes structured tool calls the agent can invoke directly during a conversation. It is useful for data operations and basic table management — but has significant gaps for metadata work.

---

## What the MCP Server Actually Supports

**Supported:**
- Data CRUD: `create_record`, `read_query`, `update_record`, `delete_record`, `fetch`
- Table operations: `create_table`, `update_table`, `delete_table`, `list_tables`, `describe_table`
- Keyword search across Dataverse: `search`

**NOT supported:**
- Forms (FormXml) — no create, modify, or retrieve
- Views (SavedQueries) — no create, modify, or retrieve
- Relationships (1:N, N:N) — no create or modify
- Option sets — no create or modify
- Column-level metadata operations (individual attribute definitions)

For forms, views, relationships, and option sets, the agent must fall back to the Web API directly. See the [`dataverse-metadata` skill documentation](../dataverse-metadata/SKILL.md) for those patterns.

---

## Tool Routing: MCP Server vs. Web API

| Task | Use |
|---|---|
| Create/read/update/delete data records | MCP server |
| Create a new table | MCP server |
| Explore what tables/columns exist | MCP server (`list_tables`, `describe_table`) |
| Add a column to an existing table | Web API (direct) |
| Create a relationship / lookup | Web API (direct) |
| Create or modify a form | Web API (direct) |
| Create or modify a view | Web API (direct) |
| Manage option sets | Web API (direct) |

---

## Install

Microsoft publishes the Dataverse MCP server. Verify the current package at:
https://github.com/microsoft/Dataverse-MCP

```
npm install -g @microsoft/dataverse-mcp
```

---

## Configure for Claude Code CLI

Create `.claude/mcp_settings.json` in the repo root by reading values from `.env`:

```python
import os, json
from pathlib import Path

# Load .env
env = {}
for line in Path(".env").read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

os.makedirs(".claude", exist_ok=True)
config = {
    "mcpServers": {
        "dataverse": {
            "command": "npx",
            "args": ["@microsoft/dataverse-mcp"],
            "env": {
                "DATAVERSE_URL": env["DATAVERSE_URL"],
                "TENANT_ID": env["TENANT_ID"],
                "CLIENT_ID": env["CLIENT_ID"],
                "CLIENT_SECRET": env["CLIENT_SECRET"]
            }
        }
    }
}
with open(".claude/mcp_settings.json", "w") as f:
    json.dump(config, f, indent=2)
```

Ensure `.claude/mcp_settings.json` is gitignored:
```python
gitignore = open(".gitignore").read() if os.path.exists(".gitignore") else ""
if ".claude/mcp_settings.json" not in gitignore:
    with open(".gitignore", "a") as f:
        f.write(".claude/mcp_settings.json\n")
```

---

## Configure for GitHub Copilot (VS Code)

Create `.vscode/settings.json` by reading values from `.env`. This is handled automatically by `dataverse-init` Scenario A step 4 — no manual file creation needed. If it needs to be recreated:

```python
import os, json
from pathlib import Path

env = {}
for line in Path(".env").read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

os.makedirs(".vscode", exist_ok=True)
settings = {
    "github.copilot.chat.mcp.servers": {
        "dataverse": {
            "command": "npx",
            "args": ["@microsoft/dataverse-mcp"],
            "env": {
                "DATAVERSE_URL": env["DATAVERSE_URL"],
                "TENANT_ID": env["TENANT_ID"],
                "CLIENT_ID": env["CLIENT_ID"],
                "CLIENT_SECRET": env["CLIENT_SECRET"]
            }
        }
    }
}
with open(".vscode/settings.json", "w") as f:
    json.dump(settings, f, indent=2)
```

`.vscode/settings.json` contains credentials and must never be committed. Confirm it is in `.gitignore`.

---

## Auth Requirements

The MCP server requires service principal credentials (`CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID`). Interactive/device code auth is not supported. Complete `dataverse-cicd/SKILL.md` steps 1–4 to create a service principal before configuring the MCP server.

---

## Verify

Ask the agent: *"List the tables in my Dataverse environment"*

If the MCP server is connected, the agent calls `list_tables` directly. If it falls back to PAC CLI or Web API, the MCP server is not connected — check the configuration and confirm the `.env` values are loaded.

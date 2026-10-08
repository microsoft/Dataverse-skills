---
name: dataverse
description: Microsoft Dataverse / Power Platform for coding agents -- connect, then record CRUD, bulk data, advanced queries, schema & metadata, solution ALM, administration, security, and Finance & Operations X++. Use when the user mentions Dataverse, Dynamics 365, Power Platform, CRM, or ERP.
license: Complete terms in LICENSE.txt
compatibility: Requires network/internet access to reach the Dataverse Web API and Microsoft Entra ID for authentication.
metadata:
  short-description: "Connect to Dataverse and unpack the full dv-* skill set"
  author: Microsoft
  source: https://github.com/microsoft/Dataverse-skills/tree/main/.github/plugins/dataverse
---

# Microsoft Dataverse

## Overview

Entry point for working with Microsoft Dataverse (Power Platform / Dynamics 365) from a coding agent. This skill introduces Dataverse, installs the full set of specialist skills, and connects your environment (CLI auth + MCP server). After setup, the agent routes to the specialist skill that fits the task.

Dataverse work spans several capabilities, each a dedicated skill once installed:

| Need | Skill |
| --- | --- |
| Connect, authenticate, configure MCP, verify / troubleshoot the environment | `dv-connect` |
| Record CRUD, bulk create/update/upsert, CSV / FK-ordered import | `dv-data` |
| Reads & analytics -- OData, QueryBuilder, FetchXML, DataFrames | `dv-query` |
| Schema -- tables, columns, relationships, forms, views | `dv-metadata` |
| Solution ALM -- create, export, import, pack/unpack | `dv-solution` |
| Environment administration -- bulk delete, retention, org settings | `dv-admin` |
| Security & access -- roles, users, business units | `dv-security` |
| Finance & Operations X++ -- author, build, deploy | `erp-xpp` |

**Execute the steps in order.** Each is idempotent -- skip it if it's already done.

## Step 1: Install the full Dataverse skill set

Install the specialist `dv-*` skills from the canonical repository so the agent can route to them:

```
npx skills add microsoft/Dataverse-skills -s "*"
```

Add `-g` to install globally across every project. This makes `dv-connect`, `dv-data`, `dv-query`, `dv-metadata`, `dv-solution`, `dv-admin`, `dv-security`, and `erp-xpp` available as routable skills. Once installed, defer to `dv-connect` for the full, per-agent setup matrix and troubleshooting; the steps below are the essential path.

## Step 2: Install tools

| Tool | Check | Install |
| --- | --- | --- |
| Node.js | `node --version` | required for the Dataverse CLI + MCP proxy |
| Dataverse CLI | `npm list -g @microsoft/dataverse` | `npm install -g @microsoft/dataverse@latest` (only if missing) |
| Python 3 | `python --version` | required for the `dv-data` / `dv-query` SDK paths |

Then install the Python dependencies used by the bundled scripts and the data/query skills:

```
pip install --upgrade PowerPlatform-Dataverse-Client python-dotenv azure-identity msal msal-extensions requests pandas
```

## Step 3: Authenticate

The Dataverse CLI holds the token in a shared cache that the MCP server and the Python SDK both reuse -- one sign-in covers all three:

```
dataverse auth create --environment <your-environment-url>            # interactive (WAM / browser)
dataverse auth create --environment <your-environment-url> --deviceCode   # headless / SSH / remote
```

Record `DATAVERSE_URL` and `TENANT_ID` in a project `.env`. If an admin-consent error appears, share the exact consent URL the CLI prints -- do not synthesize one.

## Step 4: Register the MCP server

The MCP server is the `@microsoft/dataverse` stdio proxy. Set `MCP_CLIENT_ID` in `.env` by agent:

- **GitHub Copilot** -> `aebc6443-996d-45c2-90f0-388ff96faa56`
- **Claude / Cursor / Codex** -> `0c412cc3-0dd6-449b-987f-05b053db9457` (all use the npx stdio proxy, which authenticates as the Dataverse CLI app)

Register the server in the agent's MCP config (e.g. `.mcp.json` for Copilot, `claude mcp add` for Claude, `~/.cursor/mcp.json` for Cursor, `~/.codex/config.toml` for Codex), pointing at:

```
npx @microsoft/dataverse mcp <your-environment-url>
```

Then allowlist the client for the environment:

```
python scripts/enable-mcp-client.py
```

## Step 5: Telemetry attribution (JetBrains)

Inside a JetBrains IDE, tag Dataverse calls with `host=jetbrains`:

- Write `DATAVERSE_PLUGIN_HOST=jetbrains` into the project `.env`.
- `scripts/auth.py` reads it and stamps `host=jetbrains` into the operation-context on every call, so Dataverse telemetry attributes the traffic to JetBrains.

## Step 6: Verify

```
dataverse org who            # prints the signed-in user + environment
python scripts/auth.py --check   # confirms the data plane is reachable
```

If both succeed, you're connected. Route to the specialist skill for the task (`dv-data`, `dv-query`, `dv-metadata`, ...); run `dv-connect` for deeper setup, environment switching, or connection troubleshooting.

## Bundled scripts

- `scripts/auth.py` -- shared authentication + telemetry attribution. Reads `.env`, reuses the Dataverse CLI token cache (via MSAL), and stamps the operation-context (`app`, `skill`, `agent`, `host`).
- `scripts/enable-mcp-client.py` -- allowlists the agent's MCP client ID for the environment.
- `scripts/requirements.txt` -- pinned Python dependencies for the scripts above.

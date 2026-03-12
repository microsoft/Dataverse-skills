---
name: dataverse-overview
description: >
  Start here for any Dataverse task. Routes requests to the right tools.
  USE WHEN: "how do I", "what tool", "which skill", "where do I start", "help with Dataverse",
  "what can this plugin do", "overview", "getting started".
  DO NOT USE WHEN: you already know which specific skill to use.
---

# Skill: Overview — What to Use and When

This skill provides cross-cutting context that no individual skill owns: tool capabilities, UX principles, and the skill index. Per-task routing is handled by each skill's WHEN/DO NOT USE WHEN frontmatter triggers — not duplicated here.

---

## UX Principle: Natural Language First

Users should never need to invoke skills or slash commands directly. The intended workflow is:

1. Install the plugin
2. Describe what you want in plain English
3. Claude figures out the right sequence of tools, APIs, and scripts

**Example prompt:** *"I want to create an extension called IronHandle for Dynamics CRM in this Git repo folder that adds a 'nickname' column to the account table and populates it with a clever nickname every time a new account is created."*

From that single prompt, Claude should orchestrate the full sequence: check if the workspace is initialized → create metadata via Web API → write and deploy a C# plugin → pull the solution to the repo. No skill names, no commands — just intent.

Skills exist as **Claude's knowledge**, not as user-facing commands. Each skill documents how to do one thing well. Claude chains them together based on what the user describes. If a capability gap exists (e.g., prompt columns aren't programmatically creatable yet), say so honestly and suggest workarounds rather than hallucinating a path.

---

## Multi-Environment Rule

Pro-dev scenarios involve multiple environments (dev, test, staging, prod) and multiple sets of credentials. **Never assume** the active PAC auth profile, values in `.env`, or anything from memory or a previous session reflects the correct target for the current task.

**Before any operation that touches a specific environment** — deploying a plugin, pushing a solution, registering a step, running a script against the Web API — ask the user:

> "Which environment should I target for this? Please confirm the URL."

Then verify the active PAC profile matches:

```bash
pac auth list
pac org who
```

The more impactful the operation (plugin deploy, solution import, step registration), the more important this confirmation is. Do not proceed against an environment the user hasn't explicitly confirmed in the current session.

---

## What This Plugin Covers

This plugin covers **Dataverse / Power Platform development**: solutions, tables, columns, forms, views, and data operations (CRUD, bulk, analytics).

It does **not** cover:

- Power Automate flows (use the maker portal or Power Automate Management API)
- Canvas apps (use `pac canvas` or the maker portal)
- Azure infrastructure beyond what's needed for service principal setup
- Business Central or other Dynamics products

---

## Tool Capabilities — Which Tool for Which Job

Understanding the real limits of each tool prevents hallucinated paths. This is the one piece of context no individual skill owns.

| Tool | Use for | Does NOT support |
| --- | --- | --- |
| **MCP Server** | Data CRUD (create/read/update/delete records), table create/update/delete/list/describe, column add via `update_table`, keyword search, single-record fetch | Forms, Views, Relationships, Option Sets, Solutions. **Note:** table creation may timeout but still succeed — always `describe_table` before retrying. Run queries sequentially (parallel calls timeout). Column names with spaces normalize to underscores (e.g., `"Specialty Area"` → `cr9ac_specialty_area`). **SQL limitations:** The `read_query` tool uses Dataverse SQL, which does NOT support: `DISTINCT`, `HAVING`, subqueries, `OFFSET`, `UNION`, `CASE`/`IF`, `CAST`/`CONVERT`, or date functions. For analytical queries that need these (e.g., finding duplicates, unmatched records, filtered aggregates), use Python with OData or pandas — see the python-sdk skill. **Bulk operations:** MCP `create_record` creates one record at a time. For 50+ records, use the Web API `$batch` endpoint or Python SDK `CreateMultiple` instead — see the python-sdk skill. |
| **Python SDK** | **Preferred for all scripted data work and schema creation.** Data CRUD, upsert (alternate keys), bulk create/update/upsert/delete (uses CreateMultiple/UpdateMultiple internally), OData queries (select/filter/expand/orderby/top), read-only SQL, table create/delete/metadata, add/remove columns, relationship metadata CRUD (1:N, N:N, lookup fields), alternate key management, file column uploads (chunked >128MB), context manager with connection pooling | Forms, Views, global Option Sets, record association (`$ref`), `$apply` aggregation, custom action invocation, generic `$batch` |
| **Web API** | Everything — forms, views, relationships, option sets, columns, table definitions, unbound actions, `$ref` association | Nothing (full MetadataService + OData access) |
| **PAC CLI** | Solution export/import/pack/unpack, environment create/list/delete/reset, auth profile management, plugin updates (`pac plugin push` — first-time registration requires Web API), user/role assignment (`pac admin assign-user`), solution component management | Data CRUD, metadata creation (tables/columns/forms) |
| **Azure CLI** | App registrations, service principals, credential management | Dataverse-specific operations |
| **GitHub CLI** | Repo management, GitHub secrets, Actions workflow status | Dataverse-specific operations |

**When in doubt:** MCP for conversational data work (single records, simple queries) → Python SDK for scripted data, bulk operations, schema creation, and analysis → Web API for metadata the SDK doesn't cover (forms, views, option sets) → PAC CLI for solution lifecycle.

**Volume guidance:** MCP `create_record` is fine for 1–10 records. For 10+ records, use Python SDK `client.records.create(table, list_of_dicts)` — it uses `CreateMultiple` internally and handles batching. For data profiling and analytics beyond simple GROUP BY, use Python with pandas (see python-sdk skill). For aggregation queries (`$apply`), use the Web API directly.

Note: The Python SDK is in **preview** — breaking changes possible.

---

## Available Skills

Each skill's frontmatter contains WHEN/DO NOT USE WHEN triggers that Claude uses for automatic routing. This index is for human reference only.

| Skill | What it covers |
| --- | --- |
| **init** | Workspace setup: `.env`, MCP config, directory structure, demo data |
| **setup** | Machine setup: install tools (PAC CLI, .NET, Python), authenticate |
| **metadata** | Create/modify tables, columns, relationships, forms, views via Web API |
| **python-sdk** | Data CRUD, bulk ops, OData queries, file uploads, bulk import, data profiling, notebook analysis via Python SDK |
| **solution** | Solution create/export/import/pack/unpack, post-import validation |
| **mcp-configure** | Configure Dataverse MCP server for GitHub Copilot or Claude Code as part of `init` |

---

## Scripts

The plugin ships utility scripts in `scripts/`:

| Script | Purpose |
| --- | --- |
| `auth.py` | Azure Identity token/credential acquisition — used by all other scripts and the SDK |
| `enable-mcp-client.py` | Add the MCP Client ID to the list of allowed MCP clients in Dataverse |

For data operations and post-import validation, use the Python SDK directly (inline in your own scripts). See the `python-sdk` skill for SDK patterns and the `solution` skill for validation queries.

Any Web API call that goes beyond a one-off query should be written as a Python script and committed to `/scripts/`. Use `scripts/auth.py` for token acquisition.

---

## Windows Scripting Rules

When running in Git Bash on Windows (the default for Claude Code on Windows):

- **ASCII only in `.py` files.** Curly quotes, em dashes, or other non-ASCII characters cause `SyntaxError`. Use straight quotes and regular dashes.
- **No `python -c` for multiline code.** Shell quoting differences between Git Bash and CMD break multiline `python -c` commands. Write a `.py` file instead.
- **PAC CLI may need a PowerShell wrapper.** If `pac` hangs or fails in Git Bash, use `powershell -Command "& pac.cmd <args>"`. See the setup skill for details.
- **Generate GUIDs in Python scripts**, not via shell backtick-substitution: `str(uuid.uuid4())` inside the `.py` file.

---

## After Any Change: Pull to Repo

Any time you make a metadata change (via MCP, Web API, or the maker portal), end the session by pulling:

```bash
pac solution export --name <SOLUTION_NAME> --path ./solutions/<SOLUTION_NAME>.zip --managed false
pac solution unpack --zipfile ./solutions/<SOLUTION_NAME>.zip --folder ./solutions/<SOLUTION_NAME>
rm ./solutions/<SOLUTION_NAME>.zip
git add ./solutions/<SOLUTION_NAME>
git commit -m "feat: <description>"
git push
```

The repo is always the source of truth.

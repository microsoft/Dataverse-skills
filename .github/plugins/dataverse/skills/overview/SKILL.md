---
name: dataverse-overview
description: >
  Start here for any Dataverse task. Routes requests to the right tools.
  WHEN: "how do I", "what tool", "which skill", "where do I start", "help with Dataverse",
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

This plugin covers **Dataverse / Power Platform development**: environments, solutions, tables, columns, forms, views, security roles, C# plugins, and CI/CD for solution deployment.

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
| **Python SDK** | Data CRUD, upsert (alternate keys), bulk create/update/upsert/delete, OData queries (select/filter/expand/orderby/top), read-only SQL, table create/delete/metadata, add/remove columns, relationship metadata CRUD (1:N, N:N, lookup fields), alternate key management, file column uploads (chunked >128MB), context manager with connection pooling | Forms, Views, global Option Sets, record association (`$ref`), custom action invocation, generic `$batch` |
| **Web API** | Everything — forms, views, relationships, option sets, columns, table definitions, unbound actions, `$ref` association | Nothing (full MetadataService + OData access) |
| **PAC CLI** | Solution export/import/pack/unpack, environment create/list/delete/reset, auth profile management, plugin updates (`pac plugin push` — first-time registration requires Web API), user/role assignment (`pac admin assign-user`), solution component management | Data CRUD, metadata creation (tables/columns/forms) |
| **Azure CLI** | App registrations, service principals, credential management | Dataverse-specific operations |
| **GitHub CLI** | Repo management, GitHub secrets, Actions workflow status | Dataverse-specific operations |

**When in doubt:** MCP for conversational data work (single records, simple queries) → Python SDK for scripted data, bulk operations, and analysis → Web API for metadata the SDK doesn't cover → PAC CLI for solution lifecycle.

**Volume guidance:** MCP `create_record` is fine for 1–50 records. For 50–1000 records, use Web API `$batch` (see python-sdk skill). For 1000+ records, use Python SDK `CreateMultiple`. For data profiling and analytics beyond simple GROUP BY, use Python with pandas (see python-sdk skill).

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
| **security** | Add users, assign security roles |
| **csharp-plugins** | Scaffold, build, register, deploy C# plugins |
| **environment** | Create, list, select, delete Power Platform environments |
| **cicd** | GitHub Actions workflow for auto-deploy on merge |

---

## Scripts

The plugin ships two utility scripts in `scripts/`:

| Script | Purpose |
| --- | --- |
| `auth.py` | Azure Identity token/credential acquisition — used by all other scripts and the SDK |
| `assign-user.py` | Add a user and assign a security role (PAC CLI fast path, SDK + Web API fallback) |

For data operations and post-import validation, use the Python SDK directly (inline in your own scripts). See the `python-sdk` skill for SDK patterns and the `solution` skill for validation queries.

Any Web API call that goes beyond a one-off query should be written as a Python script and committed to `/scripts/`. Use `scripts/auth.py` for token acquisition.

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

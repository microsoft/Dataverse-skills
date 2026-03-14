---
name: dataverse-overview
description: >
  ALWAYS LOAD THIS SKILL FIRST for any Dataverse task. Contains hard rules that override all other skills.
  USE WHEN: ANY request involving Dataverse, Dynamics 365, Power Platform, tables, columns, solutions,
  records, queries, CRM, metadata, plugins, SDK, Web API, PAC CLI, or environment operations.
  Also use for: "how do I", "what tool", "which skill", "where do I start", "help with Dataverse",
  "create table", "create column", "build solution", "query data", "bulk import", "sample data",
  "support agent", "customer table", "ticket table".
  This skill MUST be loaded before any other Dataverse skill. Read the Hard Rules section first.
---

# Skill: Overview — What to Use and When

This skill provides cross-cutting context that no individual skill owns: tool capabilities, UX principles, and the skill index. Per-task routing is handled by each skill's WHEN/DO NOT USE WHEN frontmatter triggers — not duplicated here.

---

## Hard Rules — Read These First

These rules are non-negotiable. Violating any of them means the task is going off-rails.

### 0. Check Init State Before Anything Else

Before writing ANY code or creating ANY files, check if the workspace is initialized:

```bash
ls .env scripts/auth.py 2>/dev/null
```

- If BOTH exist: workspace is initialized. Proceed to the relevant task.
- If EITHER is missing: **Automatically run the init flow** (see the init skill). Do NOT ask the user whether to initialize — just do it. Do not create your own `.env`, `requirements.txt`, `.env.example`, or auth scripts. The init skill handles all of this.

Do NOT create `requirements.txt`, `.env.example`, or scaffold files manually. The init flow produces the correct file structure. Skipping init is the #1 cause of broken setups.

### 1. Python Only — No Exceptions

All scripts, data operations, and automation MUST use **Python**. This plugin's entire toolchain — `scripts/auth.py`, the Dataverse SDK, all skill examples — is Python-based.

**NEVER:**
- Run `npm init`, `npm install`, or any Node.js/JavaScript tooling
- Install packages via `npm`, `yarn`, or `pnpm`
- Write scripts in JavaScript, TypeScript, PowerShell, or any language other than Python
- Use `@azure/msal-node`, `@azure/identity`, or any Node.js Azure SDK
- Import or reference `node_modules/`

**ALWAYS:**
- Use `pip install` for Python packages
- Use `scripts/auth.py` for authentication tokens and credentials
- Use the Python Dataverse SDK (`PowerPlatform-Dataverse-Client`) for data and schema operations
- Use `azure-identity` (Python) for Azure credential flows

If you find yourself about to run `npm` or create a `package.json`, STOP. You are going off-rails. Re-read the python-sdk skill.

### 2. MCP → SDK → Web API (in that order)

**Before writing ANY code, ask: can MCP handle this?** If MCP tools are available in your tool list (`list_tables`, `describe_table`, `read_query`, `create_record`, etc.) and the task is a simple read, query, or small CRUD operation (≤10 records), **use MCP — no script needed.** Examples: "how many accounts have 'jeff' in the name?", "show me the columns on the contact table", "create an account named Contoso."

**If MCP can't handle it** (bulk operations, schema creation, multi-step workflows, analytics, or MCP tools aren't available), **use the Python SDK — not raw HTTP.** This is the most common mistake agents make.

**SDK checklist — evaluate EVERY time you write a script:**
- Creating/reading/updating/deleting records? → `client.records.create()`, `.get()`, `.update()`, `.delete()`
- Creating tables or columns? → `client.tables.create()`
- Creating relationships? → `client.tables.create_lookup_field()` or `client.tables.create_many_to_many_relationship()`
- Creating publishers or solutions? → `client.records.create("publisher", {...})`, `client.records.create("solution", {...})`
- Bulk operations? → `client.records.create(table, [list_of_dicts])`
- Querying with $select/$filter/$expand? → `client.records.get()` with `select=`, `filter=`, `expand=`

**If you are about to write `import requests` or `from auth import get_token` in a script, STOP.** Ask yourself: does the SDK support this operation? If yes, use `from auth import get_credential` + `DataverseClient` instead. The `get_token()` function exists ONLY for the narrow set of operations the SDK does not support.

**Raw Web API is ONLY acceptable for:** forms, views, global option sets, N:N `$ref` associations, N:N `$expand`, `$apply` aggregation, memo columns, and unbound actions. Everything else MUST use MCP (if available) or the SDK.

**Field casing:** `$select`/`$filter` use lowercase logical names (`new_name`). `$expand` and `@odata.bind` use Navigation Property Names that are case-sensitive and must match `$metadata` (e.g., `new_AccountId`). Getting this wrong causes 400 errors. The SDK handles this correctly for `@odata.bind` keys.

**Publisher prefix:** Never hardcode a prefix (especially not `new`). Always query existing publishers in the environment and ask the user which to use. The prefix is permanent on every component created with it. See the solution skill's publisher discovery flow.

### 3. Use Documented Auth Patterns

Authentication is handled by `pac auth create` (for PAC CLI) and `scripts/auth.py` (for Python scripts and the SDK).

**NEVER:**
- Read or parse raw token cache files (e.g., `tokencache_msalv3.dat`)
- Implement your own MSAL device-code flow
- Hard-code tokens or credentials in scripts
- Invent a new auth mechanism

If auth is expired or missing, re-run `pac auth create` or check `.env` credentials. See the setup skill.

### 4. Follow Skill Instructions, Don't Improvise

Each skill documents a specific, tested sequence of steps. Follow them. If a skill says "use the Python SDK," use the Python SDK — do not substitute a raw HTTP call, a different library, or a different language. If a skill says "run this command," run that command — do not invent an alternative.

If you hit a gap (something the skills don't cover), say so honestly and suggest a workaround. Do not hallucinate a path or improvise a solution using tools the skills don't mention.

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

## Multi-Environment Rule (MANDATORY)

Pro-dev scenarios involve multiple environments (dev, test, staging, prod) and multiple sets of credentials. **Never assume** the active PAC auth profile, values in `.env`, or anything from memory or a previous session reflects the correct target for the current task.

**Before the FIRST operation that touches a specific environment** — creating a table, deploying a plugin, pushing a solution, inserting data — you MUST:

1. Show the user the environment URL you intend to use
2. Ask them to confirm it is correct
3. Run `pac org who` to verify the active connection matches

> "I'm about to make changes to `<URL>`. Is this the correct target environment?"

**Do not proceed until the user explicitly confirms.** This is the single most important safety check in the plugin. Skipping it risks making irreversible changes to the wrong environment.

Once confirmed for a session, you do not need to re-confirm for every subsequent operation in the same session against the same environment.

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

**Tool priority (always follow this order):** MCP (if available) for simple reads, queries, and ≤10 record CRUD → Python SDK for scripted data, bulk operations, schema creation, and analysis → Web API for operations the SDK doesn't cover (forms, views, option sets) → PAC CLI for solution lifecycle. MCP tools not in your tool list? → Load `dataverse-mcp-configure` to set them up (see below).

**Volume guidance:** MCP `create_record` is fine for 1–10 records. For 10+ records, use Python SDK `client.records.create(table, list_of_dicts)` — it uses `CreateMultiple` internally and handles batching. For data profiling and analytics beyond simple GROUP BY, use Python with pandas (see python-sdk skill). For aggregation queries (`$apply`), use the Web API directly.

Note: The Python SDK is in **preview** — breaking changes possible.

### MCP Availability Check

If the user's request involves MCP — either explicitly ("connect via MCP", "use MCP", "query via MCP") or implicitly (conversational data queries where MCP would be the natural tool) — check whether Dataverse MCP tools are available in your current tool list (e.g., `list_tables`, `describe_table`, `read_query`, `create_record`).

**If MCP tools are NOT available and the user explicitly asked for MCP:**
1. **Do NOT silently fall back** to the Python SDK or Web API
2. Tell the user: "Dataverse MCP tools aren't configured in this session yet."
3. Load the `dataverse-mcp-configure` skill to set up the MCP server
4. After MCP is configured, **stop here** — the session must be restarted for MCP tools to appear (if running in Claude Code, remind them to resume the session correctly: "Remember to **use `claude --continue` to resume the session** without losing context"). Do not fall back to the SDK or proceed with other tools. Wait for the user to restart and come back.

**If MCP tools are NOT available and the user asked a simple data question** (e.g., "how many accounts with 'jeff'?"):
1. Answer the question using the Python SDK (don't block the user)
2. After answering, suggest: "This would be even simpler with MCP configured — want me to set that up?"

**If MCP tools ARE available**, prefer MCP for simple reads/queries/small CRUD. Use the SDK only when a script is needed.

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

## Before Any Metadata Change: Confirm Solution

Before creating tables, columns, or other metadata, ensure a solution exists to contain the work:

1. Ask the user: "What solution should these components go into?"
2. If a solution name is in `.env` (`SOLUTION_NAME`), confirm it with the user
3. If no solution exists yet, create one (see the `solution` skill)
4. Use the `MSCRM.SolutionName` header on all Web API metadata calls to auto-add components

Creating metadata without a solution means it exists only in the default solution and cannot be cleanly exported or deployed. Always solution-first.

---

## After Any Change: Pull to Repo (MANDATORY)

Any time you make a metadata change (via MCP, Web API, or the maker portal), **you must** end the session by pulling:

```bash
pac solution export --name <SOLUTION_NAME> --path ./solutions/<SOLUTION_NAME>.zip --managed false
pac solution unpack --zipfile ./solutions/<SOLUTION_NAME>.zip --folder ./solutions/<SOLUTION_NAME>
rm ./solutions/<SOLUTION_NAME>.zip
git add ./solutions/<SOLUTION_NAME>
git commit -m "feat: <description>"
git push
```

The repo is always the source of truth.

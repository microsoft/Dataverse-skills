---
name: dv-overview
description: Tool routing and cross-cutting rules for Dataverse work — which skill applies to which task, environment-confirmation, and pull-to-repo. Use when the user mentions Dataverse, Dynamics 365, Power Platform, or CRM; this skill picks the specialist (dv-connect / dv-data / dv-metadata / dv-query / dv-solution / dv-admin / dv-security) for the request.
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
- If EITHER is missing: **Automatically run the connect flow** (see the `dv-connect` skill). Do NOT ask the user whether to initialize — just do it. Do not create your own `.env`, `requirements.txt`, `.env.example`, or auth scripts. The `dv-connect` skill handles all of this.

Do NOT create `requirements.txt`, `.env.example`, or scaffold files manually. The connect flow produces the correct file structure. Skipping it is the #1 cause of broken setups.

### 1. Python Only for Scripts — CLI Allowed for Gap-Filling

All **scripts**, data operations, and automation MUST use **Python**. This plugin's entire toolchain — `scripts/auth.py`, the Dataverse SDK, all skill examples — is Python-based.

**The Dataverse CLI** (`npx @microsoft/dataverse`) is acceptable for single-record operations and gap-filling (N:N associations, uncapped reads, MCP-down fallback). It is a shell tool invocation, not a scripting language — do not write `.js` files or Node.js scripts.

**NEVER:**
- Run `npm init` or write JavaScript/TypeScript/PowerShell scripts
- Install packages via `npm`, `yarn`, or `pnpm` (except `@microsoft/dataverse` which is a CLI tool)
- Use `@azure/msal-node`, `@azure/identity` (Node.js), or any Node.js Azure SDK
- Import or reference `node_modules/`

**ALWAYS:**
- Use `pip install` for Python packages
- Use `scripts/auth.py` for authentication tokens and credentials
- Use the Python Dataverse SDK (`PowerPlatform-Dataverse-Client`) for bulk operations, DataFrames, and schema operations
- Use `azure-identity` (Python) for Azure credential flows
- Use the Dataverse CLI for simple CRUD when MCP is unavailable, N:N associations, and uncapped reads

If you find yourself about to create a `package.json` or write a `.js` file, STOP. You are going off-rails.

### 2. MCP → CLI → SDK → Web API (in that order)

**Before writing ANY code, ask: can MCP handle this?** If MCP tools are available in your tool list (`list_tables`, `describe_table`, `read_query`, `create_record`, etc.):

- **Writes:** ≤10 records → use MCP directly. 10+ records → use Python SDK (`dv-data`).
- **Reads:** Simple filter, small result set (no paging needed) → use MCP. Multi-page iteration, DataFrame loading, aggregation, or queries hitting SQL limits → use Python SDK (`dv-query`).

**If MCP is unavailable** (not configured, 403, tools not in tool list):

- **Simple CRUD (≤10 records):** Use the Dataverse CLI — one shell command, no Python needed. See `dv-data` for CLI write commands, `dv-query` for CLI read commands.
- **N:N associate/disassociate:** Always use CLI `data associate`/`data disassociate` (regardless of MCP availability — MCP does not support N:N).
- **Bulk operations (10+ records), DataFrames, analytics:** Use the Python SDK (`dv-data` / `dv-query`).
- **Forms, views, `$apply`, global option sets, N:N `$expand`:** Use raw Web API (`get_token()`).

**SDK checklist — evaluate EVERY time you write a script:**
- Creating/updating/deleting records? → `client.records.create()`, `.update()`, `.delete()` — see `dv-data`
- Bulk record operations? → `client.records.create(table, [list_of_dicts])` — see `dv-data`
- Querying or filtering records? → `client.records.get(table, select=[...], filter="...")` — see `dv-query`
- Aggregation? → Single-table: `$apply` (raw Web API). Cross-table: `client.dataframe.get()` + `pd.merge()` — see `dv-query`
- Loading data into pandas? → `client.dataframe.get(table)` — see `dv-query`
- Creating tables, columns, relationships? → `client.tables.create()`, `.add_columns()` — see `dv-metadata`
- Creating publishers or solutions? → `client.records.create("publisher", {...})` — see `dv-solution`

**Raw Web API (`get_token()`) is ONLY acceptable for:** forms, views, global option sets, N:N `$expand`, `$apply` aggregation, memo columns, and unbound actions. Everything else MUST use MCP → CLI → SDK.

**Field casing:** `$select`/`$filter` use lowercase logical names (`new_name`). `$expand` and `@odata.bind` use Navigation Property Names that are case-sensitive and must match `$metadata` (e.g., `new_AccountId`). Getting this wrong causes 400 errors.

**Publisher prefix:** Never hardcode a prefix (especially not `new`). Always query existing publishers in the environment and ask the user which to use. See the solution skill's publisher discovery flow.

For the full tool capabilities table, volume guidance, and MCP availability check flow, see [`references/tool-routing.md`](references/tool-routing.md).

### 3. Use Documented Auth Patterns

Authentication is handled by `pac auth create` (for PAC CLI) and `scripts/auth.py` (for Python scripts and the SDK).

**NEVER:**
- Read or parse raw token cache files (e.g., `tokencache_msalv3.dat`)
- Implement your own MSAL device-code flow
- Hard-code tokens or credentials in scripts
- Invent a new auth mechanism

If auth is expired or missing, re-run `pac auth create` or check `.env` credentials. See the `dv-connect` skill.

### 4. Follow Skill Instructions, Don't Improvise

Each skill documents a specific, tested sequence of steps. Follow them. If a skill says "use the Python SDK," use the Python SDK — do not substitute a raw HTTP call, a different library, or a different language. If a skill says "run this command," run that command — do not invent an alternative.

**Do NOT introspect the SDK** with `dir()`, `inspect.signature()`, or `help()` to discover APIs. The skills document the exact methods and parameters to use. If a method call fails with `AttributeError`, the installed SDK version may not have it — check the version note in the skill and fall back to the documented alternative. Introspecting the SDK wastes time and leads to using deprecated or internal APIs.

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

## Tool Capabilities

**Tool priority:** MCP → Dataverse CLI → Python SDK → Raw Web API → PAC CLI. See [`references/tool-routing.md`](references/tool-routing.md) for the full tool capabilities table, volume guidance, and MCP availability check flow. MCP tools not in your tool list? → Load `dv-connect` to set them up.

---

## Available Skills

Each skill's frontmatter contains WHEN/DO NOT USE WHEN triggers that Claude uses for automatic routing. This index is for human reference only.

| Skill | What it covers |
| --- | --- |
| **dv-connect** | Connect to Dataverse: install tools, authenticate, create `.env`, configure MCP, verify connection |
| **dv-metadata** | Create/modify tables, columns, relationships (SDK), forms and views (Web API) |
| **dv-data** | Record CRUD, bulk create/update/upsert, CSV import with lookup resolution, multi-table FK-ordered import, file uploads, alternate key upserts, sample data generation |
| **dv-query** | Bulk reads, multi-page iteration, OData queries, QueryBuilder, `$expand`, `$apply` aggregation (Web API), GUID-free display, pandas DataFrame handoff, Jupyter notebook snippets |
| **dv-solution** | Solution create/export/import/pack/unpack, post-import validation |
| **dv-admin** | Bulk delete, data retention/archival, org settings (audit, plugin trace, session timeout), OrgDB settings (MCP, search, copilot, fabric), recycle bin. PAC CLI for bulk delete/retention/org settings; Python SDK for OrgDB XML and recycle bin. Multi-environment: parallel with `&` and `wait` |
| **dv-security** | Role assignment (`pac admin assign-user`), self-elevation (`pac admin self-elevate`). **PAC CLI only** |

---

## Scripts

The plugin ships utility scripts in `scripts/`:

| Script | Purpose |
| --- | --- |
| `auth.py` | Azure Identity token/credential acquisition — used by all other scripts and the SDK |

For data write operations (create, update, bulk import), see `dv-data`. For queries, aggregation, and analytics, see `dv-query`. For post-import validation queries, see `dv-solution`.

Any Web API call that goes beyond a one-off query should be written as a Python script and committed to `/scripts/`. Use `scripts/auth.py` for token acquisition.

---

## Windows Scripting Rules

When running in Git Bash on Windows (the default for Claude Code on Windows):

- **ASCII only in `.py` files.** Curly quotes, em dashes, or other non-ASCII characters cause `SyntaxError`. Use straight quotes and regular dashes.
- **No `python -c` for multiline code.** Shell quoting differences between Git Bash and CMD break multiline `python -c` commands. Write a `.py` file instead.
- **PAC CLI may need a PowerShell wrapper.** If `pac` hangs or fails in Git Bash, use `powershell -Command "& pac.cmd <args>"`. See the setup skill for details.
- **Generate GUIDs in Python scripts**, not via shell backtick-substitution: `str(uuid.uuid4())` inside the `.py` file.
- **Background job output may be empty on Windows.** Claude Code's background task runner ("Running in the background") can silently produce no output on Windows. Always use `python -u` (unbuffered stdout) and `print(..., flush=True)` in long-running scripts. For foreground execution with logging: `python -u scripts/import_data.py 2>&1 | tee /tmp/out.txt`. Do NOT assume a background task succeeded just because it appeared to finish.

---

## Before Any Metadata Change: Confirm Solution

Before creating tables, columns, or other metadata, ensure a solution exists to contain the work:

1. Ask the user: "What solution should these components go into?"
2. If a solution name is in `.env` (`SOLUTION_NAME`), confirm it with the user
3. If no solution exists yet, **load the `dv-solution` skill** and follow its publisher discovery + solution creation flow. Use the SDK — **never raw Web API** — to create publisher and solution records:

```python
# Quick reference — full pattern with publisher discovery is in dv-solution
publisher_id = client.records.create("publisher", {
    "uniquename": "<name>", "friendlyname": "<display>",
    "customizationprefix": "<prefix>", "description": "<desc>",
})
solution_id = client.records.create("solution", {
    "uniquename": "<Name>", "friendlyname": "<Display>",
    "version": "1.0.0.0",
    "publisherid@odata.bind": f"/publishers({publisher_id})",
})
```

4. Pass `solution="<UniqueName>"` on all SDK calls, or include `"MSCRM.SolutionName": "<UniqueName>"` header on raw Web API metadata calls.

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


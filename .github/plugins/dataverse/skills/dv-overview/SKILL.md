---
name: dv-overview
description: Foundational cross-cutting context for Dataverse / Power Platform work — scope and the skill map, the tool-capability reference, the safety rules, and the safe change lifecycle. Use when the user mentions Dataverse, Dynamics 365, Power Platform, or CRM; load this first for orientation. Specialist skills self-route via their own frontmatter triggers.
---

# Skill: Overview — What to Use and When

Load this skill first for any Dataverse work — it holds the cross-cutting context every task needs: scope, the tool-capability reference, the hard rules, and the change lifecycle. It does **not** route; the agent auto-selects specialist skills via their own WHEN/DO NOT USE WHEN frontmatter triggers. Users describe what they want in plain English; the agent chains skills automatically and never asks the user to name a skill or command.

---

## What This Plugin Covers

Dataverse / Power Platform work for **every persona** — builders and agent devs, data scientists, environment admins, and business users — delivered by specialist skills. The agent loads and routes to these automatically via their frontmatter triggers — you never invoke them by name.

| Area | Skill |
| --- | --- |
| Connect, authenticate, configure MCP, verify the environment | `dv-connect` |
| Schema — tables, columns, relationships, forms, views; inspect existing schema | `dv-metadata` |
| Data writes — record CRUD, bulk create/update/upsert, CSV/FK-ordered import, sample data | `dv-data` |
| Data reads & analytics — OData queries, QueryBuilder, FetchXML (aggregation + N:N joins), DataFrames | `dv-query` |
| Solution ALM — create, export, import, pack/unpack, post-import validation | `dv-solution` |
| Environment administration — bulk delete, retention/archival, org & OrgDB settings, recycle bin | `dv-admin` |
| Security & access — roles, users, application users, business units, self-elevation (PAC CLI) | `dv-security` |

**Model-driven apps:** the building blocks (tables, forms, views) are covered by `dv-metadata`; composing the app shell itself — site map and navigation — is **not yet** a first-class skill.

**Out of scope:**

- **Canvas apps** — a different technology; use `pac canvas` or the maker portal
- **Power Automate flows** — use the maker portal or the Power Automate Management API
- **Azure infrastructure** beyond what's needed for service-principal setup
- **Business Central** or other Dynamics products

---

## Hard Rules — Read These First

The safety rules (init state, auth, environment confirmation, no bespoke MSAL) are non-negotiable. The tool-selection guidance (Rules 1, 2, 4) is capability-based — strong defaults, not rigid mandates.

### 0. Check Init State Before Anything Else

Before writing ANY code or creating ANY files, check if the workspace is initialized:

```bash
ls .env scripts/auth.py 2>/dev/null
```

- If BOTH exist: workspace is initialized. Proceed to the relevant task.
- If EITHER is missing: **Automatically run the connect flow** (see the `dv-connect` skill). Do NOT ask the user whether to initialize — just do it. Do not create your own `.env`, `requirements.txt`, `.env.example`, or auth scripts. The `dv-connect` skill handles all of this.

Do NOT create `requirements.txt`, `.env.example`, or scaffold files manually. The connect flow produces the correct file structure. Skipping it is the #1 cause of broken setups.

### 1. Python for scripting; the CLIs and MCP are first-class

Python is the language for automation **logic** (transformation, control flow, retry, CSV). The toolchain (`scripts/auth.py`, the SDK, skill examples) is Python-based. But MCP tools, the Dataverse CLI (`dataverse`), the Python SDK, and the PAC CLI (`pac`) are all **first-class tool invocations** — use whichever fits. The Dataverse CLI has the same standing as `pac`, which is invoked freely across the solution, metadata, and plug-in skills.

**NEVER:**
- Write automation *logic* in JavaScript/TypeScript/Node.js (`npm`, `yarn`, `pnpm`, `package.json`, `node_modules/`)
- Use `@azure/msal-node`, `@azure/identity`, or any Node.js Azure SDK
- Implement a bespoke MSAL / device-code flow — auth is `scripts/auth.py`, `pac auth`, and the Dataverse CLI

**ALWAYS:**
- Use `pip install` and the Python SDK (`PowerPlatform-Dataverse-Client`) for data and schema logic
- Use `scripts/auth.py` for tokens/credentials; `azure-identity` (Python) for Azure credential flows
- Treat the Dataverse CLI (`dataverse`) and `pac` as allowed first-party CLIs

About to run `npm` or create a `package.json`? STOP — that is off-rails. Reaching for `pac` or the Dataverse CLI is not.

### 2. Pick the surface that fits — capability awareness, not a fixed order

No mandated tool order. Each surface has a capability profile; pick what fits the job and the surface you are already in — soft defaults, not a required sequence. The full matrix is in **Tool Capabilities** below; the principles:

- Prefer a managed surface (MCP, the Dataverse CLI, or the SDK) over hand-rolled raw OData — they carry auth, paging, retry, and geo routing that raw HTTP re-implements. When MCP can't handle it (bulk, large reads, schema creation, multi-step workflows, analytics, or MCP isn't available), the **Python SDK** is the default.
- **Raw Web API is the last-resort escape hatch** for surfaces with no managed path (forms, views, global option sets, and anything without a first-class SDK/CLI command) — and even then prefer `dataverse api` (managed auth, exit codes) over hand-rolled `urllib`/`get_token`. Aggregation and N:N joins are *not* raw-only: use `client.query.fetchxml()` (aggregates + link-entity), or the CLI's `data associate` for N:N writes.
- If an SDK method fails or a PAC command seems missing, check the relevant skill before hand-rolling raw HTTP.

**Field casing:** `$select`/`$filter` use lowercase logical names (`new_name`). `$expand` and `@odata.bind` use Navigation Property Names that are case-sensitive and must match `$metadata` (e.g., `new_AccountId`). Getting this wrong causes 400 errors. **SDK record payloads:** provide the correct SchemaName casing on `@odata.bind` keys (e.g., `new_AccountId@odata.bind`); the SDK does not auto-correct wrong casing. **Raw Web API calls** (forms, views, metadata): casing is entirely manual — a lowercase `new_accountid@odata.bind` will 400.

**Publisher prefix:** Never hardcode a prefix (especially not `new`). Always query existing publishers in the environment and ask the user which to use. The prefix is permanent on every component created with it. See the solution skill's publisher discovery flow.

### 3. Use Documented Auth Patterns

Three entry points, one shared sign-in:
- **`dataverse auth create`** (Dataverse CLI) writes a shared MSAL token cache under the DataverseCLI app registration. That single sign-in serves the CLI, the `@microsoft/dataverse` MCP proxy, **and** `scripts/auth.py` — which silently reuses the same cache via `msal-extensions` (the sanctioned MSAL API, not raw-file parsing), so Python scripts and the SDK don't prompt again.
- **`scripts/auth.py`** is the auth entry point for all Python/SDK code. Its order: service principal (`CLIENT_ID` + `CLIENT_SECRET` in `.env`) → shared Dataverse CLI cache → device-code fallback. Use `get_client(skill)` (SDK) or `get_plugin_headers(skill, get_token())` (raw Web API) — both stamp the skill attribution; bare `get_token()` does not.
- **`pac auth create`** (PAC CLI) authenticates `pac` for `dv-solution` and `dv-admin`.

**Telemetry attribution (keep it deterministic):** every request carries a closed-schema `app=dataverse-skills/<ver>;skill=<skill>;agent=<agent>` context so the server sees which skill routed each OData call. It is baked in — `get_client(skill)` and `get_plugin_headers(skill, ...)` stamp it on the SDK and raw-HTTP paths; the Dataverse CLI auto-stamps `DataverseCli/<ver>` + the command, and you add the skill with `--context "(app=dataverse-skills/<ver>;skill=<skill>;agent=<agent>)"`. Never modify, omit, or free-form this context — it is a closed schema (allowlisted skill/agent, no PII).

**NEVER:**
- Read or parse raw token cache files (e.g., `tokencache_msalv3.dat`) — reuse the cache only through `scripts/auth.py` / `msal-extensions`
- Implement your own MSAL device-code flow
- Hard-code tokens or credentials in scripts
- Invent a new auth mechanism

If auth is expired or missing, re-run `dataverse auth create` (or `pac auth create` for `pac`), or check `.env` credentials. See the `dv-connect` skill.

### 4. Be honest about gaps — don't hallucinate

Each skill documents a tested sequence — follow it when it fits. The skills are the source of truth for the supported, non-deprecated API. If a call fails with `AttributeError`, the installed SDK version may not have it — check the skill's version note and use the documented alternative.

**The honesty guard:** if you hit a gap the skills don't cover, say so and suggest a workaround. **Do not hallucinate an unsupported path** — do not invent a method, parameter, or endpoint that isn't documented. If unsure, say so.

---

## Tool Capabilities — Which Tool for Which Job

Understanding the real limits of each tool prevents hallucinated paths. This is the one piece of context no individual skill owns.

| Tool | Use for | Does NOT support |
| --- | --- | --- |
| **MCP Server** | Data CRUD (create/read/update/delete records), table create/update/delete/list/describe, column add via `update_table`, keyword search, single-record fetch | Forms, Views, Relationships, Option Sets, Solutions. **Note:** table creation may timeout but still succeed — always `describe_table` before retrying. Run queries sequentially (parallel calls timeout). Column names with spaces normalize to underscores (e.g., `"Specialty Area"` → `cr9ac_specialty_area`). **SQL limitations:** The `read_query` tool uses Dataverse SQL, which does NOT support: `DISTINCT`, `HAVING`, subqueries, `OFFSET`, `UNION`, `CASE`/`IF`, `CAST`/`CONVERT`, or date functions. For analytical queries that need these (e.g., finding duplicates, unmatched records, filtered aggregates), use `$apply` (single-table aggregation) or `client.dataframe.get()` with pandas (cross-table) — see `dv-query`. **Bulk operations:** MCP `create_record` creates one record at a time. For 10+ records, use the Python SDK `CreateMultiple` instead — see `dv-data`. |
| **Python SDK (`dv-data`)** | **Preferred for all scripted data writes.** Record CRUD, upsert (alternate keys), bulk create/update/upsert (CreateMultiple/UpdateMultiple/UpsertMultiple), CSV import with lookup resolution, file column uploads (chunked >128MB) | Forms, Views, global Option Sets, record association (`$ref`), `$apply` aggregation, N:N `$expand`, table/column/relationship creation (use `dv-metadata`), custom action invocation |
| **Python SDK (`dv-query`)** | **Preferred for bulk reads and analytics.** Multi-page record iteration, OData queries (select/filter/expand/orderby), QueryBuilder fluent API, GUID-free display (formatted values), `$expand` to resolve lookups, **aggregation and N:N joins via `client.query.fetchxml()`** (aggregate FetchXML + link-entity), pandas DataFrame handoff (`client.dataframe.get()`) for cross-table joins and exports, Jupyter notebook snippets | OData `$apply` and N:N `$expand` on the OData builder path (use `fetchxml` or raw Web API instead) |
| **Dataverse CLI (`dataverse`)** | Headless data plane (no Python script needed): `data` CRUD (`query/get/create/update/upsert/delete/count`), `data associate`/`disassociate` (N:N + lookups via `$ref`), `data upload` (file columns); `api request`/`invoke` (managed Web API escape hatch + Custom API discovery); shared `auth`/`org` token cache | Metadata/schema creation (use SDK — `dv-metadata`), solution ALM (use PAC), forms/views authoring |
| **PAC CLI** | Solution export/import/pack/unpack, environment create/list/delete/reset, auth profile management, plugin updates (`pac plugin push` — first-time registration requires Web API), user/role assignment (`pac admin assign-user`), add solution components (`pac solution add-solution-component`) | Data CRUD, metadata creation (tables/columns/forms), listing solution components (no `list-components` — query `solutioncomponent` via SDK/CLI) |
| **Azure CLI** | App registrations, service principals, credential management | Dataverse-specific operations |
| **GitHub CLI** | Repo management, GitHub secrets, Actions workflow status | Dataverse-specific operations |
| **Raw Web API** (last resort) | Only when **no** managed surface exposes the operation — i.e. not doable via MCP, the Python SDK, the Dataverse CLI, or the `dataverse api` escape hatch. Genuine cases: form/view (FormXml) authoring, global option sets, and similar edge cases. Even then, prefer `dataverse api` (managed auth + skill attribution) over hand-rolled `urllib`. | Functionally nothing (full OData/MetadataService) — but raw `urllib` bypasses managed auth, paging, retry, and skill attribution, so treat it as the path of last resort |

**Routing:** the table shows what each surface does; the *how to choose* principle (soft defaults, not a fixed order) is Hard Rule 2. MCP tools not in your list? Load `dv-connect`.

**Volume guidance:** MCP for a handful of records or simple filters; the SDK's `CreateMultiple` for bulk writes (chunk large sets starting ~1,000 — see `dv-data`) and `dv-query` for bulk reads (streams pages, avoids MCP SQL limits); Web API for `$apply` aggregation.

**SDK method cheat-sheet** (anti-hallucination, *not* a preference signal): SDK method names are the least discoverable surface — MCP tools appear in your tool list and the CLI self-documents via `dataverse --help`, but SDK calls surface nowhere, so agents invent them. This maps common ops to the exact call. Each op is equally reachable via MCP/CLI per Hard Rule 2; see the noted skill for the full pattern.

| Operation | SDK call | Skill |
| --- | --- | --- |
| Create / update / delete records | `client.records.create()` / `.update()` / `.delete()` (pass a list for bulk) | `dv-data` |
| Upsert on an alternate key | `client.records.upsert()` | `dv-data` |
| Query / filter records | `client.records.list(...)` (flat) or `.list_pages(...)` (streaming) | `dv-query` |
| One record by GUID | `client.records.retrieve(table, guid)` (`None` if missing) | `dv-query` |
| Aggregation / server-side joins | `client.query.fetchxml(xml)` (aggregates + link-entity) | `dv-query` |
| Fluent query build (chainable) | `client.query.builder(Table).where(...).execute()` | `dv-query` |
| Limited SQL read | `client.query.sql("SELECT ...")` | `dv-query` |
| Load into pandas | `client.dataframe.get(table, select=[...])` | `dv-query` |
| Upload to a file column | `client.files.upload(...)` | `dv-data` |
| Create tables / columns / lookups / N:N | `client.tables.create()` / `.add_columns()` / `.create_lookup_field()` / `.create_many_to_many_relationship()` | `dv-metadata` |
| Create an alternate key (enables upsert) | `client.tables.create_alternate_key(...)` | `dv-metadata` |
| Inspect existing schema | `client.tables.list_columns()` / `.list_relationships()` | `dv-metadata` |
| Create publisher / solution | `client.records.create("publisher" / "solution", {...})` | `dv-solution` |

### MCP Availability Check

If the user's request involves MCP — either explicitly ("connect via MCP", "use MCP", "query via MCP") or implicitly (conversational data queries where MCP would be the natural tool) — check whether Dataverse MCP tools are available in your current tool list (e.g., `list_tables`, `describe_table`, `read_query`, `create_record`).

**If MCP tools are NOT available and the user explicitly asked for MCP** (e.g., "use MCP to query", "why isn't MCP working"):
1. **Do NOT silently fall back** to the Python SDK or Web API
2. Tell the user: "Dataverse MCP tools aren't configured in this session yet."
3. Load the `dv-connect` skill to set up the MCP server
4. After MCP is configured, **stop here** — the session must be restarted for MCP tools to appear. Remind the user to resume the session without losing context (Claude Code: `claude --continue`; Cursor: reload the window with Ctrl+Shift+P → "Developer: Reload Window"; Copilot: reopen the Copilot panel). Do not proceed with SDK. Wait for the user to restart.

**If MCP tools are NOT available and the user asked a data question without explicitly requesting MCP** (e.g., "how many accounts with 'jeff'?", "show me open tickets"):
1. This is a SDK fallback case — use the Python SDK to answer the question. Do not block the user.
2. After answering, offer: "MCP would handle this conversationally — want me to set it up?"

The distinction matters: explicit MCP request → block and set up MCP. Implicit/conversational question → answer with SDK, offer MCP setup.

**If MCP tools ARE available**, prefer MCP for simple reads/queries/small CRUD. Use the SDK only when a script is needed.

---

## The Change Lifecycle — Operate Safely

For any real change, walk these three steps in order: confirm **where**, confirm the **container**, then persist the **result**.

### Step 1 — Confirm the Environment (MANDATORY)

Dataverse work often spans multiple environments (dev, test, staging, prod) and multiple sets of credentials. **Never assume** the active PAC auth profile, values in `.env`, or anything from memory or a previous session reflects the correct target for the current task.

**Before the FIRST operation that touches a specific environment** — creating a table, deploying a plugin, pushing a solution, inserting data — you MUST:

1. Show the user the environment URL you intend to use
2. Ask them to confirm it is correct
3. Run `pac org who` to verify the active connection matches

> "I'm about to make changes to `<URL>`. Is this the correct target environment?"

**Do not proceed until the user explicitly confirms.** This is the single most important safety check in the plugin. Skipping it risks making irreversible changes to the wrong environment. Once confirmed for a session, you do not need to re-confirm for every subsequent operation in the same session against the same environment.

### Step 2 — Confirm the Solution (before any metadata change)

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

### Step 3 — Pull to Repo (MANDATORY)

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

---

## Scripts

The plugin ships `scripts/auth.py` (Azure Identity token/credential acquisition — used by all other scripts and the SDK). Any Web API call beyond a one-off query should be a Python script committed to `/scripts/`, using `scripts/auth.py` for tokens. For writes see `dv-data`; queries and analytics see `dv-query`; post-import validation see `dv-solution`.

---

## Windows Scripting

Platform-specific shell rules (ASCII in `.py`, no multiline `python -c`, PAC PowerShell wrapper, unbuffered background output) live in [`references/windows-scripting.md`](references/windows-scripting.md). Read it when running on Windows.


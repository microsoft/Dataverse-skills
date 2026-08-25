---
name: dv-overview
description: Foundational cross-cutting context for Dataverse / Power Platform work — scope and the skill map, the tool-capability reference, the safety rules, and the safe change lifecycle. Use when the user mentions Dataverse, Dynamics 365, Power Platform, CRM, or ERP; load this first for orientation. Specialist skills self-route via their own frontmatter triggers.
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
| Finance and Operations X++ — author, build, deploy, DB sync, verify | `dv-xpp` |
| Environment administration — bulk delete, retention/archival, org & OrgDB settings, recycle bin | `dv-admin` |
| Security & access — roles, users, application users, business units, self-elevation (PAC CLI) | `dv-security` |

**Model-driven apps:** the building blocks (tables, forms, views) are covered by `dv-metadata`; composing the app shell itself — site map and navigation — is **not yet** a first-class skill.

**Out of scope:**

- **Canvas apps** — a different technology; use `pac canvas` or the maker portal
- **Power Automate flows** — use the maker portal or the Power Automate Management API
- **Azure infrastructure** beyond what's needed for service-principal setup
- **Business Central** or other Dynamics products

---

## Hard Rules

Safety rules (init, auth, env confirmation) are non-negotiable. Tool selection (Rules 1, 2, 4) is capability-based.

### 0. Check Init State First

Before writing ANY code or creating ANY files, **actively search your callable tools for any tool whose name or description contains `dataverse`** (tools may be registered under environment-specific names like `mcp__dataverse_<orgid>__read_query`, not just generic names). **If any Dataverse MCP tool is found, use it directly — skip the init check and all setup.** MCP auth is host-managed and does not need `.env` or `scripts/auth.py`. Never declare MCP unavailable based solely on the initially displayed tool list.

If no MCP tool is found, check for an existing CLI profile — it's the fastest path for data operations:

```bash
dataverse auth who
```

If that shows an active profile with an environment URL, use CLI directly for data operations (see `dv-query`/`dv-data` examples) — no `.env`, `auth.py`, or workspace setup needed. For explicit "connect" or "set up" requests, run `dv-connect` regardless — it configures MCP, SDK, and PAC.

If no CLI profile exists, check workspace init:

```bash
ls .env scripts/auth.py 2>/dev/null
```

- If BOTH exist: proceed to the task.
- If EITHER is missing: run `python <plugin-scripts>/auth.py --ping`. If it prints `REACHABLE` (exit 0), the workspace is bootable without pip -- confirm the URL and proceed. If `--ping` fails, **run `dv-connect`**.

### 1. Python for scripting; the CLIs and MCP are first-class

Python is the language for automation **logic** (transformation, control flow, retry, CSV). The toolchain (`scripts/auth.py`, the SDK, skill examples) is Python-based. But MCP tools, the Dataverse CLI (`dataverse`), the Python SDK, and the PAC CLI (`pac`) are all **first-class tool invocations** — use whichever fits. The Dataverse CLI has the same standing as `pac`, which is invoked freely across the solution and metadata skills.

**NEVER:**
- Write automation *logic* in JavaScript/TypeScript/Node.js (`npm`, `yarn`, `pnpm`, `package.json`, `node_modules/`)
- Use `@azure/msal-node`, `@azure/identity`, or any Node.js Azure SDK
- Implement a bespoke MSAL / device-code flow — auth is `scripts/auth.py`, `pac auth`, and the Dataverse CLI

**ALWAYS:**
- Use `pip install` and the Python SDK (`PowerPlatform-Dataverse-Client`) for data and schema logic
- Use `scripts/auth.py` for tokens/credentials; `azure-identity` (Python) for Azure credential flows
- Treat the Dataverse CLI (`dataverse`) and `pac` as allowed first-party CLIs

### 2. Pick the surface that fits — capability awareness, not a fixed order

No mandated tool order. Each surface has a capability profile; pick what fits the job and the surface you are already in — soft defaults, not a required sequence. The full matrix is in **Tool Capabilities** below; the principles:

- Prefer a managed surface (MCP, the Dataverse CLI, or the SDK) over hand-rolled raw OData — they carry auth, paging, retry, and geo routing that raw HTTP re-implements. When MCP can't handle it (bulk >25 records, large reads, advanced schema like forms/views/N:N relationships/global option sets/alternate keys, multi-step workflows, analytics, or MCP isn't available), the **Python SDK** is the default.
- **Raw Web API is the last-resort escape hatch** for surfaces with no managed path (unbound actions like `PublishXml`, global option sets, anything without a first-class SDK/CLI command) — and even then prefer `dataverse api` (managed auth, exit codes) over hand-rolled `urllib`/`get_token`. Forms/views are **not** raw-only (SDK `records.create`/`update` on `systemform`/`savedquery`; only `PublishXml` needs `dataverse api`). Aggregation/N:N joins aren't raw-only either: `client.query.fetchxml()` (aggregates + link-entity), or the CLI's `data associate` for N:N writes.
- If an SDK method fails or a PAC command seems missing, check the relevant skill before hand-rolling raw HTTP.

**Field casing:** `$select`/`$filter` use lowercase logical names (`new_name`). `$expand` and `@odata.bind` use Navigation Property Names that are case-sensitive and must match `$metadata` (e.g., `new_AccountId`). Getting this wrong causes 400 errors. **SDK record payloads:** provide the correct SchemaName casing on `@odata.bind` keys (e.g., `new_AccountId@odata.bind`); the SDK does not auto-correct wrong casing. **Raw Web API calls** (forms, views, metadata): casing is entirely manual — a lowercase `new_accountid@odata.bind` will 400.

**Publisher prefix:** Never hardcode a prefix (especially `new`); query existing publishers and ask the user. The prefix is permanent. See the solution skill's publisher discovery flow.

### 3. Use Documented Auth Patterns

Three entry points, one shared sign-in:
- **`dataverse auth create`** (Dataverse CLI) writes a shared MSAL token cache. That sign-in serves CLI, MCP proxy, **and** `scripts/auth.py` via `msal-extensions`.
- **`scripts/auth.py`** is the Python/SDK auth entry point. Order: service principal → shared CLI cache → device-code. Use `get_client(skill)` (SDK) or `get_plugin_headers(skill, get_token())` (raw Web API) — both stamp attribution.
- **`pac auth create`** (PAC CLI) authenticates `pac` for `dv-solution`, `dv-admin`, and `dv-xpp`.

**Telemetry attribution (keep it deterministic):** every request carries a closed-schema `app=dataverse-skills/<ver>;skill=<skill>;agent=<agent>` context so the server sees which skill routed each OData call. It is baked in — `get_client(skill)` and `get_plugin_headers(skill, ...)` stamp it on the SDK and raw-HTTP paths; the Dataverse CLI auto-stamps `DataverseCli/<ver>` + the command, and you add the skill with `--context "app=dataverse-skills/<ver>;skill=<skill>;agent=<agent>"` (the CLI wraps it in parentheses itself — do not pre-wrap). Never modify, omit, or free-form this context — it is a closed schema (allowlisted skill/agent, no PII).

**NEVER:**
- Read or parse raw token cache files (e.g., `tokencache_msalv3.dat`) — reuse the cache only through `scripts/auth.py` / `msal-extensions`
- Implement your own MSAL device-code flow
- Hard-code tokens or credentials in scripts
- Invent a new auth mechanism

If auth is expired or missing, re-run `dataverse auth create` (or `pac auth create`), or check `.env`. See the `dv-connect` skill.

### 4. Be honest about gaps — don't hallucinate

Each skill documents a tested sequence — follow it when it fits. The skills are the source of truth for the supported, non-deprecated API. If a call fails with `AttributeError`, the installed SDK version may not have it — check the skill's version note and use the documented alternative.

**The honesty guard:** if you hit a gap the skills don't cover, say so and suggest a workaround. **Do not hallucinate an unsupported path** — do not invent a method, parameter, or endpoint that isn't documented. If unsure, say so.

**Connectivity is not auth.** A `login.microsoftonline.com` token can succeed while the org's data-plane domain is unreachable (restricted-egress hosts like ChatGPT Work Mode). Never report a count or result you didn't get from a real call that returned — verify with `python scripts/auth.py --check`; if it fails, say "unreachable," never a fabricated number. On a constrained host, lead with the SDK, not CLI/MCP. See `dv-connect/references/headless-hosts.md`.

---

## Tool Capabilities — Which Tool for Which Job

Understanding the real limits of each tool prevents hallucinated paths. This is the one piece of context no individual skill owns.

| Tool | Use for | Does NOT support |
| --- | --- | --- |
| **MCP Server** | Data CRUD (create/read/update/delete records, batch up to 25 per call), table create/update/delete + column add (incl. local choice/multiselect + lookup/customer), schema + record inspection via `describe`, metadata search (`search`), data + file-content search (`search_data`, when Dataverse search is enabled), file upload/download | Forms, Views, **global** Option Sets, **N:N** relationships, alternate keys, Solutions (lookup + local choice/multiselect columns **are** supported via `create_table`/`update_table`). **Note:** table creation may timeout but still succeed — always `describe` (e.g. `describe('tables/{name}')`) before retrying. Run queries sequentially (parallel calls timeout). Column names with spaces normalize to underscores (e.g., `"Specialty Area"` → `cr9ac_specialty_area`). **SQL (`read_query`):** supports `JOIN`, `GROUP BY` (COUNT/SUM/AVG/MIN/MAX), `TOP`, `WHERE`, `ORDER BY`; does NOT support `DISTINCT`, `HAVING`, subqueries, `OFFSET`, `UNION`, `CASE`/`IF`, `CAST`/`CONVERT`, CTE, or date functions. For those, use `client.query.sql()` (also allows `DISTINCT`, <5K rows), `$apply`, or a builder->DataFrame with pandas — see `dv-query`. **Bulk:** MCP `create_record`/`update_record`/`delete_record` batch up to 25 records per call; for larger bulk use the SDK `CreateMultiple` — see `dv-data`. |
| **Python SDK (`dv-data`)** | Scripted data writes, especially at volume. Record CRUD, upsert (alternate keys), bulk create/update/upsert (CreateMultiple/UpdateMultiple/UpsertMultiple), CSV import with lookup resolution, file column uploads (chunked >128MB) | global Option Sets, record association (`$ref`), `$apply` aggregation, table/column/relationship creation (use `dv-metadata`), custom action invocation |
| **Python SDK (`dv-query`)** | Bulk reads and analytics. Multi-page record iteration, OData queries (select/filter/expand/orderby), QueryBuilder fluent API, GUID-free display (formatted values), `$expand` to resolve lookups, **aggregation and N:N joins via `client.query.fetchxml()`** (aggregate FetchXML + link-entity), pandas DataFrame handoff (`client.query.builder(...).execute().to_dataframe()`) for exports, Jupyter notebook snippets | OData `$apply` and N:N `$expand` on the **QueryBuilder** path — use `records.list(expand=...)` for N:N, or `fetchxml()` for aggregates (not raw `urllib`) |
| **Dataverse CLI (`dataverse`)** | Headless data plane: `data` CRUD, `associate`/`disassociate` (N:N + `$ref`), `data upload`; `api request`/`invoke` (Web API escape hatch); `api list`/`describe` (Custom API discovery) | Metadata/schema (use SDK — `dv-metadata`), solution ALM (use PAC), forms/views; **blocked on ChatGPT web / Codex cloud** (no .NET runtime) — use the SDK |
| **PAC CLI** | Solution export/import/pack/unpack, ERP X++ SDK install + package scaffold/compile/deploy/DB sync, environment create/list/delete/reset, auth profile management, plugin updates (`pac plugin push` — first-time registration requires Web API), user/role assignment (`pac admin assign-user`), add solution components (`pac solution add-solution-component`) | Data CRUD, Dataverse metadata creation (tables/columns/forms), listing solution components (no `list-components` — query `solutioncomponent` via SDK/CLI); X++ SDK install/compile require Windows |
| **Azure CLI** | App registrations, service principals, credential management | Dataverse-specific operations |
| **GitHub CLI** | Repo management, GitHub secrets, Actions workflow status | Dataverse-specific operations |
| **Raw Web API** (last resort) | Only when **no** managed surface exposes the operation — i.e. not doable via MCP, the Python SDK, the Dataverse CLI, or the `dataverse api` escape hatch. Genuine cases: unbound actions like `PublishXml`, global option sets, and similar edge cases (**not** forms/views — those are SDK record CRUD on `systemform`/`savedquery`). Even then, prefer `dataverse api` (managed auth + skill attribution) over hand-rolled `urllib`. | Functionally nothing (full OData/MetadataService) — but raw `urllib` bypasses managed auth, paging, retry, and skill attribution, so treat it as the path of last resort |

**Routing:** the table shows what each surface does; the *how to choose* principle (soft defaults, not a fixed order) is Hard Rule 2. MCP tools not in your list? Load `dv-connect`.

**Volume guidance:** CLI `dataverse data create/query/count` for one-off commands; MCP for up to ~25 records per call or simple filters; the SDK's `CreateMultiple` for larger bulk writes (chunk large sets starting ~1,000 — see `dv-data`) and `dv-query` for bulk reads; Web API for `$apply` aggregation.

**SDK method cheat-sheet** (anti-hallucination, *not* a preference signal): SDK method names are the least discoverable surface, so agents invent them. This maps common ops to the exact call. Each op is equally reachable via MCP/CLI per Hard Rule 2; see the noted skill for the full pattern.

| Operation | SDK call | Skill |
| --- | --- | --- |
| Create / update / delete records | `client.records.create()` / `.update()` / `.delete()` (pass a list for bulk) | `dv-data` |
| Upsert on an alternate key | `client.records.upsert()` | `dv-data` |
| Query / filter records | `client.records.list(...)` (flat) or `.list_pages(...)` (streaming) | `dv-query` |
| One record by GUID | `client.records.retrieve(table, guid)` (`None` if missing) | `dv-query` |
| Aggregation / server-side joins | `client.query.fetchxml(xml)` (aggregates + link-entity) | `dv-query` |
| Fluent query build (chainable) | `client.query.builder(Table).where(...).execute()` | `dv-query` |
| Limited SQL read | `client.query.sql("SELECT ...")` | `dv-query` |
| Load into pandas | `client.query.builder(table).select(...).execute().to_dataframe()` | `dv-query` |
| Upload to a file column | `client.files.upload(...)` | `dv-data` |
| Create tables / columns / lookups / N:N | `client.tables.create()` / `.add_columns()` / `.create_lookup_field()` / `.create_many_to_many_relationship()` | `dv-metadata` |
| Create an alternate key (enables upsert) | `client.tables.create_alternate_key(...)` | `dv-metadata` |
| Inspect existing schema | `client.tables.list_columns(table)` / `.list_table_relationships(table)` | `dv-metadata` |
| Create publisher / solution | `client.records.create("publisher" / "solution", {...})` | `dv-solution` |

### MCP Availability Check

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

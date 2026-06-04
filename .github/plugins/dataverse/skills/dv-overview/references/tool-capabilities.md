# Tool Capabilities — Which Tool for Which Job

Understanding the real limits of each tool prevents hallucinated paths. This is the one piece of context no individual skill owns.

| Tool | Use for | Does NOT support |
| --- | --- | --- |
| **MCP Server** | Data CRUD (create/read/update/delete records), table create/update/delete/list/describe, column add via `update_table`, keyword search, single-record fetch | Forms, Views, Relationships, Option Sets, Solutions. **Note:** table creation may timeout but still succeed — always `describe_table` before retrying. Run queries sequentially (parallel calls timeout). Column names with spaces normalize to underscores (e.g., `"Specialty Area"` → `cr9ac_specialty_area`). **SQL limitations:** The `read_query` tool uses Dataverse SQL, which does NOT support: `DISTINCT`, `HAVING`, subqueries, `OFFSET`, `UNION`, `CASE`/`IF`, `CAST`/`CONVERT`, or date functions. For analytical queries that need these (e.g., finding duplicates, unmatched records, filtered aggregates), use `$apply` (single-table aggregation) or `client.dataframe.get()` with pandas (cross-table) — see `dv-query`. **Bulk operations:** MCP `create_record` creates one record at a time. For 10+ records, use the Python SDK `CreateMultiple` instead — see `dv-data`. |
| **Python SDK (`dv-data`)** | **Preferred for all scripted data writes.** Record CRUD, upsert (alternate keys), bulk create/update/upsert (CreateMultiple/UpdateMultiple/UpsertMultiple), CSV import with lookup resolution, file column uploads (chunked >128MB) | Forms, Views, global Option Sets, record association (`$ref`), `$apply` aggregation, N:N `$expand`, table/column/relationship creation (use `dv-metadata`), custom action invocation |
| **Python SDK (`dv-query`)** | **Preferred for bulk reads and analytics.** Multi-page record iteration, OData queries (select/filter/expand/orderby), QueryBuilder fluent API (b8+), GUID-free display (formatted values), `$expand` to resolve lookups, pandas DataFrame handoff (`client.dataframe.get()`) for cross-table joins and exports, Jupyter notebook snippets | `$apply` aggregation (use Web API), N:N `$expand` (use Web API) |
| **Web API** | Everything — forms, views, relationships, option sets, columns, table definitions, unbound actions, `$ref` association | Nothing (full MetadataService + OData access) |
| **PAC CLI** | Solution export/import/pack/unpack, environment create/list/delete/reset, auth profile management, plugin updates (`pac plugin push` — first-time registration requires Web API), user/role assignment (`pac admin assign-user`), solution component management | Data CRUD, metadata creation (tables/columns/forms) |
| **Azure CLI** | App registrations, service principals, credential management | Dataverse-specific operations |
| **GitHub CLI** | Repo management, GitHub secrets, Actions workflow status | Dataverse-specific operations |

**Tool priority (always follow this order):** MCP for simple reads/queries (small result set, no paging) and ≤10 record writes → Python SDK for bulk reads, scripted writes, bulk operations, and analysis → Web API for operations the SDK doesn't cover (forms, views, option sets, `$apply`, N:N `$expand`) → PAC CLI for solution lifecycle. Schema creation (tables/columns/relationships) → SDK via `dv-metadata`. MCP tools not in your tool list? → Load `dv-connect` to set them up (see below).

**Volume guidance — writes:** MCP `create_record` for 1-10 records. For 10+ records, use `dv-data` (`client.records.create(table, list_of_dicts)`) — it uses `CreateMultiple` internally. **Note:** the SDK does not chunk automatically; for large datasets, chunk in your script starting at 1,000 and adapt up or down based on success (see `dv-data` for the adaptive pattern).

**Volume guidance — reads:** MCP `read_query` for simple filters and small result sets (no paging needed). For bulk reads (multi-page iteration, all-records loads, DataFrame handoff), use `dv-query` SDK — it streams pages automatically and avoids MCP SQL limitations. For aggregation queries (`$apply`), use the Web API directly (see `dv-query`).

Note: The Python SDK is in **preview** — breaking changes possible.

## MCP Availability Check

If the user's request involves MCP — either explicitly ("connect via MCP", "use MCP", "query via MCP") or implicitly (conversational data queries where MCP would be the natural tool) — check whether Dataverse MCP tools are available in your current tool list (e.g., `list_tables`, `describe_table`, `read_query`, `create_record`).

**If MCP tools are NOT available and the user explicitly asked for MCP** (e.g., "use MCP to query", "why isn't MCP working"):
1. **Do NOT silently fall back** to the Python SDK or Web API
2. Tell the user: "Dataverse MCP tools aren't configured in this session yet."
3. Load the `dv-connect` skill to set up the MCP server
4. After MCP is configured, **stop here** — the session must be restarted for MCP tools to appear. Remind them: "Use `claude --continue` to resume without losing context." Do not proceed with SDK. Wait for the user to restart.

**If MCP tools are NOT available and the user asked a data question without explicitly requesting MCP** (e.g., "how many accounts with 'jeff'?", "show me open tickets"):
1. This is a SDK fallback case — use the Python SDK to answer the question. Do not block the user.
2. After answering, offer: "MCP would handle this conversationally — want me to set it up?"

The distinction matters: explicit MCP request → block and set up MCP. Implicit/conversational question → answer with SDK, offer MCP setup.

**If MCP tools ARE available**, prefer MCP for simple reads/queries/small CRUD. Use the SDK only when a script is needed.

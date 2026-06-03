# Tool Routing — Full Capabilities and MCP Availability

## Tool Capabilities — Which Tool for Which Job

Understanding the real limits of each tool prevents hallucinated paths.

| Tool | Use for | Does NOT support |
| --- | --- | --- |
| **MCP Server** | Data CRUD (create/read/update/delete records), table create/update/delete/list/describe, column add via `update_table`, keyword search, single-record fetch | Forms, Views, Relationships, Option Sets, Solutions. **Note:** table creation may timeout but still succeed — always `describe_table` before retrying. Run queries sequentially (parallel calls timeout). Column names with spaces normalize to underscores (e.g., `"Specialty Area"` -> `cr9ac_specialty_area`). **SQL limitations:** The `read_query` tool uses Dataverse SQL, which does NOT support: `DISTINCT`, `HAVING`, subqueries, `OFFSET`, `UNION`, `CASE`/`IF`, `CAST`/`CONVERT`, or date functions. For analytical queries that need these (e.g., finding duplicates, unmatched records, filtered aggregates), use `$apply` (single-table aggregation) or `client.dataframe.get()` with pandas (cross-table) — see `dv-query`. **Bulk operations:** MCP `create_record` creates one record at a time. For 10+ records, use the Python SDK `CreateMultiple` instead — see `dv-data`. |
| **Dataverse CLI** | MCP-down fallback for single-record CRUD (`data create/get/update/delete`), N:N associate/disassociate (`data associate/disassociate`), uncapped paginated reads (`data query --all`), record count with filter (`data count`), raw authenticated HTTP (`api request`), custom API discovery/invocation (`api list/describe/invoke`) | Bulk/batch operations (no `CreateMultiple`), metadata authoring (no table/column/relationship creation), DataFrames/pandas, file uploads, forms, views, solutions, transactional changesets |
| **Python SDK (`dv-data`)** | **Preferred for all scripted data writes.** Record CRUD, upsert (alternate keys), bulk create/update/upsert (CreateMultiple/UpdateMultiple/UpsertMultiple), CSV import with lookup resolution, file column uploads (chunked >128MB) | Forms, Views, global Option Sets, `$apply` aggregation, N:N `$expand`, table/column/relationship creation (use `dv-metadata`), custom action invocation |
| **Python SDK (`dv-query`)** | **Preferred for bulk reads and analytics.** Multi-page record iteration, OData queries (select/filter/expand/orderby), QueryBuilder fluent API (b8+), GUID-free display (formatted values), `$expand` to resolve lookups, pandas DataFrame handoff (`client.dataframe.get()`) for cross-table joins and exports, Jupyter notebook snippets | `$apply` aggregation (use Web API), N:N `$expand` (use Web API) |
| **Web API** | Everything — forms, views, relationships, option sets, columns, table definitions, unbound actions, `$ref` association | Nothing (full MetadataService + OData access) |
| **PAC CLI** | Solution export/import/pack/unpack, environment create/list/delete/reset, auth profile management, plugin updates (`pac plugin push` — first-time registration requires Web API), user/role assignment (`pac admin assign-user`), solution component management | Data CRUD, metadata creation (tables/columns/forms) |
| **Azure CLI** | App registrations, service principals, credential management | Dataverse-specific operations |
| **GitHub CLI** | Repo management, GitHub secrets, Actions workflow status | Dataverse-specific operations |

**Volume guidance — writes:** MCP `create_record` for 1-10 records. MCP unavailable? CLI `data create` for 1-10 records. For 10+ records, use `dv-data` (`client.records.create(table, list_of_dicts)`) — it uses `CreateMultiple` internally. **Note:** the SDK does not chunk automatically; for large datasets, chunk in your script starting at 1,000 and adapt up or down based on success (see `dv-data` for the adaptive pattern).

**Volume guidance — reads:** MCP `read_query` for simple filters and small result sets (no paging needed). MCP unavailable? CLI `data query` for simple reads, `data query --all` for paginated reads up to `--max-records` cap. For bulk reads (DataFrame handoff, cross-table joins), use `dv-query` SDK — it streams pages automatically and avoids MCP SQL limitations. For aggregation queries (`$apply`), use the Web API directly (see `dv-query`).

Note: The Python SDK is in **preview** — breaking changes possible.

---

## MCP Availability Check

If the user's request involves MCP — either explicitly ("connect via MCP", "use MCP", "query via MCP") or implicitly (conversational data queries where MCP would be the natural tool) — check whether Dataverse MCP tools are available in your current tool list (e.g., `list_tables`, `describe_table`, `read_query`, `create_record`).

**If MCP tools are NOT available and the user explicitly asked for MCP** (e.g., "use MCP to query", "why isn't MCP working"):
1. **Do NOT silently fall back** to the CLI or Python SDK
2. Tell the user: "Dataverse MCP tools aren't configured in this session yet."
3. Load the `dv-connect` skill to set up the MCP server
4. After MCP is configured, **stop here** — the session must be restarted for MCP tools to appear. Remind them: "Use `claude --continue` to resume without losing context." Do not proceed with CLI or SDK. Wait for the user to restart.

**If MCP tools are NOT available and the user asked a data question without explicitly requesting MCP** (e.g., "how many accounts with 'jeff'?", "show me open tickets"):
1. For simple CRUD or reads — use the Dataverse CLI as the first fallback (see `dv-data` and `dv-query` for CLI commands).
2. For bulk operations, DataFrames, or analytics — use the Python SDK.
3. After answering, offer: "MCP would handle this conversationally — want me to set it up?"

**If MCP tools ARE available**, prefer MCP for simple reads/queries/small CRUD. Use the CLI only for operations MCP cannot handle (N:N associations, uncapped reads). Use the SDK only when a script is needed.

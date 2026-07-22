---
name: dv-query
description: Bulk reads, multi-page iteration, and analytics over Dataverse data. Use when the user wants to read, list, filter, aggregate, group, join, or analyze records — including pandas DataFrame workflows and notebook exploration.
---

# Skill: Query — Read and Analyze Dataverse Records

> **This skill uses Python exclusively.** Do not use Node.js, JavaScript, or any other language for Dataverse scripting. See the overview skill's Hard Rules.

## Reads: prefer a managed surface, choose by shape

Pick **MCP or the SDK by the shape of the read** — both handle auth, paging, and retry (see the routing table below and the overview's **Tool Capabilities** / Hard Rule 2). MCP fits small, interactive reads; the SDK fits bulk iteration and analytics. For `$apply` aggregation and N:N `$expand`, prefer `client.query.fetchxml()` (aggregates + link-entity) or the managed `dataverse api` escape hatch; reach for hand-rolled `urllib`/`get_token()` **only** to stay in-process inside a tight Python loop (e.g. paging thousands of rows with client-side processing — see web-api-advanced.md).

### Dataverse CLI gotchas (custom tables + Windows)

When you drive the `dataverse` CLI directly (headless reads/CRUD), two empirical traps:

- **Custom-table SQL pluralization.** `dataverse data query` in SQL mode auto-pluralizes the table name, and irregular plurals resolve wrong: `FROM im_category` looks up entity set `im_categorys` and returns a **404** that reads like "table missing." It is not — switch to OData mode with the explicit entity set: `dataverse data query --table im_categories --select im_name`. Discover the real `EntitySetName` from `EntityDefinitions` when unsure; never conclude the table doesn't exist from this 404.
- **Windows `.cmd` URL encoding.** On Windows the CLI is a `.cmd` wrapper, so `cmd.exe` parses `--path` query strings. URL-encode `$`->`%24` and every `&` — an unencoded `&` can make the wrapper exit nonzero *even when the API returned valid JSON*, so don't treat that nonzero exit as an API failure. (This is why the `dataverse api request` examples in other skills already encode `%24`.)

## How to Answer Data Questions

When the user asks a question about their data, pick the approach by **what they're asking**, not by which API you know:

| User asks... | Approach | Why |
|---|---|---|
| "show me open tickets" / simple filter | **MCP** `read_query` (if available) or `client.records.list(table, filter=...)` | Small result, no aggregation |
| "how many X" / simple count | **MCP** `read_query`, or `client.query.sql("SELECT COUNT(*) AS n FROM <table> WHERE ...")` | Server-side count (no row download) |
| Single-table aggregation (most/sum/avg/top-N) | **`$apply`** (raw) or **`client.query.sql()`** GROUP BY | Both run server-side, return only grouped results |
| Cross-table aggregation | **`client.query.sql("...INNER JOIN...GROUP BY...")`** or **`client.query.fetchxml(...)`** (server-side); else builder->DataFrame + `pd.merge()` | `sql()` supports INNER/LEFT JOIN + GROUP BY; pandas merge for shapes SQL can't express |
| "show me X with related Y" / resolve lookups | `client.records.list(table, expand=...)` or **QueryBuilder** | Lookup resolution |
| "export this data" / bulk extract | **`client.query.builder(t).select(...).execute().to_dataframe()`** | Direct to DataFrame → CSV |
| "load into notebook" / interactive analysis | **`client.query.builder(t).select(...).execute().to_dataframe()`** | pandas native |
| "find duplicates" / complex filter | `client.records.list(table, filter=...)` or **QueryBuilder** | SDK handles pagination |
| Simple filtered read (<5K rows) | **`client.query.sql()`** | Lightweight SQL SELECT with WHERE, ORDER BY, TOP |

**Key principle:** Let the server do the work. For single-table aggregation, use `$apply` (raw) or `client.query.sql()` GROUP BY — both run server-side and return only grouped results. For cross-table questions, prefer a server-side `sql()` JOIN (INNER/LEFT) or `fetchxml()` link-entity; when SQL can't express it, pull each table via `client.query.builder(t).select(...).execute().to_dataframe()` and `pd.merge()` — the merge is sub-second; the bottleneck is network transfer, which `select` minimizes.

**Always query the live Dataverse environment.** Do not query local copies, cached files, or source databases when the user expects results from Dataverse. The data in Dataverse is the source of truth.

---

## SQL Queries — `client.query.sql()`

`client.query.sql()` uses the Dataverse Web API `?sql=` parameter — a **T-SQL subset**. It **supports** `SELECT` / `SELECT DISTINCT` / `SELECT TOP N` (0-5000), `INNER JOIN` / `LEFT JOIN`, `WHERE`, `GROUP BY`, `ORDER BY`, `OFFSET`/`FETCH`, and `COUNT/SUM/AVG/MIN/MAX`. It does **NOT** support `SELECT *`, subqueries, CTEs, `HAVING`, `UNION`, `RIGHT`/`FULL`/`CROSS JOIN`, `CASE`, or string/date/math functions. Results are capped at ~5,000 rows.

**When to use:** Fast filtered reads on tables with <5K rows. For these, it's significantly faster (~2-6s) than page iteration or DataFrames because it's a single HTTP call.

```python
# Fast filtered read on small tables (<5K rows)
results = client.query.sql(
    "SELECT TOP 100 name, estimatedvalue "
    "FROM opportunity "
    "WHERE statecode = 0 "
    "ORDER BY estimatedvalue DESC"
)
for r in results:
    print(f"{r['name']}: ${r.get('estimatedvalue', 0):,.0f}")
```

**Do NOT use for:** Tables >5K rows (results silently truncated), `SELECT *`, subqueries/CTEs, `HAVING`, `UNION`, `RIGHT`/`FULL`/`CROSS JOIN`, or functions. `INNER`/`LEFT JOIN` and `GROUP BY` **are** supported — use them for server-side joins/aggregation on <5K-row results; for larger or unsupported shapes use `fetchxml()` or `$apply`.

## FetchXML — server-side joins and aggregates

For SQL-JOIN scenarios or aggregates the OData builder cannot express, use FetchXML. `client.query.fetchxml(xml)` returns an inert query object — no HTTP is made until you call `.execute()` (eager, all pages) or `.execute_pages()` (lazy, one page at a time). Both return `QueryResult` pages with `.to_dataframe()`.

```python
query = client.query.fetchxml("""
  <fetch top="50">
    <entity name="account">
      <attribute name="name" />
      <link-entity name="contact" from="parentcustomerid" to="accountid" alias="c" link-type="inner">
        <attribute name="fullname" />
      </link-entity>
    </entity>
  </fetch>
""")

result = query.execute()          # collect all pages
df = result.to_dataframe()

# Or stream one page at a time for large results:
for page in query.execute_pages():
    print(page.to_dataframe().shape)
```

## Discover queryable columns — `client.query.sql_columns()`

Before writing a SQL or `$select` read, list the columns the SQL endpoint can actually query — virtual and computed lookup-display columns are excluded. Each entry has `name`, `type`, `is_pk`, `is_name`, and `label`.

```python
for c in client.query.sql_columns("account"):
    print(f"{c['name']:30s} {c['type']:20s} PK={c['is_pk']}")
```

For deeper schema inspection — full column metadata and table relationships — use `dv-metadata`
(`client.tables.list_columns()`, `client.tables.list_relationships()`,
`client.tables.list_table_relationships()`).

## Skill boundaries

| Need | Use instead |
|---|---|
| Create, update, delete records | **dv-data** |
| Create tables, columns, relationships | **dv-metadata** |
| Export or deploy solutions | **dv-solution** |

---

## Setup

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

# get_client sets a plugin attribution context on the User-Agent header.
# Do not modify the context value — it is a closed schema for server-side
# telemetry (app/skill/agent). Never include secrets or PII.
client = get_client("dv-query")
```

`get_client(skill)` handles auth, environment URL, and plugin attribution (User-Agent tagging). See `scripts/auth.py`. For scripts that run to completion, wrap the returned client in a `with` statement for automatic connection cleanup.

---

## Field Name Casing Rule

Getting this wrong causes 400 errors.

| Property type | Convention | Example | When used |
|---|---|---|---|
| **Structural** (columns) | LogicalName — always lowercase | `new_name`, `new_priority` | `$select`, `$filter`, `$orderby` |
| **Navigation** (lookups) | Navigation Property Name — case-sensitive, matches `$metadata` | `new_AccountId` | `$expand` |

- System table navigation properties (e.g., `parentaccountid`, `ownerid`): lowercase
- Custom lookup navigation properties: case-sensitive, match `$metadata` SchemaName (e.g., `new_AccountId`)

---

## Query Records

`client.records.list()` is the primary read method on the GA SDK. It collects all pages and returns a flat `QueryResult` you iterate directly (records, not pages). For very large result sets, `client.records.list_pages()` streams one `QueryResult` per HTTP page. **Always use `select=` to limit columns.**

```python
# list() -- flat QueryResult, iterate records directly
result = client.records.list(
    "new_ticket",
    select=["new_name", "new_priority", "new_status"],
    filter="new_status eq 100000000",
    orderby=["new_name asc"],
    top=50,
)
for r in result:
    print(r["new_name"], r["new_priority"])

print(f"{len(result)} tickets")   # QueryResult supports len(), indexing, .first(), .to_dataframe()
```

For large tables where you do not want every row in memory at once, stream pages:

```python
for page in client.records.list_pages("new_ticket", select=["new_name"], page_size=200):
    for r in page:          # each page is a QueryResult
        print(r["new_name"])
```

Each record is a `Record` object that supports dict-like access: `r["column"]`, `r.get("column")`, `r.keys()`. Do not use `r.data.get()` -- use `r.get()` directly.

> **Migrating from `records.get()`:** `records.get()` is deprecated on the GA SDK. Replace `for page in client.records.get(...): for r in page:` with `for r in client.records.list(...):` (flat), or keep the page loop using `list_pages(...)`. Replace a by-GUID `records.get(table, guid)` with `records.retrieve(table, guid)` (returns `None` if not found).

---

## Fetch a Single Record by ID

`client.records.retrieve()` returns the record, or `None` if no row has that GUID (no exception on 404).

```python
record = client.records.retrieve("new_ticket", "<record-guid>",
    select=["new_name", "new_priority", "new_status"])
if record is not None:
    print(record["new_name"])
else:
    print("Ticket not found")
```

---

## $select with Lookup Columns (GUID-free display)

To show display names instead of GUIDs, request the formatted value annotation via `include_annotations`:

```python
for r in client.records.list("opportunity",
    select=["name", "estimatedvalue", "_parentaccountid_value"],
    include_annotations="OData.Community.Display.V1.FormattedValue",
):
    account_name = r.get("_parentaccountid_value@OData.Community.Display.V1.FormattedValue")
    print(f"{r['name']} — {account_name}")
```

**You MUST pass `include_annotations`** — without it, the `Prefer: odata.include-annotations` header is not sent and formatted values are not in the response. Use `"*"` for all annotations or the specific annotation name above.

Formatted values are available for lookup, choice, status, and owner fields.

---

## $expand — Resolve Lookup to Full Related Record

```python
for r in client.records.list("opportunity",
    select=["name", "estimatedvalue"],
    expand=["parentaccountid($select=name)"],   # nested $select avoids fetching all account columns
):
    account = r.get("parentaccountid") or {}
    print(f"{r['name']} — {account.get('name', 'Unknown')}")
```

Always use nested `$select` inside `$expand` — without it, Dataverse returns every column on the related entity, which wastes bandwidth and memory.

### $expand with multiple custom lookups

```python
for r in client.records.list(
    "new_ticket",
    select=["new_name", "new_priority", "new_status"],
    expand=["new_CustomerId($select=new_name)", "new_AgentId($select=new_name)"],  # nested $select + case-sensitive nav props
):
    customer = r.get("new_CustomerId") or {}
    agent    = r.get("new_AgentId") or {}
    print(f"{r['new_name']} | {customer.get('new_name','')} | {agent.get('new_name','')}")
```

> `expand` uses the Navigation Property Name (`new_CustomerId`), not the lowercase logical name (`new_customerid`). Using lowercase causes a 400 error.

---

## Advanced query patterns (raw Web API)

`$apply` aggregation and N:N `$expand` on the OData path are raw-only. Note the SDK **does** cover most aggregation/joins — `client.query.sql()` (INNER/LEFT JOIN, GROUP BY, COUNT/SUM/AVG) and `client.query.fetchxml()` (aggregate + link-entity). Reach for raw Web API only for the `$apply` transform and N:N `$expand`. See [`references/web-api-advanced.md`](references/web-api-advanced.md) for full code samples.

**Quick reference:**
- **`$expand` on N:N relationships:** `GET /<entitySet>?$expand=<n:n_nav>($select=...)` — single page only; follow `@odata.nextLink` for >5,000 results.
- **`$apply` for aggregations:** runs server-side, returns grouped results in one call. Patterns: `groupby((col),aggregate(metric with sum as total))`, `aggregate($count as count)`, `aggregate(amount with average as avg)`. 50K source-record limit.
- **Cross-table aggregation:** `$apply` only works within one entity set. Prefer `client.query.sql()` (INNER/LEFT JOIN + GROUP BY) or `fetchxml()` link-entity; else pull each table via `client.query.builder(t).select(...).execute().to_dataframe()` → `pd.merge()` → `groupby()`. Always pass `select`; without it transfers 10-20x more data.

## QueryBuilder — Fluent Query API

Chainable builder for complex queries that would be awkward as a single OData URL or FetchXML string. Full reference and examples in [`references/querybuilder.md`](references/querybuilder.md).

## Jupyter Notebook Setup

For interactive querying in notebooks (auth + DataverseClient + DataFrame display), see [`references/jupyter-setup.md`](references/jupyter-setup.md).

## Common Query Errors

| Status | Cause | Fix |
|---|---|---|
| 400 | Wrong field casing in `$select`/`$filter` (must be lowercase LogicalName) or `$expand` (must be case-sensitive Navigation Property Name) | Verify names via `EntityDefinitions(LogicalName='...')/Attributes` |
| 400 | Unsupported SQL — MCP `read_query` rejects DISTINCT/HAVING/subqueries/OFFSET/UNION/CAST/CONVERT/CASE/date-functions (but **allows** JOIN + GROUP BY); `client.query.sql()` rejects `SELECT *`/subqueries/CTE/HAVING/UNION/RIGHT/FULL/CROSS JOIN/functions (but **allows** INNER/LEFT JOIN, GROUP BY, DISTINCT) | Use `fetchxml()`/`$apply` for shapes `sql()` can't express, or pandas for cross-table |
| 404 | Table logical name not found | Check spelling — use `client.tables.get("<name>")` to verify |
| 429 | Rate limited | SDK retries automatically; reduce page size or add delays between pages |

For `HttpError` handling in SDK scripts, see the error handling pattern in **dv-data**.

---

## Windows Scripting Notes

- **ASCII only** in `.py` files — curly quotes and em dashes cause `SyntaxError` on Windows.
- **No `python -c` for multiline code** — write a `.py` file instead.
- **Generate GUIDs in scripts**: `str(uuid.uuid4())`, not shell backtick substitution.

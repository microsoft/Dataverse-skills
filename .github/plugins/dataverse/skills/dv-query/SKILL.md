---
name: dv-query
description: Bulk reads, multi-page iteration, and analytics over Dataverse data via the Python SDK and Web API. Use when the user wants to read, list, filter, aggregate, group, join, or analyze records — including pandas DataFrame workflows and notebook exploration.
---

# Skill: Query — Read and Analyze Dataverse Records

> **This skill uses Python exclusively.** Do not use Node.js, JavaScript, or any other language for Dataverse scripting. See the overview skill's Hard Rules.

## SDK-First Rule for Reads

**All reads use the SDK — not `urllib`, `requests`, or raw HTTP.** This is the same rule as dv-data's SDK-First Rule, applied to reads. If you find yourself writing `urllib.request` or `get_token()` for a query, STOP — the SDK handles it. The only exceptions are `$apply` aggregation and N:N `$expand`, documented below.

## How to Answer Data Questions

When the user asks a question about their data, pick the approach by **what they're asking**, not by which API you know:

| User asks... | Approach | Why |
|---|---|---|
| "show me open tickets" / simple filter | **MCP** `read_query` (if available) or `client.records.get()` with `$filter` | Small result, no aggregation |
| "how many X" / simple count | **MCP** `read_query` or `client.records.get()` with `count=True` | Single number |
| Single-table aggregation (most/sum/avg/top-N) | **`$apply`** server-side aggregation (raw Web API) | One HTTP call, returns only grouped results |
| Cross-table aggregation | **`client.dataframe.get()`** with minimal `$select` + `pd.merge()` | Server can't join; pandas merge is fast with minimal columns |
| "show me X with related Y" / resolve lookups | `client.records.get()` with `$expand` or **QueryBuilder** (b8+) | Lookup resolution |
| "export this data" / bulk extract | **`client.dataframe.get()`** with `select=` | Direct to DataFrame → CSV |
| "load into notebook" / interactive analysis | **`client.dataframe.get()`** or **QueryBuilder** `.to_dataframe()` (b8+) | pandas native |
| "find duplicates" / complex filter | `client.records.get()` with `$filter` or **QueryBuilder** (b8+) | SDK handles pagination |
| Simple filtered read (<5K rows) | **`client.query.sql()`** | Lightweight SQL SELECT with WHERE, ORDER BY, TOP |

**Key principle:** Let the server do the work. For single-table aggregation, use `$apply` — it runs server-side and returns only grouped results. For cross-table questions, use `client.dataframe.get()` with minimal `$select` on each table, then `pd.merge()` — the merge itself is sub-second; the bottleneck is network transfer, which `$select` minimizes.

**Always query the live Dataverse environment.** Do not query local copies, cached files, or source databases when the user expects results from Dataverse. The data in Dataverse is the source of truth.

---

## SQL Queries — `client.query.sql()`

`client.query.sql()` uses the Dataverse Web API `?sql=` parameter — a **limited SQL subset** (same limitations as MCP `read_query`). It does NOT support GROUP BY, JOINs, HAVING, DISTINCT, or subqueries. Results are capped at ~5,000 rows.

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

**Do NOT use for:** Tables >5K rows (results silently truncated), aggregation (no GROUP BY), or cross-table queries (no JOINs). Use `$apply` for single-table aggregation and `client.dataframe.get()` + `pd.merge()` for cross-table.

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
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient

load_env()
client = DataverseClient(
    base_url=os.environ["DATAVERSE_URL"],
    credential=get_credential(),
)
```

For scripts that run to completion: wrap in `with DataverseClient(...) as client:` for automatic connection cleanup (recommended since b6). For notebooks and interactive sessions, the explicit client above is simpler.

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

## Query Records (multi-page)

`client.records.get()` is the primary read method — works on all SDK versions (b6+). It returns a page iterator for multi-record queries and a single Record for by-GUID fetch. **Always use `select=` to limit columns.**

```python
for page in client.records.get(
    "new_ticket",
    select=["new_name", "new_priority", "new_status"],
    filter="new_status eq 100000000",
    orderby=["new_name asc"],
    top=50,
):
    for r in page:
        print(r["new_name"], r["new_priority"])
```

`client.records.get()` returns a page iterator — always iterate pages and then records within each page. Each record is a `Record` object that supports dict-like access: `r["column"]`, `r.get("column")`, `r.keys()`. Do not use `r.data.get()` — use `r.get()` directly.

---

## Fetch a Single Record by ID

```python
record = client.records.get("new_ticket", "<record-guid>",
    select=["new_name", "new_priority", "new_status"])
print(record["new_name"])
```

---

## $select with Lookup Columns (GUID-free display)

To show display names instead of GUIDs, request the formatted value annotation via `include_annotations`:

```python
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "_parentaccountid_value"],
    include_annotations="OData.Community.Display.V1.FormattedValue",
):
    for r in page:
        account_name = r.get("_parentaccountid_value@OData.Community.Display.V1.FormattedValue")
        print(f"{r['name']} — {account_name}")
```

**You MUST pass `include_annotations`** — without it, the `Prefer: odata.include-annotations` header is not sent and formatted values are not in the response. Use `"*"` for all annotations or the specific annotation name above.

Formatted values are available for lookup, choice, status, and owner fields.

---

## $expand — Resolve Lookup to Full Related Record

```python
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue"],
    expand=["parentaccountid($select=name)"],   # nested $select avoids fetching all account columns
):
    for r in page:
        account = r.get("parentaccountid") or {}
        print(f"{r['name']} — {account.get('name', 'Unknown')}")
```

Always use nested `$select` inside `$expand` — without it, Dataverse returns every column on the related entity, which wastes bandwidth and memory.

### $expand with multiple custom lookups

```python
for page in client.records.get(
    "new_ticket",
    select=["new_name", "new_priority", "new_status"],
    expand=["new_CustomerId($select=new_name)", "new_AgentId($select=new_name)"],  # nested $select + case-sensitive nav props
):
    for r in page:
        customer = r.get("new_CustomerId") or {}
        agent    = r.get("new_AgentId") or {}
        print(f"{r['new_name']} | {customer.get('new_name','')} | {agent.get('new_name','')}")
```

> `expand` uses the Navigation Property Name (`new_CustomerId`), not the lowercase logical name (`new_customerid`). Using lowercase causes a 400 error.

---

## Advanced query patterns (Web API only)

For aggregations and many-to-many expansion, the SDK doesn't have direct support — use raw Web API. See [`references/web-api-advanced.md`](references/web-api-advanced.md) for full code samples.

**Quick reference:**
- **`$expand` on N:N relationships:** `GET /<entitySet>?$expand=<n:n_nav>($select=...)` — single page only; follow `@odata.nextLink` for >5,000 results.
- **`$apply` for aggregations:** runs server-side, returns grouped results in one call. Patterns: `groupby((col),aggregate(metric with sum as total))`, `aggregate($count as count)`, `aggregate(amount with average as avg)`. 50K source-record limit.
- **Cross-table aggregation:** `$apply` only works within one entity set. Use `client.dataframe.get(entity, select=[...])` per table → `pd.merge()` → `groupby()`. Always pass `select=`; without it transfers 10-20× more data.

## QueryBuilder — Fluent Query API (SDK b8+)

Available in `PowerPlatform-Dataverse-Client` b8+. Chainable builder for complex queries that would be awkward as a single OData URL or FetchXML string. Full reference and examples in [`references/querybuilder.md`](references/querybuilder.md).

## Jupyter Notebook Setup

For interactive querying in notebooks (auth + DataverseClient + DataFrame display), see [`references/jupyter-setup.md`](references/jupyter-setup.md).

## Common Query Errors

| Status | Cause | Fix |
|---|---|---|
| 400 | Wrong field casing in `$select`/`$filter` (must be lowercase LogicalName) or `$expand` (must be case-sensitive Navigation Property Name) | Verify names via `EntityDefinitions(LogicalName='...')/Attributes` |
| 400 | Unsupported SQL in MCP `read_query` or `client.query.sql()` (DISTINCT, HAVING, subqueries, OFFSET, JOINs, GROUP BY) | Use `$apply` for single-table aggregation, or `client.dataframe.get()` + pandas for cross-table |
| 404 | Table logical name not found | Check spelling — use `client.tables.get("<name>")` to verify |
| 429 | Rate limited | SDK retries automatically; reduce page size or add delays between pages |

For `HttpError` handling in SDK scripts, see the error handling pattern in **dv-data**.

---

## Windows Scripting Notes

- **ASCII only** in `.py` files — curly quotes and em dashes cause `SyntaxError` on Windows.
- **No `python -c` for multiline code** — write a `.py` file instead.
- **Generate GUIDs in scripts**: `str(uuid.uuid4())`, not shell backtick substitution.

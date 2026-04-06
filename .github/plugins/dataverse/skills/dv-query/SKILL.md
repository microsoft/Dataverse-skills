---
name: dv-query
description: >
  Bulk reads, multi-page iteration, and analytics using the Python SDK and Web API.
  Use when: "query records", "read data", "bulk read", "all records", "iterate records",
  "expand lookup", "cross-table query", "join tables",
  "aggregate", "group by", "average", "sum", "count with HAVING", "$apply",
  "N:N expand", "notebook", "pandas", "DataFrame", "analyze data", "load into dataframe".
  Do not use when: MCP is sufficient (simple filter, single-record read, small result set — use MCP first),
  creating or modifying records (use dv-data),
  creating tables or columns (use dv-metadata).
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

## $expand on N:N Relationships (Web API — SDK does not support)

> **Note:** These raw Web API examples fetch a single page only. If results exceed one page (~5000 records), you must follow `@odata.nextLink` in a loop to get all records. For most N:N and aggregation queries, a single page is sufficient.

```python
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # get_token() is correct here — SDK cannot do this

load_env()
env = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

# Tickets with their linked KB articles (N:N)
url = (f"{env}/api/data/v9.2/new_tickets"
       f"?$select=new_name"
       f"&$expand=new_ticket_kbarticle($select=new_title)")
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())
    for ticket in data["value"]:
        articles = [a["new_title"] for a in ticket.get("new_ticket_kbarticle", [])]
        print(f"{ticket['new_name']}: {', '.join(articles)}")
```

---

## $apply Aggregation (Web API — SDK does not support)

**Use `$apply` for any single-table aggregation** — "which X has the most Y", "total by group", "top N", "average per category". This runs server-side and returns only the grouped results. One HTTP call, no client-side processing. Limit: 50,000 source records per aggregation.

**Common $apply patterns:**

| User question | $apply expression |
|---|---|
| "total sales by status" | `groupby((statuscode),aggregate(amount with sum as total))` |
| "which account has the most revenue" | `groupby((_parentaccountid_value),aggregate(estimatedvalue with sum as total))` then sort client-side |
| "how many records per category" | `groupby((category),aggregate($count as count))` |
| "average deal size by region" | `groupby((region),aggregate(amount with average as avg))` |

```python
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # get_token() is correct here — SDK does not support $apply

load_env()
env = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

def apply_query(entity_set, apply_expr):
    """Run a $apply aggregation query. Returns list of result dicts."""
    url = f"{env}/api/data/v9.2/{entity_set}?$apply={apply_expr}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read()).get("value", [])

# Example 1: Count and sum by status
results = apply_query("opportunities",
    "groupby((statuscode),aggregate($count as count,estimatedvalue with sum as total_value))")
for row in results:
    print(f"Status {row['statuscode']}: {row['count']} records, ${row['total_value']:,.0f}")

# Example 2: Top accounts by total deal value
results = apply_query("opportunities",
    "groupby((_parentaccountid_value),aggregate(estimatedvalue with sum as total))")
top = sorted(results, key=lambda r: r.get("total", 0), reverse=True)[:10]
for r in top:
    print(f"Account {r['_parentaccountid_value']}: ${r['total']:,.0f}")
```

**When `$apply` won't work** (cross-table questions, complex transforms):

`$apply` only works within a single entity set. For cross-table aggregation, use `client.dataframe.get()` with minimal `$select` on each table, then `pd.merge()`. The merge itself is sub-second; the bottleneck is network transfer, which `$select` minimizes:

```python
import pandas as pd

# Only the columns needed — always pass select= on large tables
df_a = client.dataframe.get("prefix_tablea",
    select=["prefix_keycolumn", "prefix_metric"])
df_b = client.dataframe.get("prefix_tableb",
    select=["prefix_keycolumn", "prefix_dimension"])

merged = pd.merge(df_a, df_b, on="prefix_keycolumn")
top = merged.groupby("prefix_dimension")["prefix_metric"].sum().nlargest(10)
print(top)
```

**Performance rules for client-side processing:**
- Always use `$select` — fetching all columns on 100K rows transfers 10-20x more data than needed
- Use `client.dataframe.get()`, not raw HTTP page iteration
- pandas `merge` + `groupby` on 100K-300K rows takes seconds — the bottleneck is network transfer, not Python processing

---

## QueryBuilder — Fluent Query API (SDK b8+)

> **Version check:** QueryBuilder requires SDK version b8 or later (`pip show PowerPlatform-Dataverse-Client` → Version ≥ 0.1.0b8). If you're on b7 or earlier, `client.query.builder()` does not exist — use `client.records.get()` instead (documented above). Do NOT introspect the SDK with `dir()` or `inspect` to discover APIs — if a method isn't documented here, it doesn't exist in the installed version.

QueryBuilder offers composable filters, OR/AND logic, and `.to_dataframe()` in one chain. It calls `client.records.get()` internally — it is a convenience layer, not a replacement.

```python
# Basic — flat record iteration
for record in client.query.builder("opportunity") \
        .select("name", "estimatedvalue", "statuscode") \
        .filter_eq("statuscode", 1) \
        .order_by("estimatedvalue", descending=True) \
        .top(100) \
        .execute():
    print(record["name"], record["estimatedvalue"])
```

**Direct DataFrame result** — combines query + pandas handoff in one call:

```python
df = client.query.builder("opportunity") \
    .select("name", "estimatedvalue", "statuscode") \
    .filter_eq("statuscode", 1) \
    .to_dataframe()
```

**Composable filter expressions** — for OR/AND logic:

```python
from PowerPlatform.Dataverse.models.filters import eq, gt

active_or_pending = (eq("statecode", 0) | eq("statecode", 1)) & gt("estimatedvalue", 10000)

df = client.query.builder("opportunity") \
    .select("name", "estimatedvalue") \
    .where(active_or_pending) \
    .to_dataframe()
```

**Paged execution** — when you need per-page control:

```python
for page in client.query.builder("opportunity").select("name").execute(by_page=True):
    for record in page:
        print(record["name"])
```

---

## Pandas DataFrame Handoff

**Prefer `client.dataframe.get()` for any read that involves analysis, verification, comparison, or export.** Use `client.records.get()` with page iteration only when you need per-page processing (e.g., streaming to a file) or when the table is too large to fit in memory.

| Task | Use | Why |
|---|---|---|
| Aggregate, group, pivot | `client.dataframe.get()` | pandas does this natively |
| Compare counts after import | `client.records.get()` with single-column select | Page-count is memory-efficient; no need to load full DataFrame for a count |
| Build a lookup map (small table) | `client.dataframe.get()` | `dict(zip(df["src_id"], df["guid"]))` — 1 line |
| Build a lookup map (100K+ rows) | `client.records.get()` | Page iterator uses less memory |
| Export to CSV/Excel | `client.dataframe.get()` | `df.to_csv("out.csv")` |
| Stream large result to file | `client.records.get()` | Page-at-a-time avoids loading all into memory |
| Cross-table join/aggregation | `client.dataframe.get()` both tables with `$select` + `pd.merge()` | pandas merge is sub-second; use `$select` to minimize network transfer |

**Always pass `select=` when calling `client.dataframe.get()` or `client.records.get()`.** Omitting `select` returns every column — on a 100K-row table with 20 columns, this transfers 10-20x more data than needed and turns a 15-second query into a 90-second query. Only request the columns you need.

Use `client.dataframe.get()` to pull Dataverse records directly into a pandas DataFrame — no manual page iteration needed:

```python
import pandas as pd

# Returns a fully consolidated DataFrame (all pages)
df = client.dataframe.get("opportunity",
    select=["name", "estimatedvalue", "statuscode", "_parentaccountid_value"],
)
print(df.groupby("statuscode")["estimatedvalue"].agg(["count", "sum", "mean"]))
```

**DataFrame write-back** — update or create records from a DataFrame. These are write operations — agents consulting **dv-data** for writes should also check here for the DataFrame variant. **Note:** DataFrame write-back supports `create` and `update` only — not upsert. For idempotent imports with alternate keys, use `client.records.upsert()` with `UpsertItem` (see **dv-data**).

```python
# Update records — DataFrame must include the primary key column
client.dataframe.update("opportunity", df_updates, id_column="opportunityid")

# Create records — returns a Series of new GUIDs
guids = client.dataframe.create("opportunity", df_new_records)
```

**Fallback (manual page iteration)** — use only when you need per-page processing. Prefer `client.dataframe.get()` above for the common case:

```python
all_records = []
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "statuscode"],
):
    all_records.extend([dict(r) for r in page])  # convert Record objects to dicts
df = pd.DataFrame(all_records)
```

---

## Jupyter Notebook Setup

> **Auth note:** Notebooks do not have a `scripts/` directory, so `scripts/auth.py` is not available. Use `InteractiveBrowserCredential` directly — this is the intended exception to the `scripts/auth.py` rule. For scripts (`.py` files), always use `scripts/auth.py`.

```python
# Cell 1: Setup
import os
from azure.identity import InteractiveBrowserCredential
from PowerPlatform.Dataverse.client import DataverseClient

credential = InteractiveBrowserCredential()
client = DataverseClient(
    base_url="https://<org>.crm.dynamics.com",  # replace with your org URL
    credential=credential,
)

# Cell 2: Load data into pandas (direct DataFrame, no manual iteration)
df = client.dataframe.get("account",
    select=["name", "industrycode", "revenue", "numberofemployees"],
)
df.head()
```

**Prerequisites:**
```bash
pip install --upgrade PowerPlatform-Dataverse-Client pandas matplotlib seaborn azure-identity
```

`pandas>=2.0.0` is a required dependency of the SDK (since b7) and is installed automatically with `--upgrade`.

---

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

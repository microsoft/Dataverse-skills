---
name: dv-query
description: >
  Read and analyze Dataverse records using the Python SDK and Web API — for operations MCP cannot handle.
  Use when: "query records", "read data", "expand lookup", "cross-table query", "join tables",
  "aggregate", "group by", "average", "sum", "count with HAVING", "$apply",
  "N:N expand", "notebook", "pandas", "DataFrame", "analyze data".
  Do not use when: MCP can handle the query (simple filters, single-record reads — use MCP first),
  creating or modifying records (use dv-data),
  creating tables or columns (use dv-metadata).
---

# Skill: Query — Read and Analyze Dataverse Records

> **This skill uses Python exclusively.** Do not use Node.js, JavaScript, or any other language for Dataverse scripting. See the overview skill's Hard Rules.

> **Check MCP first.** This skill is for operations MCP cannot handle. If MCP tools are available and the task is a simple filter, single-record read, or small result set, use MCP — no script needed.

## When to use this skill vs. MCP

| Task | Use |
|---|---|
| Simple filter ("show open tickets") | **MCP** `read_query` |
| Single record read | **MCP** `read_query` |
| Count records | **MCP** `read_query` |
| Multi-page iteration (thousands of records) | **dv-query** SDK |
| `$expand` to resolve lookup display names | **dv-query** SDK |
| `$apply` aggregation (GROUP BY, HAVING) | **dv-query** Web API |
| N:N `$expand` (collection-valued navigation) | **dv-query** Web API |
| Pandas DataFrame / Jupyter notebook handoff | **dv-query** `client.dataframe.get()` |
| Fluent composable query with OR/AND filters | **dv-query** `client.query.builder()` |

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

# Recommended for scripts — context manager handles connection cleanup
with DataverseClient(
    base_url=os.environ["DATAVERSE_URL"],
    credential=get_credential(),
) as client:
    pass  # your code here

# For notebooks / interactive sessions — explicit client
client = DataverseClient(
    base_url=os.environ["DATAVERSE_URL"],
    credential=get_credential(),
)
```

---

## Field Name Casing Rule

Getting this wrong causes 400 errors.

| Property type | Convention | Example | When used |
|---|---|---|---|
| **Structural** (columns) | LogicalName — always lowercase | `new_name`, `new_priority` | `$select`, `$filter`, `$orderby` |
| **Navigation** (lookups) | Navigation Property Name — case-sensitive, matches `$metadata` | `new_AccountId` | `$expand`, `@odata.bind` |

- System table navigation properties (e.g., `parentaccountid`, `ownerid`): lowercase
- Custom lookup navigation properties: case-sensitive, match `$metadata` SchemaName (e.g., `new_AccountId`)

---

## Query Records (multi-page)

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

`client.records.get()` returns a page iterator — always iterate pages and then records within each page.

---

## Fetch a Single Record by ID

```python
record = client.records.get("new_ticket", "<record-guid>",
    select=["new_name", "new_priority", "new_status"])
print(record["new_name"])
```

---

## $select with Lookup Columns (GUID-free display)

To show display names instead of GUIDs, use the formatted value annotation:

```python
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "_parentaccountid_value"],
):
    for r in page:
        account_name = r.get("_parentaccountid_value@OData.Community.Display.V1.FormattedValue")
        print(f"{r['name']} — {account_name}")
```

Formatted values are available for lookup, choice, status, and owner fields.

---

## $expand — Resolve Lookup to Full Related Record

```python
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue"],
    expand=["parentaccountid"],   # system nav props are lowercase
):
    for r in page:
        account = r.get("parentaccountid") or {}
        print(f"{r['name']} — {account.get('name', 'Unknown')}")
```

### $expand with multiple custom lookups

```python
for page in client.records.get(
    "new_ticket",
    select=["new_name", "new_priority", "new_status"],
    expand=["new_CustomerId", "new_AgentId"],  # Navigation Property Names, case-sensitive
):
    for r in page:
        customer = r.get("new_CustomerId") or {}
        agent    = r.get("new_AgentId") or {}
        print(f"{r['new_name']} | {customer.get('new_name','')} | {agent.get('new_name','')}")
```

> `expand` uses the Navigation Property Name (`new_CustomerId`), not the lowercase logical name (`new_customerid`). Using lowercase causes a 400 error.

---

## $expand on N:N Relationships (Web API — SDK does not support)

```python
import json, urllib.request
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

For GROUP BY, HAVING, and server-side aggregates:

```python
import json, urllib.request
from auth import get_token, load_env

load_env()
env = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

# Count and sum opportunities by status
url = (f"{env}/api/data/v9.2/opportunities"
       f"?$apply=groupby((statuscode),"
       f"aggregate($count as count,estimatedvalue with sum as total_value))")
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    for row in json.loads(resp.read())["value"]:
        print(f"Status {row['statuscode']}: {row['count']} records, ${row['total_value']:,.0f}")
```

---

## QueryBuilder — Fluent Query API

For composable, readable queries without constructing OData strings manually:

```python
from PowerPlatform.Dataverse.models.query_builder import QueryBuilder

# Basic — flat record iteration
for record in client.query.builder("opportunity") \
        .select("name", "estimatedvalue", "statuscode") \
        .filter_eq("statuscode", 1) \
        .order_by("estimatedvalue desc") \
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
    .filter(active_or_pending) \
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

Use `client.dataframe.get()` to pull Dataverse records directly into a pandas DataFrame — no manual page iteration needed:

```python
import pandas as pd

# Returns a fully consolidated DataFrame (all pages)
df = client.dataframe.get("opportunity",
    select=["name", "estimatedvalue", "statuscode", "_parentaccountid_value"],
)
print(df.groupby("statuscode")["estimatedvalue"].agg(["count", "sum", "mean"]))
```

**DataFrame write-back** — update or create records from a DataFrame:

```python
# Update records — DataFrame must include the primary key column
client.dataframe.update("opportunity", df_updates, id_column="opportunityid")

# Create records — returns a Series of new GUIDs
guids = client.dataframe.create("opportunity", df_new_records)
```

**Fallback (manual page iteration)** — use when you need per-page processing:

```python
all_records = []
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "statuscode"],
):
    all_records.extend(page)
df = pd.DataFrame(all_records)
```

---

## Jupyter Notebook Setup

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

## Windows Scripting Notes

- **ASCII only** in `.py` files — curly quotes and em dashes cause `SyntaxError` on Windows.
- **No `python -c` for multiline code** — write a `.py` file instead.
- **Generate GUIDs in scripts**: `str(uuid.uuid4())`, not shell backtick substitution.

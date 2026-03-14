---
name: dataverse-python-sdk
description: >
  Use the official Microsoft Dataverse Python SDK for data operations.
  USE WHEN: "use the SDK", "query records", "create records", "bulk operations", "upsert",
  "Python script for Dataverse", "read data", "write data", "upload file",
  "bulk import", "CSV import", "load data", "data profiling", "data quality",
  "analyze data", "Jupyter notebook", "pandas", "notebook".
  DO NOT USE WHEN: creating forms/views (use dataverse-metadata with Web API),
  exporting solutions (use dataverse-solution with PAC CLI).
---

# Skill: Python SDK

> **This skill uses Python exclusively.** Do not use Node.js, JavaScript, or any other language for Dataverse scripting. If you are about to run `npm install` or write a `.js` file, STOP — you are going off-rails. See the overview skill's Hard Rules.

Use the official Microsoft Power Platform Dataverse Client Python SDK for data operations and basic table management in scripts and automation.

**Official SDK:** https://github.com/microsoft/PowerPlatform-DataverseClient-Python
**PyPI package:** `PowerPlatform-Dataverse-Client` (this is the only official one — do not use `dataverse-api` or other unofficial packages)
**Status:** Preview — breaking changes are possible

```
pip install --upgrade PowerPlatform-Dataverse-Client
```

---

## What This SDK Supports

- Data CRUD: create, read, update, delete records
- Upsert (with alternate key support)
- Bulk operations: `CreateMultiple`, `UpdateMultiple`, `UpsertMultiple`
- OData queries: `select`, `filter`, `orderby`, `expand`, `top`, paging
- SQL queries (read-only, via Web API `?sql=` parameter)
- Table create, delete, and metadata (`tables.get()`, `tables.list()`)
- Relationship metadata: create/delete 1:N and N:N relationship definitions
- Alternate key management
- File column uploads (chunked for files >128MB)
- Context manager support with HTTP connection pooling

## What This SDK Does NOT Support

- **Forms** (FormXml) — use the Web API directly (see `dataverse-metadata`)
- **Views** (SavedQueries) — use the Web API directly
- **Option sets** — use the Web API directly
- **N:N record association** ($ref linking for N:N data, e.g., role assignments) — use the Web API directly
- DeleteMultiple, general OData batching

For anything not in the "supports" list above, write a Web API script using `scripts/auth.py` for token acquisition.

### SDK-First Rule

**If an operation is in the "supports" list, you MUST use the SDK — not `urllib`, `requests`, or raw HTTP.** This applies to:
- **All record CRUD** (create, read, update, delete) — use `client.records.create()`, `.get()`, `.update()`, `.delete()`
- **All queries** with `$select`, `$filter`, `$orderby`, `$expand` on 1:N lookups — use `client.records.get()` with `select=`, `filter=`, `expand=`, `orderby=`
- **Bulk operations** — pass a list to `client.records.create(table, [list])` instead of looping with individual HTTP POSTs
- **Publisher and solution records** — these are standard Dataverse tables; use `client.records.create("publisher", {...})` and `client.records.create("solution", {...})`

Raw HTTP is only acceptable for: forms, views, option sets, N:N `$ref` associations, N:N `$expand`, `$apply` aggregation, memo columns, and unbound actions.

### Field Name Casing Rule

Dataverse uses two different naming conventions for properties. Getting this wrong causes 400 errors.

| Property type | Name convention | Example | When used |
|---|---|---|---|
| **Structural** (columns) | LogicalName (always lowercase) | `new_name`, `new_priority` | `$select`, `$filter`, `$orderby`, record payload keys |
| **Navigation** (relationships / lookups) | Navigation Property Name (case-sensitive, must match `$metadata`) | `new_AccountId`, `new_DepartmentId` | `$expand`, `@odata.bind` annotation keys |

- **`$select`, `$filter`, `$orderby`**: always lowercase logical names (`new_name`, `new_priority`)
- **`$expand` navigation properties**: Navigation Property Name, case-sensitive (`new_AccountId`, `new_DepartmentId`)
- **`@odata.bind` keys**: Navigation Property Name, case-sensitive (`new_AccountId@odata.bind`)
- **Record payloads** (create/update data): lowercase logical names for regular fields; `@odata.bind` keys preserve the navigation property casing

The SDK handles this correctly: it lowercases structural property keys but preserves `@odata.bind` key casing.

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

`get_credential()` returns `ClientSecretCredential` (if CLIENT_ID + CLIENT_SECRET are in `.env`) or `DeviceCodeCredential` (interactive fallback). See `scripts/auth.py`.

---

## Common Operations

### Create a record
```python
guid = client.records.create("new_projectbudget", {
    "new_name": "Q1 Marketing Budget",
    "new_amount": 75000.00,
    "new_status": 100000000,
    # Lookup binding — see "@odata.bind rules" section below
    "new_AccountId@odata.bind": "/accounts(<account-guid>)",
})
print(f"Created: {guid}")
```

**Lookup binding (`@odata.bind`) notes:**
- If you just created lookup columns, wait 5-10 seconds before inserting records that reference them. Metadata propagation delays can cause "Invalid property" errors.
- Choice (picklist) columns use integer values, not strings: `"new_status": 100000000` (not `"Draft"`).
- If a record insert fails with "Invalid property", verify the lookup column's logical name and navigation property name by querying `EntityDefinitions(LogicalName='...')/Attributes`.

### Query records (multi-record — returns page iterator)
```python
for page in client.records.get(
    "new_projectbudget",
    select=["new_name", "new_amount", "new_status"],
    filter="new_status eq 100000000",
    orderby=["new_name asc"],
    top=50,
):
    for r in page:
        print(r["new_name"], r["new_amount"])
```

### Fetch a single record by ID
```python
record = client.records.get("new_projectbudget", "<record-guid>",
    select=["new_name", "new_amount"])
print(record["new_name"])
```

### Update a record
```python
client.records.update("new_projectbudget", "<record-guid>",
    {"new_status": 100000001})
```

### Delete a record
```python
client.records.delete("new_projectbudget", "<record-guid>")
```

### Bulk create (SDK uses CreateMultiple internally)
```python
records = [{"new_name": f"Budget {i}"} for i in range(100)]
guids = client.records.create("new_projectbudget", records)
print(f"Created {len(guids)} records")
```

### Bulk update (broadcast same change to multiple records)
```python
client.records.update("new_projectbudget",
    [id1, id2, id3],
    {"new_status": 100000001})
```

### Upsert (with alternate keys)
```python
from PowerPlatform.Dataverse.models.upsert import UpsertItem

client.records.upsert("account", [
    UpsertItem(
        alternate_key={"accountnumber": "ACC-001"},
        record={"name": "Contoso Ltd", "description": "Primary account"},
    ),
])
```

### Create a table
```python
from enum import IntEnum

class BudgetStatus(IntEnum):
    DRAFT = 100000000
    APPROVED = 100000001

info = client.tables.create(
    "new_ProjectBudget",
    {
        "new_Amount": "decimal",
        "new_Status": BudgetStatus,
    },
    solution="MySolution",
    primary_column="new_Name",
)
print(f"Created: {info['table_schema_name']}, entity set: {info['entity_set_name']}")
```

### Add columns to an existing table
```python
created = client.tables.add_columns("new_projectbudget", {
    "new_Notes": "string",
    "new_Active": "bool",
})
```

### Create a lookup (1:N relationship)
```python
result = client.tables.create_lookup_field(
    referencing_table="new_projectbudget",
    lookup_field_name="new_AccountId",
    referenced_table="account",
    display_name="Account",
    solution="MySolution",
)
print(f"Created lookup: {result.lookup_schema_name}")
# The nav property for @odata.bind is the lookup's Navigation Property Name (case-sensitive)
```

### Create a many-to-many relationship
```python
from PowerPlatform.Dataverse.models.relationship import ManyToManyRelationshipMetadata

result = client.tables.create_many_to_many_relationship(
    ManyToManyRelationshipMetadata(
        schema_name="new_employee_project",
        entity1_logical_name="new_employee",
        entity2_logical_name="new_project",
    ),
    solution="MySolution",
)
```

---

## @odata.bind Rules (Lookup Binding)

When creating or updating a record that sets a lookup field, you must use `@odata.bind` with the correct **navigation property name**. Getting this wrong is the #1 cause of 400 errors.

### The rule

```
<NavigationPropertyName>@odata.bind = "/<EntitySetName>(<target-guid>)"
```

- **Navigation property name**: Case-sensitive, must match the entity's `$metadata`. For custom lookups this is typically the SchemaName (e.g., `new_AccountId`). Do NOT use the lowercase logical name.
- **Entity set name**: The plural collection name of the referenced table (e.g., `accounts`, `contacts`).

### Examples

| Lookup field | Correct `@odata.bind` key | Wrong |
|---|---|---|
| `new_AccountId` (custom) | `new_AccountId@odata.bind` | ~~`new_accountid@odata.bind`~~ |
| `customerid` (system polymorphic) | `customerid_account@odata.bind` | ~~`customerid@odata.bind`~~ |
| `parentcustomerid` (system) | `parentcustomerid_account@odata.bind` | ~~`_parentcustomerid_value@odata.bind`~~ |

### How to find the navigation property name

1. **After creating a lookup via SDK**: `result.lookup_schema_name` is the navigation property name.
2. **For system tables**: Query the relationship metadata:
   ```
   GET /api/data/v9.2/EntityDefinitions(LogicalName='<entity>')/ManyToOneRelationships?$select=ReferencingEntityNavigationPropertyName,ReferencedEntity
   ```
3. **Rule of thumb for custom lookups**: The navigation property name matches the lookup field's SchemaName (e.g., `new_AccountId`). Always verify against `$metadata` if unsure.

---

## $select with Lookup Columns

When using `$select` to include a lookup column in query results, use the `_<logicalname>_value` format:

```python
# Correct — lookup value in $select uses underscore-wrapped format
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "_parentaccountid_value"],
    top=10,
):
    for r in page:
        account_id = r.get("_parentaccountid_value")
        account_name = r.get("_parentaccountid_value@OData.Community.Display.V1.FormattedValue")
```

To get the full related record instead, use `$expand`:

```python
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue"],
    expand=["parentaccountid"],  # system nav props are lowercase
    top=10,
):
    for r in page:
        account = r.get("parentaccountid")
        if account:
            print(account["name"])
```

> **Note:** System table navigation properties (e.g., `parentaccountid`, `ownerid`) are lowercase. Custom lookup navigation properties are case-sensitive and must match `$metadata` (e.g., `new_AccountId`). When in doubt, query the entity's `ManyToOneRelationships` metadata.

### $expand with multiple custom lookups

Use the correct navigation property names (case-sensitive, must match `$metadata`):

```python
# Expand multiple lookups — e.g., project budgets with account and department details
for page in client.records.get(
    "new_projectbudget",
    select=["new_name", "new_amount", "new_status"],
    filter="new_status eq 100000001",
    expand=["new_AccountId", "new_DepartmentId"],
    orderby=["new_amount desc"],
):
    for budget in page:
        acct = budget.get("new_AccountId") or {}
        dept = budget.get("new_DepartmentId") or {}
        print(f"{budget['new_name']}: {acct.get('name', '')} / {dept.get('new_name', '')}")
```

> **Important:** `expand` uses the navigation property name (case-sensitive, e.g., `new_AccountId`), not the lowercase logical name (`new_accountid`). Using lowercase causes a 400 error.

### $expand on N:N relationships

N:N expand uses the relationship navigation property name (found in the ManyToManyRelationships metadata). The SDK does **not** support `$expand` on N:N collection-valued navigation properties in multi-record queries. For N:N traversal, use the Web API directly:

```python
# Fall back to Web API for N:N expand
import urllib.request, json
from auth import get_token

token = get_token()
url = f"{env}/api/data/v9.2/new_projectdocuments?$select=new_title&$expand=new_ProjectBudget_Documents($select=new_name)"
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    articles = json.loads(resp.read())["value"]
```

> **Use the SDK for all queries except N:N expand.** Do not fall back to `requests` or `urllib` for standard queries, lookups, or 1:N expand — the SDK handles these correctly.

---

## Error Handling

```python
from PowerPlatform.Dataverse.core.errors import HttpError

try:
    guid = client.records.create("account", {"name": "Contoso"})
except HttpError as e:
    print(f"Status {e.status_code}: {e.message}")
    if e.details:
        print(f"Details: {e.details}")
    if e.status_code == 400:
        # Bad request — check field names, @odata.bind format, required fields
        pass
    elif e.status_code == 403:
        # Permission denied — check security roles
        pass
    elif e.status_code == 404:
        # Table or record not found
        pass
    elif e.status_code == 429:
        # Rate limited — the SDK handles retry automatically,
        # but if you hit this, reduce batch sizes or add delays
        pass
```

---

## Bulk Import from CSV

For loading records from a CSV file, use the SDK directly — it handles batching via `CreateMultiple` internally.

### When to use which tool

| Volume | Tool | Why |
|--------|------|-----|
| 1–10 records | MCP `create_record` | Simple, conversational |
| 10+ records | Python SDK `client.records.create(table, list)` | Built-in batching, error handling, retry |

### CSV import pattern

```python
import csv, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient
from PowerPlatform.Dataverse.core.errors import HttpError

load_env()
client = DataverseClient(
    base_url=os.environ["DATAVERSE_URL"],
    credential=get_credential(),
)

# Read CSV
with open("data/tickets.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# Map CSV columns to Dataverse fields
records = []
for row in rows:
    records.append({
        "new_name": row["Title"],
        "new_description": row["Description"],
        "new_priority": int(row["Priority"]),
        # Lookup binding — use navigation property name (case-sensitive)
        "new_AccountId@odata.bind": f"/accounts({row['AccountGuid']})",
    })

# Bulk create — SDK uses CreateMultiple internally
guids = client.records.create("new_ticket", records)
print(f"Created {len(guids)} tickets")
```

### Required field discovery

Before bulk-creating records in a **system table** (account, contact, opportunity), create a single test record first:

1. Build a minimal payload with only the fields you intend to populate
2. Create it as a single record: `client.records.create("account", {...})`
3. If it raises `HttpError` with status 400, the error message names the missing required field
4. Some required fields are **plugin-enforced** (not visible in `describe_table`) and only triggered by certain field combinations
5. Once the test record succeeds, delete it, then proceed with the bulk create

---

## Aggregation Queries (Web API $apply)

The SDK does not support OData `$apply` for aggregation. Use the Web API directly for GROUP BY, COUNT, SUM, AVG, etc.:

```python
import os, json, urllib.request
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env

load_env()
env = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

# Example: count opportunities by status
url = f"{env}/api/data/v9.2/opportunities?$apply=groupby((statuscode),aggregate($count as count))"
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
    "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())
    for row in data["value"]:
        print(f"Status {row['statuscode']}: {row['count']}")
```

For complex analytics (duplicates, cross-table joins, filtered aggregates), pull data into pandas:

```python
import pandas as pd

# Pull all records into a DataFrame
all_records = []
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "statuscode", "_parentaccountid_value"],
):
    all_records.extend(page)

df = pd.DataFrame(all_records)
# Now use pandas for analysis: groupby, pivot, merge, duplicates, etc.
print(df.groupby("statuscode")["estimatedvalue"].sum())
```

---

## Jupyter Notebook Setup

For interactive analysis with visualizations.

### Prerequisites

```bash
pip install --upgrade PowerPlatform-Dataverse-Client pandas matplotlib seaborn azure-identity
```

### Notebook structure

```python
# Cell 1: Setup
import os
from azure.identity import InteractiveBrowserCredential
from PowerPlatform.Dataverse.client import DataverseClient

credential = InteractiveBrowserCredential()
client = DataverseClient(
    base_url="https://<org>.crm.dynamics.com",  # replace with your URL
    credential=credential,
)

# Cell 2: Load data into pandas
import pandas as pd

accounts = []
for page in client.records.get("account",
    select=["name", "industrycode", "revenue", "numberofemployees"],
):
    accounts.extend(page)
df_accounts = pd.DataFrame(accounts)

# Cell 3+: Analysis with pandas, matplotlib, seaborn
```

---

## Windows Scripting Notes

When writing Python scripts on Windows (especially in Git Bash / Claude Code):

- **Use only ASCII characters** in script files — no curly quotes, em dashes, or non-ASCII. These cause `SyntaxError` on Windows.
- **Avoid `python -c`** for anything beyond trivial one-liners. Write a `.py` file instead — multiline `python -c` commands break on Windows due to quoting differences.
- **Generate GUIDs in scripts**, not inline: use `str(uuid.uuid4())` inside the script rather than backtick-substitution in shell commands.

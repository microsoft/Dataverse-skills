---
name: dv-data
description: >
  Create, update, delete, bulk-import, and upsert Dataverse records using the official Python SDK.
  Use when: "create records", "insert data", "bulk create", "bulk update", "bulk import",
  "import CSV", "load data", "upsert", "upsert records", "write data", "upload file",
  "add records", "CreateMultiple", "UpdateMultiple", "UpsertMultiple".
  Do not use when: querying or reading records (use dv-query),
  creating tables, columns, or relationships (use dv-metadata),
  exporting solutions (use dv-solution).
---

# Skill: Data — Create, Update, Delete, and Bulk Import

> **This skill uses Python exclusively.** Do not use Node.js, JavaScript, or any other language for Dataverse scripting. If you are about to run `npm install` or write a `.js` file, STOP — you are going off-rails. See the overview skill's Hard Rules.

Use the official Microsoft Power Platform Dataverse Client Python SDK for all data write operations.

**Official SDK:** https://github.com/microsoft/PowerPlatform-DataverseClient-Python
**PyPI package:** `PowerPlatform-Dataverse-Client` (this is the only official one — do not use `dataverse-api` or other unofficial packages)
**Status:** Preview — breaking changes are possible

```
pip install --upgrade PowerPlatform-Dataverse-Client
```

## Skill boundaries

| Need | Use instead |
|---|---|
| Query or read records | **dv-query** |
| Create tables, columns, relationships, forms, views | **dv-metadata** |
| Export or deploy solutions | **dv-solution** |

---

## Before Writing ANY Script — Check MCP First

**If MCP tools are available** (`create_record`, `update_record`) and the task is ≤10 records, **use MCP directly — no script needed.** Only write a Python script when the task requires: bulk operations (10+ records), data transformation, retry logic, CSV import, or operations the SDK supports that MCP cannot (upsert, file uploads). Sequential MCP tool calls are not "multi-step logic" — use MCP for those.

## SDK-First Rule

**If an operation is in the "supports" list below, you MUST use the SDK — not `urllib`, `requests`, or raw HTTP.**

**Correct imports:**
```python
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient
```

**WRONG for SDK-supported operations:**
```python
from auth import get_token, load_env  # WRONG for SDK-supported ops
import requests                        # WRONG for SDK-supported ops
```

`get_token()` and `requests` exist ONLY for operations the SDK does not support (forms, views, `$apply`, N:N `$expand`, unbound actions) — see **dv-query** and **dv-metadata**.

---

## What This SDK Supports (Data Operations)

- Record writes: create, update, delete
- Record reads within write workflows (e.g., lookup resolution) — for standalone queries see **dv-query**
- Upsert (with alternate key support)
- Bulk operations: `CreateMultiple`, `UpdateMultiple`, `UpsertMultiple`
- File column uploads (chunked for files >128MB)
- Context manager with HTTP connection pooling

## What This SDK Does NOT Support

Use raw Web API (`get_token()`) for:
- Forms (FormXml) — see **dv-metadata**
- Views (SavedQueries) — see **dv-metadata**
- Global option sets — see **dv-metadata**
- N:N record association (`$ref` POST) — use raw Web API (`POST /api/data/v9.2/<entity>(<id>)/<nav-property>/$ref`)
- N:N `$expand` — see **dv-query**
- `$apply` aggregation — see **dv-query**
- Unbound actions (e.g., `InstallSampleData`)
- DeleteMultiple, general OData batching

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

For scripts that run to completion: wrap in `with DataverseClient(...) as client:` for automatic connection cleanup (recommended since b6). For notebooks and interactive sessions, the explicit client above is simpler.

---

## Field Name Casing Rule

Getting this wrong causes 400 errors.

| Property type | Convention | Example | When used |
|---|---|---|---|
| **Structural** (columns) | LogicalName — always lowercase | `new_name`, `new_priority` | Record payload keys |
| **Navigation** (lookups) | Navigation Property Name — case-sensitive, matches `$metadata` | `new_AccountId` | `@odata.bind` keys |

The SDK lowercases structural keys automatically but preserves `@odata.bind` key casing.

---

## Create a Record

```python
guid = client.records.create("new_ticket", {
    "new_name": "Ticket 001",
    "new_priority": 100000002,          # choice column — integer value, not string
    "new_AccountId@odata.bind": "/accounts(<account-guid>)",
})
print(f"Created: {guid}")
```

**`@odata.bind` notes:**
- Key is the Navigation Property Name: `new_AccountId@odata.bind` (the SDK preserves casing automatically as of b6, but matching the schema name is still the correct form)
- Value is `"/<EntitySetName>(<guid>)"` — e.g., `"/accounts(<guid>)"`
- If you just created the lookup column, wait 5–10 seconds before inserting. Metadata propagation delays cause "Invalid property" errors.
- Choice columns use integer values, not strings: `"new_priority": 100000002` (not `"High"`)

### Common `@odata.bind` patterns

| Lookup | Correct key | Wrong |
|---|---|---|
| Custom: `new_AccountId` | `new_AccountId@odata.bind` | ~~`new_accountid@odata.bind`~~ |
| System polymorphic: `customerid` | `customerid_account@odata.bind` | ~~`customerid@odata.bind`~~ |
| System: `parentcustomerid` | `parentcustomerid_account@odata.bind` | ~~`_parentcustomerid_value@odata.bind`~~ |

### Find the Navigation Property Name

After creating a lookup via SDK: `result.lookup_schema_name` is the navigation property name.

For existing system tables, query:
```
GET /api/data/v9.2/EntityDefinitions(LogicalName='<entity>')/ManyToOneRelationships
  ?$select=ReferencingEntityNavigationPropertyName,ReferencedEntity
```

---

## Update a Record

```python
client.records.update("new_ticket", "<record-guid>",
    {"new_status": 100000001})
```

---

## Delete a Record

```python
client.records.delete("new_ticket", "<record-guid>")
```

---

## Bulk Create (SDK uses CreateMultiple internally)

```python
records = [{"new_name": f"Ticket {i}", "new_priority": 100000000} for i in range(500)]
guids = client.records.create("new_ticket", records)
print(f"Created {len(guids)} records")
```

Volume guidance: MCP `create_record` for 1–10 records. SDK for 10+ — it handles batching (max 1,000 per batch) and retry automatically.

---

## Bulk Update

```python
# Broadcast same change to multiple records
client.records.update("new_ticket",
    [id1, id2, id3],
    {"new_status": 100000001})
```

---

## Upsert (Alternate Keys)

Idempotent — re-running the same import does not create duplicates. The alternate key must be defined on the table first — see **dv-metadata**.

```python
from PowerPlatform.Dataverse.models.upsert import UpsertItem

client.records.upsert("account", [
    UpsertItem(
        alternate_key={"accountnumber": "ACC-001"},
        record={"name": "Contoso Ltd", "description": "Primary account"},
    ),
    UpsertItem(
        alternate_key={"accountnumber": "ACC-002"},
        record={"name": "Fabrikam Inc"},
    ),
])
```

---

## Bulk Import from CSV

| Volume | Tool | Why |
|---|---|---|
| 1–10 records | MCP `create_record` | Simple, no script |
| 10+ records | SDK `client.records.create(table, list)` | Built-in batching, retry |

```python
import csv, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient

load_env()
client = DataverseClient(base_url=os.environ["DATAVERSE_URL"], credential=get_credential())

with open("data/customers.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

records = [{"new_name": row["name"], "new_email": row["email"]} for row in rows]
guids = client.records.create("new_customer", records)
print(f"Imported {len(guids)} customers")
```

### Lookup resolution during import

If the CSV has a human-readable key (e.g., `customer_email`) but Dataverse needs a GUID, pre-resolve with a lookup dict:

```python
# Build email -> GUID map first
email_to_guid = {}
for page in client.records.get("new_customer", select=["new_customerid", "new_email"]):
    for r in page:
        email_to_guid[r["new_email"]] = r["new_customerid"]

# Use it during import
records = []
for row in rows:
    customer_guid = email_to_guid.get(row["customer_email"])
    if not customer_guid:
        print(f"Skipping row — unknown email: {row['customer_email']}")
        continue
    records.append({
        "new_channel": row["channel"],
        "new_CustomerId@odata.bind": f"/new_customers({customer_guid})",
    })

guids = client.records.create("new_interaction", records)
```

### Required field discovery for system tables

Before bulk-creating in a system table (account, contact, opportunity):
1. Create a single test record with your intended minimal payload
2. If `HttpError` 400 is raised, the error message names the missing required field
3. Some required fields are plugin-enforced and not visible in `describe_table`
4. Delete the test record, then proceed with bulk create

---

## Error Handling

```python
from PowerPlatform.Dataverse.core.errors import HttpError

try:
    guid = client.records.create("new_ticket", {"new_name": "Test"})
except HttpError as e:
    print(f"Status {e.status_code}: {e.message}")
    if e.details:
        print(f"Details: {e.details}")
    # 400 — bad field name, @odata.bind format, or missing required field
    # 403 — check security roles
    # 404 — table or record not found
    # 429 — rate limited; SDK retries automatically, reduce batch size if persistent
```

---

## Windows Scripting Notes

- **ASCII only** in `.py` files — curly quotes and em dashes cause `SyntaxError` on Windows.
- **No `python -c` for multiline code** — write a `.py` file instead.
- **Generate GUIDs in scripts**: `str(uuid.uuid4())`, not shell backtick substitution.

---
name: dataverse-python-sdk
description: Use the official Microsoft Dataverse Python SDK for data operations. Use this when reading or writing records, bulk operations, or querying live data.
---

# Skill: Python SDK

Use the official Microsoft Power Platform Dataverse Client Python SDK for data operations and basic table management in scripts and automation.

**Official SDK:** https://github.com/microsoft/PowerPlatform-DataverseClient-Python
**PyPI package:** `PowerPlatform-Dataverse-Client` (this is the only official one — do not use `dataverse-api` or other unofficial packages)
**Status:** Preview — breaking changes are possible

```
pip install PowerPlatform-Dataverse-Client
```

---

## What This SDK Supports

- Data CRUD: create, read, update, delete records
- Bulk operations: `CreateMultiple`, `UpdateMultiple`
- OData queries: `select`, `filter`, `orderby`, `expand`, `top`, paging
- Table create and delete
- File column uploads (chunked for files >128MB)

## What This SDK Does NOT Support

- **Forms** (FormXml) — use the Web API directly (see `dataverse-metadata`)
- **Views** (SavedQueries) — use the Web API directly
- **Relationships** (1:N, N:N) — use the Web API directly
- **Lookup columns** — explicitly listed as a current limitation; use the Web API directly
- **Option sets** — use the Web API directly
- Upsert, DeleteMultiple, general OData batching

For anything not in the "supports" list above, write a Web API script using `scripts/auth.py` for token acquisition.

---

## Setup

```python
from azure.identity import InteractiveBrowserCredential
from PowerPlatform.Dataverse.client import DataverseClient

credential = InteractiveBrowserCredential()
client = DataverseClient(
    resource_url=os.environ["DATAVERSE_URL"],
    credential=credential,
)
```

For non-interactive (service principal) auth — preferred for dev tenants:
```python
from azure.identity import ClientSecretCredential

credential = ClientSecretCredential(
    tenant_id=os.environ["TENANT_ID"],
    client_id=os.environ["CLIENT_ID"],
    client_secret=os.environ["CLIENT_SECRET"],
)
client = DataverseClient(
    resource_url=os.environ["DATAVERSE_URL"],
    credential=credential,
)
```

---

## Common Operations

### Create a record
```python
result = client.entity("new_projectbudget").create({
    "new_name": "Q1 Marketing Budget",
    "new_amount": 75000.00,
    "new_status": 100000000,
    "new_accountid@odata.bind": "/accounts(<account-guid>)"
})
# Returns the new record GUID
```

### Query records
```python
records = client.entity("new_projectbudget").read(
    select=["new_name", "new_amount", "new_status"],
    filter="new_status eq 100000000",
    orderby="new_name asc",
    top=50
)
for r in records:
    print(r["new_name"], r["new_amount"])
```

### Update a record
```python
client.entity("new_projectbudget").update(
    entity_id="<record-guid>",
    data={"new_status": 100000001}
)
```

### Delete a record
```python
client.entity("new_projectbudget").delete(entity_id="<record-guid>")
```

### Bulk create
```python
records = [{"new_name": f"Budget {i}"} for i in range(100)]
client.entity("new_projectbudget").create(records)
```

### Create a table
```python
client.create_table(
    schema_name="new_ProjectBudget",
    display_name="Project Budget",
    display_collection_name="Project Budgets",
    primary_name_column_schema_name="new_name",
    primary_name_column_display_name="Name",
)
```

---

## Where SDK Scripts Live

Scripts using the SDK go in `/scripts/`. Keep them small and single-purpose:

```
scripts/
  auth.py              — Azure Identity token acquisition (used by all scripts)
  validate.py          — post-import validation
  assign-user.py       — user provisioning and role assignment
  seed-data.py         — example: load test data into an environment
  export-to-csv.py     — example: export table data
```

Both the SDK and Web API scripts now use Azure Identity for auth via `auth.py`. For Web API scripts (forms, views, relationships), use `get_token()`. For data scripts using this SDK, use `get_credential()` to get a `TokenCredential` directly.

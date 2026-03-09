---
name: dataverse-python-sdk
description: >
  Use the official Microsoft Dataverse Python SDK for data operations.
  WHEN: "use the SDK", "query records", "create records", "bulk operations", "upsert",
  "Python script for Dataverse", "read data", "write data", "upload file".
  DO NOT USE WHEN: creating forms/views/relationships (use dataverse-metadata with Web API),
  exporting solutions (use dataverse-solution with PAC CLI).
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
- **Record association** ($ref linking for N:N data, e.g., role assignments) — use the Web API directly
- DeleteMultiple, general OData batching

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

```text
scripts/
  auth.py              — Azure Identity token acquisition (used by all scripts)
  assign-user.py       — user provisioning and role assignment
```

Both the SDK and Web API scripts use Azure Identity for auth via `auth.py`. For Web API scripts (forms, views, relationships), use `get_token()`. For data scripts using this SDK, use `get_credential()` to get a `TokenCredential` directly.

Post-import validation (table existence, form checks, role checks, import errors) is done inline using the SDK — see `/dataverse:solution` for patterns.

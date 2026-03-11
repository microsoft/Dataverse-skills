---
name: dataverse-python-sdk
description: >
  Use the official Microsoft Dataverse Python SDK for data operations.
  USE WHEN: "use the SDK", "query records", "create records", "bulk operations", "upsert",
  "Python script for Dataverse", "read data", "write data", "upload file",
  "bulk import", "CSV import", "load data", "data profiling", "data quality",
  "analyze data", "Jupyter notebook", "pandas", "notebook".
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

---

## Bulk Import via Web API $batch

For loading 50+ records (e.g., from a CSV file), use the Web API `$batch` endpoint instead of MCP `create_record` (which is one-at-a-time and impractical at scale).

### When to use which tool

| Volume | Tool | Why |
|--------|------|-----|
| 1–50 records | MCP `create_record` | Simple, conversational |
| 50–1000 records | Web API `$batch` | Fast, handles rate limits with retry |
| 1000+ records | Python SDK `CreateMultiple` | Built-in batching |

### $batch request pattern

```python
import csv, json, uuid, time, requests
from auth import get_token, load_env

load_env()
DATAVERSE_URL = os.environ["DATAVERSE_URL"].rstrip("/")
API = f"{DATAVERSE_URL}/api/data/v9.2"

def batch_create(token, entity_set, records, batch_size=20):
    """Create records via $batch in chunks with rate-limit retry."""
    created, failed = 0, 0
    for i in range(0, len(records), batch_size):
        chunk = records[i:i + batch_size]
        for attempt in range(3):
            batch_id = f"batch_{uuid.uuid4()}"
            changeset_id = f"changeset_{uuid.uuid4()}"
            parts = [f"--{batch_id}",
                     f"Content-Type: multipart/mixed; boundary={changeset_id}", ""]
            for idx, rec in enumerate(chunk):
                parts += [f"--{changeset_id}", "Content-Type: application/http",
                          "Content-Transfer-Encoding: binary", f"Content-ID: {idx+1}", "",
                          f"POST {API}/{entity_set} HTTP/1.1",
                          "Content-Type: application/json", "", json.dumps(rec)]
            parts += [f"--{changeset_id}--", f"--{batch_id}--"]
            resp = requests.post(f"{API}/$batch", data="\r\n".join(parts),
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": f"multipart/mixed; boundary={batch_id}",
                         "OData-MaxVersion": "4.0", "OData-Version": "4.0"})
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))  # backoff: 5s, 10s, 15s
                continue
            if resp.status_code == 200 and "HTTP/1.1 4" not in resp.text:
                created += len(chunk)
            else:
                failed += len(chunk)
            break
        time.sleep(1)  # pause between batches to avoid rate limits
    return created, failed
```

### Rate limits and batch sizing

- **Batch size:** 20 records per changeset is safe. 50 can trigger 429s.
- **Inter-batch delay:** 1 second between batches prevents rate limiting.
- **429 retry:** Wait `5 * attempt` seconds, retry up to 3 times.
- **Changeset atomicity:** If any record in a changeset fails, the entire changeset is rolled back. Keep batch sizes small so one bad record doesn't block 49 good ones.

### Required field discovery

Before bulk-creating records in a **system table** (account, contact, opportunity, etc.), create a single test record first:

1. Build a minimal payload with only the fields you intend to populate
2. POST it as a single record (not in a batch)
3. If it returns 400, read the error — it will name the missing required field
4. Some required fields are **plugin-enforced** (not visible in `describe_table` NOT NULL) and only triggered by certain field combinations
5. Once the test record succeeds, delete it, then proceed with the batch

This avoids discovering required fields mid-batch where the entire changeset gets rolled back.

---

## Jupyter Notebook Setup

For interactive analysis with visualizations, use a Jupyter notebook with the `query_dataverse()` helper above.

### Prerequisites

```bash
pip install pandas matplotlib seaborn requests azure-identity
```

### Notebook structure

```python
# Cell 1: Setup
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), ".github", "plugins", "dataverse", "scripts"))
from auth import get_token, load_env
load_env()
# ... paste query_dataverse() helper ...

# Cell 2: Load data
accounts = query_dataverse("accounts", select="accountid,name,industrycode,revenue,numberofemployees")
contacts = query_dataverse("contacts", select="contactid,fullname,emailaddress1,_parentcustomerid_value")

# Cell 3+: Analysis with pandas, matplotlib, seaborn
```

The `auth.py` module handles token acquisition and caching automatically. In a notebook, tokens are refreshed silently within the same kernel session.

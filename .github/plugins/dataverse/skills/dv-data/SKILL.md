---
name: dv-data
description: >
  Create, update, delete, bulk-import, and upsert Dataverse records using the official Python SDK.
  Use when: "create records", "insert data", "bulk create", "bulk update", "bulk import",
  "import CSV", "load data", "upsert", "upsert records", "write data", "upload file",
  "add records", "CreateMultiple", "UpdateMultiple", "UpsertMultiple",
  "multi-table import", "FK dependencies", "dependency order", "parallel import", "large dataset",
  "create sample data", "seed data", "generate test records", "populate entity",
  "add sample records", "create dummy data", "generate sample accounts",
  "seed the account table", "create test data for".
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

**Correct imports** (always preceded by `sys.path.insert` in a full script — see Setup below):
```
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient
```

**WRONG for SDK-supported operations:**
```
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

Volume guidance: MCP `create_record` for 1-10 records. SDK for 10+ records.

**Important:** The SDK sends all records in a single POST to `CreateMultiple`. It does **not** chunk automatically. Dataverse has no fixed record count limit — the constraints are payload size and request timeout (SDK default: 120s for POST). For larger datasets, you **must** chunk in your script. The `bulk_upsert` and `bulk_create` helpers below use adaptive chunking: start at 1,000, double on success (up to 4,000), halve on payload/timeout failure, and cap at the last successful size. Tables with few columns can handle larger chunks than tables with many columns.

---

## Bulk Update

```python
# Broadcast same change to multiple records
client.records.update("new_ticket",
    [id1, id2, id3],
    {"new_status": 100000001})
```

---

## DataFrame Write-Back

To create or update records from a pandas DataFrame, use the `client.dataframe` namespace. This is documented in **dv-query** (alongside `client.dataframe.get()`) but is a write operation — include it in your data write workflow:

```python
# Update records — DataFrame must include the primary key column
client.dataframe.update("opportunity", df_updates, id_column="opportunityid")

# Create records — returns a Series of new GUIDs
guids = client.dataframe.create("opportunity", df_new_records)
```

See **dv-query** for the full `client.dataframe` reference including `client.dataframe.get()`.

---

## Upsert (Alternate Keys)

Idempotent — re-running the same import does not create duplicates. The alternate key must be defined on the table first — see **dv-metadata**.

**Do NOT include alternate key columns in the record body.** The alternate key identifies the record; the record body contains the data to set. If the same column appears in both, `UpsertMultiple` fails with "An unexpected error occurred" (single upsert tolerates it, bulk does not).

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

> **For imports that may be re-run** (most real-world cases), use `UpsertItem` with alternate keys instead of `create()` — see the Multi-Table Import section below. The `create()` pattern here is for one-shot loads only.

| Volume | Tool | Why |
|---|---|---|
| 1–10 records | MCP `create_record` | Simple, no script |
| 10+ records | SDK `client.records.create(table, list)` | Uses CreateMultiple; chunk large datasets (start at 1K, adapt) |

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

# SDK sends all in one POST — chunk to avoid payload/timeout limits
# Start at 1000; for narrow tables (few columns) you can go higher
chunk_size = 1000
for i in range(0, len(records), chunk_size):
    guids = client.records.create("new_customer", records[i:i + chunk_size])
    print(f"Imported {i + len(guids)}/{len(records)} customers", flush=True)
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
        "new_CustomerId@odata.bind": f"/new_customers({customer_guid})",  # verify entity set name via EntityDefinitions
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

## Multi-Table Import with FK Dependencies

When importing data across multiple tables with foreign key relationships, follow this sequence:

1. **Create tables** with source ID columns (`prefix_Src*Id`) — see **dv-metadata**
2. **Create alternate keys** on the source ID columns — see **dv-metadata** "Alternate Keys" section
3. **Create lookup relationships** — see **dv-metadata**
4. **Import data** in dependency order using `UpsertItem` with alternate keys (safe for re-runs)

Using upsert from the start means partial failures, retries, and re-runs never create duplicates. The alternate key lets Dataverse match records by the source system's ID instead of GUIDs.

**Deciding which alternate key to create:**
- **Database source (SQLite, SQL Server):** Read the schema to identify primary keys. The source PK maps directly to the Dataverse alternate key. Agent can decide without asking.
- **Excel/CSV source:** Inspect the data for columns with all-unique values (`df[col].nunique() == len(df)`). Look for naming conventions (`*_ID`, `*_Code`). **Propose the candidate to the user and confirm** — "Column `Employee_ID` has 500 unique values across 500 rows. Use this as the key?" Do not create the key without confirmation, since uniqueness in current data doesn't guarantee it's the intended business key.

```python
import os, sys, csv, time
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient
from PowerPlatform.Dataverse.models.upsert import UpsertItem
from PowerPlatform.Dataverse.core.errors import HttpError
from concurrent.futures import ThreadPoolExecutor, as_completed

load_env()
client = DataverseClient(base_url=os.environ["DATAVERSE_URL"], credential=get_credential())

def bind(entity_set, guid):
    """Build an @odata.bind value. entity_set must be the actual EntitySetName, not a guess."""
    return f"/{entity_set}({guid})"

# IMPORTANT: EntitySetName is NOT always logical_name + 's'.
# Dataverse uses English pluralization: country -> countries, city -> cities,
# winby -> winbies, extraruns -> extrarunses.
# Always query the actual names before building @odata.bind values:
#   GET /api/data/v9.2/EntityDefinitions?$select=LogicalName,EntitySetName

def bulk_upsert(logical_name, items, chunk_size=1000, retries=3):
    """Upsert items in adaptive chunks with retry. Starts at chunk_size, doubles on
    success (up to max_size), halves on size/timeout failure. Caps at last successful
    size to avoid oscillation. Safe for re-runs."""
    import requests as req_lib  # for timeout exception types
    current_size = chunk_size
    max_size = 4000
    i = 0
    while i < len(items):
        chunk = items[i:i + current_size]
        for attempt in range(retries):
            try:
                client.records.upsert(logical_name, chunk)
                print(f"  {logical_name}: {i + len(chunk)}/{len(items)} (chunk={current_size})", flush=True)
                i += len(chunk)
                current_size = min(current_size * 2, max_size)  # ramp up
                break
            except HttpError as e:
                if e.status_code == 429 and attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                if e.status_code in (413, 500) and current_size > 100:
                    current_size = max(current_size // 2, 100)
                    max_size = current_size
                    print(f"  {logical_name}: chunk capped at {current_size}", flush=True)
                    break  # retry same offset with smaller chunk
                raise
            except req_lib.exceptions.RequestException:
                # Network timeout — SDK default is 120s for POST
                if current_size > 100:
                    current_size = max(current_size // 2, 100)
                    max_size = current_size
                    print(f"  {logical_name}: timeout, chunk capped at {current_size}", flush=True)
                    break
                raise
        else:
            i += len(chunk)  # skip chunk after all retries exhausted

def build_map(logical_name, src_col, id_col):
    """Query Dataverse to build source_id -> GUID map after upsert."""
    result = {}
    for page in client.records.get(logical_name, select=[src_col, id_col]):
        for r in page:
            src_val = r.get(src_col)
            if src_val is not None:
                result[src_val] = r[id_col]
    return result

def upsert_table(logical_name, items, chunk_size=1000):
    """Upsert one table — used as target for ThreadPoolExecutor."""
    bulk_upsert(logical_name, items, chunk_size)
    return logical_name
```

**Import data in dependency levels — parallelize tables within each level:**

Tables at the same dependency level are independent of each other and can be imported concurrently. Tables at different levels must be sequential (Level 1 needs Level 0's GUIDs for `@odata.bind`).

```python
# --- Level 0: All lookup tables concurrently (no FK dependencies) ---
# Alternate keys must already exist. See dv-metadata "Alternate Keys".
level0 = {
    "prefix_country": [UpsertItem(
        alternate_key={"prefix_srccountryid": r["id"]},
        record={"prefix_name": r["name"]},  # key cols must NOT be in record body
    ) for r in country_rows],
    "prefix_team": [UpsertItem(...) for r in team_rows],
    # ... all other Level 0 tables
}

# For composite-key tables (e.g., line items with multi-column PK):
# ALL key columns go in alternate_key, NONE of them in record.
line_items = [UpsertItem(
    alternate_key={
        "prefix_srcorderid": r["order_id"],
        "prefix_srclineno": r["line_no"],
    },
    record={  # only non-key columns here
        "prefix_name": f"Order-{r['order_id']}-Line-{r['line_no']}",
        "prefix_quantity": r["qty"],
        "prefix_unitprice": r["price"],
    },
) for r in order_line_rows]

level0 = {
    # ... lookup tables as above
}

with ThreadPoolExecutor(max_workers=len(level0)) as pool:
    futures = {pool.submit(upsert_table, t, items): t for t, items in level0.items()}
    for f in as_completed(futures):
        table = futures[f]
        try:
            f.result()
            print(f"  {table}: done", flush=True)
        except Exception as e:
            print(f"  {table}: FAILED — {e}", flush=True)
            # Continue — don't kill other tables. Re-run later (upsert is idempotent).

# Build lookup maps by querying back (upsert doesn't return GUIDs)
country_map = build_map("prefix_country", "prefix_srccountryid", "prefix_countryid")
team_map = build_map("prefix_team", "prefix_srcteamid", "prefix_teamid")

# --- Level 1: Tables referencing Level 0, imported concurrently ---
# Build items with @odata.bind using Level 0 maps, then import in parallel
# ... repeat pattern for each level
```

**Key rules:**
- **Parallelize across tables at the same level** — they share no data pages or indexes. Use `ThreadPoolExecutor` with one worker per table.
- **Sequential between levels** — Level 1 needs Level 0's GUIDs for `@odata.bind`.
- **Sequential chunks within each table** — concurrent writes to the same table cause SQL deadlocks (error 1205).
- Use `UpsertItem` with the source system's PK as the alternate key — idempotent, safe for re-runs and partial failures.
- **Do NOT put alternate key columns in the record body.** `UpsertMultiple` fails with "An unexpected error" if key columns appear in both. Single upsert tolerates it; bulk does not.
- **Catch per-table failures in ThreadPoolExecutor** — wrap `f.result()` in try/except. One table failing must not kill the entire executor and prevent other tables from completing.
- Build GUID maps by querying Dataverse after each level (upsert doesn't return GUIDs).
- Start with `chunk_size=1000` and let the adaptive helper ramp up. Dataverse has no fixed record limit — the constraints are payload size and timeout. Narrow tables (few columns) can handle 2000-4000 per chunk.
- `flush=True` on all print statements for real-time progress on Windows.
- If a source row references a missing lookup ID, skip the row and log it.

**Do NOT parallelize chunks within a single table.** Concurrent `UpsertMultiple`/`CreateMultiple` calls to the same table cause SQL Server deadlocks because concurrent inserts contend on shared data pages and index pages — even though the records are different.

### Post-Import Verification

After all levels are imported, verify record counts match the source. Count by iterating pages with a single-column select (memory-efficient — no need to load full DataFrames just for counts):

```python
def count_records(logical_name, id_col):
    return sum(len(page) for page in client.records.get(logical_name, select=[id_col]))

# Build expected counts from source data (e.g., len(rows) per table from earlier import phases)
expected = {"prefix_department": 12, "prefix_employee": 500, "prefix_timesheet": 15000}
for table, exp in expected.items():
    actual = count_records(table, table + "id")  # e.g., prefix_department -> prefix_departmentid
    status = "OK" if actual == exp else f"MISMATCH ({actual})"
    print(f"  {table}: {status} (expected {exp})", flush=True)
```

For deeper verification (spot-check data values, not just counts), use `client.dataframe.get()` — see **dv-query**.

### First-Time Import (when you are certain no re-runs are needed)

If you control the environment and are certain the tables are empty, `client.records.create()` is faster than upsert (no existence check). But if the import fails partway through, re-running will create duplicates. Use this only for one-shot loads into fresh environments:

```python
def bulk_create(logical_name, records, chunk_size=1000):
    """Import via create with adaptive chunking — faster but NOT safe for re-runs."""
    import requests as req_lib
    all_guids = []
    current_size = chunk_size
    max_size = 4000
    i = 0
    while i < len(records):
        chunk = records[i:i + current_size]
        try:
            guids = client.records.create(logical_name, chunk)
            all_guids.extend(guids)
            print(f"  {logical_name}: {i + len(chunk)}/{len(records)} (chunk={current_size})", flush=True)
            i += len(chunk)
            current_size = min(current_size * 2, max_size)
        except HttpError as e:
            if e.status_code in (413, 500) and current_size > 100:
                current_size = max(current_size // 2, 100)
                max_size = current_size
                print(f"  {logical_name}: chunk capped at {current_size}", flush=True)
            else:
                raise
        except req_lib.exceptions.RequestException:
            if current_size > 100:
                current_size = max(current_size // 2, 100)
                max_size = current_size
                print(f"  {logical_name}: timeout, chunk capped at {current_size}", flush=True)
            else:
                raise
    return all_guids
```

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

---

## Sample Data Generation

Generate and insert realistic sample records into any Dataverse table. Useful for development, demos, and testing.

**Use the Python SDK** (`client.records.create()`) — not raw `urllib` or `requests`.

### Agentic Flow

#### Step 1: Confirm environment and count

Before creating anything, confirm:
- **Target environment** — run `pac auth list` to show the active environment
- **Record count** — default is **5 records** unless the user specifies otherwise
- **Table name** — get the logical name (e.g., `account`, `contact`, `cr123_customtable`)

#### Step 2: Inspect the table schema

```bash
python scripts/inspect_schema.py              # defaults to 'account'
python scripts/inspect_schema.py contact      # any table
```

Reports required columns and column types to determine what fake data to generate.

#### Step 3: Create sample records

```bash
python scripts/create_sample_data.py                       # 5 sample accounts (default)
python scripts/create_sample_data.py --table account --count 10
python scripts/create_sample_data.py --table contact --count 20
```

- Uses `client.records.create()` — not raw HTTP
- Individual creates for <= 10, bulk `CreateMultiple` for 10+
- Shows summary table with record IDs

#### Step 4: Generate realistic data

| AttributeType | Generate |
|---|---|
| `String` / `Memo` | Realistic text based on column name (e.g., `name` -> company names) |
| `Integer` / `Decimal` / `Money` | Random values within `MinValue`/`MaxValue` |
| `Boolean` | Alternate `true`/`false` |
| `DateTime` | Recent dates in ISO 8601 format |
| `Picklist` / `Status` | Integer option values (e.g., `industrycode: 1`) |
| `Lookup` | **Skip by default** — only set if user provides valid record IDs |
| `Uniqueidentifier` (non-PK) | Skip — let Dataverse auto-generate |

#### Step 5: Run and verify

Show the user: progress, record IDs, link to view in environment UI, reminder to bulk delete for cleanup.

### Safety Rules for Sample Data

- **Always confirm** the target environment and record count
- Use `.example.com` domains for emails — never real domains
- Use `555-01xx` phone numbers — obviously fake
- Skip lookup fields unless user explicitly asks
- Skip system fields: `createdon`, `modifiedon`, `ownerid`, `statecode`, `statuscode`

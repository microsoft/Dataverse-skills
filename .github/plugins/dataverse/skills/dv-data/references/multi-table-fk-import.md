# Multi-Table Import with FK Dependencies

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

## Post-Import Verification

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

## First-Time Import (when you are certain no re-runs are needed)

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

# Alternate Keys

An alternate key tells Dataverse how to uniquely identify a record using a business column instead of the GUID primary key. This is required for `UpsertMultiple` — without it, Dataverse has no way to detect whether a record already exists.

**When to create alternate keys:** Always create them on source-system ID columns (`prefix_Src*Id`) during schema setup, before data import. This makes every import idempotent from the start — re-running never creates duplicates.

**How the agent decides which column:**
- **Database source (SQLite, SQL Server):** Read the schema to identify primary keys — this is unambiguous. The source PK column maps directly to the alternate key:
  - Source `Country.Country_Id` (INTEGER PRIMARY KEY) → alternate key on `prefix_srccountryid`
  - Source composite PK (`Order_Id, Line_No`) → composite alternate key on both columns
- **Excel/CSV source:** Inspect the data for columns with all-unique values and naming conventions suggesting an ID (`*_ID`, `*_Code`). **Propose the candidate to the user and get confirmation** before creating the key — uniqueness in the current data doesn't guarantee it's the intended business key.
- **No identifiable unique column:** Ask the user which column(s) uniquely identify each row. Do not guess.

**SDK approach (preferred):**

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient

load_env()
client = DataverseClient(os.environ["DATAVERSE_URL"], get_credential())

# Single-column key (most common for imports)
key = client.tables.create_alternate_key(
    "prefix_Country",
    "prefix_SrcCountryIdKey",
    ["prefix_srccountryid"],
    display_name="Source Country ID",
)
print(f"Key created: {key.schema_name} (status: {key.status})")

# Composite key (for tables with multi-column PKs in the source)
key = client.tables.create_alternate_key(
    "prefix_OrderLine",
    "prefix_OrderLineSourceKey",
    ["prefix_srcorderid", "prefix_srclineno"],
    display_name="Source Order Line Key",
)
```

**Idempotent key creation** — catch "already exists" to make the script re-runnable:

```python
from PowerPlatform.Dataverse.core.errors import HttpError

def ensure_alternate_key(table, key_name, columns, display_name):
    try:
        key = client.tables.create_alternate_key(table, key_name, columns, display_name=display_name)
        print(f"  Key created: {key_name} on {table}")
    except HttpError as e:
        if "already exists" in str(e).lower() or "0x80048d0b" in str(e):
            print(f"  Key already exists: {key_name}")
        else:
            raise

# Create keys for all import tables
ensure_alternate_key("prefix_Country", "prefix_SrcCountryIdKey",
    ["prefix_srccountryid"], "Source Country ID")
ensure_alternate_key("prefix_City", "prefix_SrcCityIdKey",
    ["prefix_srccityid"], "Source City ID")
```

**Check key status** — index creation is async for tables with existing data:

```python
keys = client.tables.get_alternate_keys("prefix_Country")
for k in keys:
    print(f"  {k.schema_name}: {k.status}")  # Pending, Active, or Failed
```

**Constraints:**
- Valid column types for keys: Integer, Decimal, String, DateTime, Lookup, OptionSet
- Max 16 columns per key, 900 bytes total key size
- Max 10 alternate keys per table
- Index creation is **async** — Dataverse builds the index in the background. For small tables (<10K rows) this is near-instant. For large existing tables, check `EntityKeyIndexStatus` for Active/Failed before using the key.
- If the key column has non-unique data, index creation **fails** (no data corruption — the key just stays in Failed state). Fix the data, then call `ReactivateEntityKey`.

**Safety:** Creating an alternate key on a column with unique data is a non-destructive metadata operation. It adds a database index — it does not modify existing records. If the column data isn't actually unique, the key creation fails harmlessly.
